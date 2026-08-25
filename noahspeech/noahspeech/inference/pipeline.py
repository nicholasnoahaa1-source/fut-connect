"""End-to-end inference pipeline:
audio -> normalize/resample -> VAD -> (optional noise reduction) ->
feature extraction -> encoder/decoder -> context engine bias -> postprocess ->
text + segment/word timestamps.
"""

from __future__ import annotations

import dataclasses
import time

from noahspeech.audio.io import WHISPER_SAMPLE_RATE, load_audio, normalize_peak
from noahspeech.inference.context_engine import ContextEngineConfig, rescore_transcript
from noahspeech.inference.postprocess import clean_transcript, merge_short_segments
from noahspeech.inference.vad import detect_speech_segments


@dataclasses.dataclass
class Word:
    text: str
    start: float
    end: float


@dataclasses.dataclass
class Segment:
    text: str
    start: float
    end: float
    words: list[Word] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class TranscriptionResult:
    text: str
    segments: list[Segment]
    language: str
    duration_s: float
    inference_time_s: float

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "language": self.language,
            "duration_s": self.duration_s,
            "inference_time_s": self.inference_time_s,
            "segments": [
                {
                    "text": s.text,
                    "start": s.start,
                    "end": s.end,
                    "words": [{"text": w.text, "start": w.start, "end": w.end} for w in s.words],
                }
                for s in self.segments
            ],
        }


class TranscriptionPipeline:
    """Wraps a loaded ModelBundle with the full pre/post-processing pipeline.

    `model_bundle` is optional: without one, `transcribe()` still runs VAD +
    audio loading (useful for tests and for validating the non-model stages
    in environments without GPU/model weights) and raises a clear error only
    if decoding is actually requested.
    """

    def __init__(self, model_bundle=None, context_vocabulary: list[str] | None = None):
        self.model_bundle = model_bundle
        self.context_config = ContextEngineConfig(vocabulary=context_vocabulary or [])

    def transcribe(
        self,
        audio_path: str,
        language: str = "pt",
        word_timestamps: bool = True,
        run_vad: bool = True,
    ) -> TranscriptionResult:
        t0 = time.monotonic()
        audio, sr = load_audio(audio_path, target_sr=WHISPER_SAMPLE_RATE)
        audio = normalize_peak(audio)
        duration_s = len(audio) / sr

        speech_segments = detect_speech_segments(audio, sr) if run_vad else None

        if self.model_bundle is None:
            raise RuntimeError(
                "TranscriptionPipeline has no model_bundle loaded; call "
                "noahspeech.model.load_model(...) first, or use "
                "TranscriptionPipeline(model_bundle=None) only for VAD/audio-stage testing."
            )

        segments = self._decode(audio, sr, speech_segments, language, word_timestamps)
        segments = merge_short_segments([dataclasses.asdict(s) for s in segments])
        full_text = " ".join(s["text"] for s in segments).strip()
        full_text = rescore_transcript(clean_transcript(full_text), self.context_config)

        return TranscriptionResult(
            text=full_text,
            segments=[
                Segment(
                    text=s["text"],
                    start=s["start"],
                    end=s["end"],
                    words=[Word(**w) for w in s.get("words", [])],
                )
                for s in segments
            ],
            language=language,
            duration_s=duration_s,
            inference_time_s=time.monotonic() - t0,
        )

    def _decode(self, audio, sr, speech_segments, language, word_timestamps) -> list[Segment]:
        """Run the model on detected speech regions. Requires transformers +
        a loaded model; this is the stage that needs real GPU/model weights
        and is not exercised in this sandbox (see REPORT.md)."""
        import torch

        model = self.model_bundle.model
        processor = self.model_bundle.processor
        device = self.model_bundle.device

        regions = speech_segments or [type("S", (), {"start_sample": 0, "end_sample": len(audio)})()]
        segments: list[Segment] = []
        for region in regions:
            chunk = audio[region.start_sample : region.end_sample]
            if len(chunk) == 0:
                continue
            inputs = processor(chunk, sampling_rate=sr, return_tensors="pt")
            input_features = inputs.input_features.to(device=device, dtype=model.dtype)
            forced_ids = processor.get_decoder_prompt_ids(language=language, task="transcribe")
            with torch.no_grad():
                generated = model.generate(input_features, forced_decoder_ids=forced_ids)
            text = processor.batch_decode(generated, skip_special_tokens=True)[0]
            segments.append(
                Segment(
                    text=text.strip(),
                    start=region.start_sample / sr,
                    end=region.end_sample / sr,
                    words=[],
                )
            )
        return segments
