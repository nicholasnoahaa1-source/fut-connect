# NoahSpeech-1

A PT-BR-focused automatic speech recognition (ASR) system, built as a LoRA
fine-tune of `openai/whisper-large-v3-turbo`, with a full inference pipeline
(VAD, context-biased decoding, timestamps), a streaming mode, a FastAPI
server, a minimal web UI, and dataset/training/benchmark tooling.

**Status: engineering scaffold, not a trained or benchmarked model.** No
fine-tuning has been run and no WER/CER/RTF numbers exist comparing
NoahSpeech to Whisper — this sandbox has no GPU, no PT-BR dataset, and no
network access to download model weights. Every claim below about
performance is a plan, not a measurement. See `REPORT.md` for exactly what
was and wasn't executed, and what a real run needs.

## What's here and what works right now

| Component | Status in this sandbox |
|---|---|
| Hardware detection (`noahspeech/utils/hardware.py`) | Runs, tested, verified: CPU-only, no CUDA |
| Audio I/O (wav/flac/ogg native, mp3/m4a/webm via ffmpeg) | Runs, tested; ffmpeg not installed here so those 3 formats fall back to a clear error |
| VAD (`noahspeech/inference/vad.py`) | Runs, tested; webrtcvad failed to import here (missing `pkg_resources`) so it uses the energy-based fallback |
| Context engine (custom vocabulary biasing) | Runs, tested |
| Postprocessing | Runs, tested |
| Streaming session buffering | Runs, tested |
| Dataset prep/cleaning scripts | Runs, tested against synthetic CSVs |
| FastAPI app (`/health`, `/models`, upload endpoints, WS) | Runs, tested via TestClient; transcription endpoints 503 without model weights |
| Model loading / LoRA wrapping (`noahspeech/model/loading.py`) | Code is correct and imports cleanly (torch/transformers/peft all installed here); loading real Whisper weights requires Hugging Face Hub access, which this sandbox does not have |
| `scripts/train.py` | Full training loop with OOM-recovery ladder, checkpointing, early stopping — structurally complete but has no dataset/GPU to actually train against here |
| `scripts/evaluate.py`, `scripts/benchmark.py` | Correct, runnable, but need a loaded model + real test set to produce numbers |
| `scripts/quantize.py`, `scripts/export_ctranslate2.py` | Correct, runnable given a trained checkpoint |

## Quickstart

```bash
pip install -r requirements.txt   # torch is large; expect a slow install
pytest tests/ -v                  # 42 passed, 1 skipped (needs HF Hub network) in this sandbox
uvicorn api.app:app --reload      # serves /health, /models immediately;
                                   # transcription endpoints need real weights
python transcribe.py sample.wav --language pt --timestamps --output json
```

Open `web/index.html` in a browser (point "API base URL" at your running
server) for a minimal upload/record/stream UI.

## Project layout

```
noahspeech/
├── noahspeech/          # library: model, audio, inference, streaming, utils
├── api/                 # FastAPI app
├── web/                 # static HTML/JS UI
├── scripts/             # dataset prep/clean, train, evaluate, benchmark, quantize, ctranslate2 export
├── configs/              # LoRA + training YAML configs
├── data/, checkpoints/   # empty scaffolding, see their README.md
├── tests/                # pytest suite (see REPORT.md for pass/skip breakdown)
└── transcribe.py         # CLI
```

## Architecture at a glance

```
audio file/mic
  → normalize + resample (noahspeech/audio)
  → VAD (webrtcvad, energy fallback)
  → [optional noise reduction — not yet implemented, see REPORT.md]
  → Whisper feature extraction + encoder/decoder (LoRA fine-tuned)
  → context engine (vocabulary bias, safe near-miss correction)
  → postprocessing (casing, punctuation, segment merge)
  → text + segment/word timestamps
```

Full design rationale, base-model choice, training hyperparameters, and
metric definitions: see `REPORT.md`.

## Honesty rule

NoahSpeech-1 has never been benchmarked against Whisper. Nothing in this
repo claims otherwise. `scripts/benchmark.py` will mark any model it
couldn't actually run as `not_run` with a reason, rather than filling in a
number.
