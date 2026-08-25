"""FastAPI app exposing NoahSpeech over an OpenAI-compatible-ish surface:
POST /v1/audio/transcriptions, POST /v1/audio/translations, GET /health,
GET /models, and a streaming WebSocket at /v1/audio/stream.

The model is loaded lazily on first use (not at import/startup time) so the
app itself always starts and /health and /models always work, even in an
environment with no GPU/model weights — only the transcription endpoints
require a real model and return a 503 with a clear reason otherwise.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from noahspeech import __version__
from noahspeech.utils.hardware import detect_hardware

app = FastAPI(title="NoahSpeech-1 API", version=__version__)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_model_cache: dict[str, object] = {}

AVAILABLE_MODELS = [
    {"id": "noahspeech-1-base", "base_model": "openai/whisper-large-v3-turbo", "status": "in_development"},
    {"id": "noahspeech-1-nano", "base_model": "openai/whisper-base", "status": "planned"},
    {"id": "noahspeech-1-pro", "base_model": "openai/whisper-large-v3", "status": "planned"},
]


class TranscriptionResponse(BaseModel):
    text: str
    language: str
    duration_s: float
    inference_time_s: float
    segments: list[dict]


def _get_pipeline(model_id: str):
    if model_id in _model_cache:
        return _model_cache[model_id]

    variant = next((m for m in AVAILABLE_MODELS if m["id"] == model_id), None)
    if variant is None:
        raise HTTPException(status_code=404, detail=f"unknown model '{model_id}'")

    try:
        from noahspeech.inference.pipeline import TranscriptionPipeline
        from noahspeech.model.loading import load_model
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"model backend unavailable in this deployment (torch/transformers not installed): {e}",
        )

    try:
        bundle = load_model(base_model_id=variant["base_model"])
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"failed to load model '{model_id}': {e}")

    pipeline = TranscriptionPipeline(model_bundle=bundle)
    _model_cache[model_id] = pipeline
    return pipeline


@app.get("/health")
def health() -> dict:
    hw = detect_hardware()
    return {
        "status": "ok",
        "version": __version__,
        "device": hw.device,
        "torch_available": hw.torch_available,
    }


@app.get("/models")
def models() -> dict:
    return {"data": AVAILABLE_MODELS}


async def _save_upload(file: UploadFile) -> str:
    suffix = Path(file.filename or "audio.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        return tmp.name


@app.post("/v1/audio/transcriptions", response_model=TranscriptionResponse)
async def transcribe(
    file: UploadFile = File(...),
    model: str = Form("noahspeech-1-base"),
    language: str = Form("pt"),
    timestamps: bool = Form(True),
):
    path = await _save_upload(file)
    try:
        pipeline = _get_pipeline(model)
        result = pipeline.transcribe(path, language=language, word_timestamps=timestamps)
    finally:
        Path(path).unlink(missing_ok=True)
    return result.to_dict()


@app.post("/v1/audio/translations", response_model=TranscriptionResponse)
async def translate(
    file: UploadFile = File(...),
    model: str = Form("noahspeech-1-base"),
    timestamps: bool = Form(True),
):
    """Translates PT-BR (or detected source language) audio to English text."""
    path = await _save_upload(file)
    try:
        pipeline = _get_pipeline(model)
        # target language fixed to English for /translations, per Whisper's
        # translate task semantics.
        result = pipeline.transcribe(path, language="en", word_timestamps=timestamps)
    finally:
        Path(path).unlink(missing_ok=True)
    return result.to_dict()


@app.websocket("/v1/audio/stream")
async def stream(websocket: WebSocket, model: str = "noahspeech-1-base", language: str = "pt"):
    """Streaming transcription: client sends raw 16kHz mono float32 PCM bytes
    as binary WebSocket frames; server sends back JSON partial/final results."""
    await websocket.accept()

    try:
        pipeline = _get_pipeline(model)
    except HTTPException as e:
        await websocket.send_json({"error": e.detail})
        await websocket.close()
        return

    import numpy as np

    from noahspeech.audio.io import WHISPER_SAMPLE_RATE
    from noahspeech.streaming.buffer import StreamingSession

    def _transcribe_fn(chunk: np.ndarray, sr: int) -> str:
        import soundfile as sf

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            sf.write(tmp.name, chunk, sr)
            try:
                return pipeline.transcribe(tmp.name, language=language, run_vad=False).text
            finally:
                Path(tmp.name).unlink(missing_ok=True)

    session = StreamingSession(_transcribe_fn, sample_rate=WHISPER_SAMPLE_RATE)

    try:
        while True:
            data = await websocket.receive_bytes()
            pcm = np.frombuffer(data, dtype=np.float32)
            for result in session.push_chunk(pcm):
                await websocket.send_json(
                    {
                        "text": result.text,
                        "is_final": result.is_final,
                        "start_s": result.chunk_start_s,
                        "end_s": result.chunk_end_s,
                        "ts": time.time(),
                    }
                )
    except WebSocketDisconnect:
        pass
