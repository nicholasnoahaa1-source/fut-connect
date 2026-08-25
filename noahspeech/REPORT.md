# NoahSpeech-1 — Engineering Report

## 1. Architecture

```
audio (wav/mp3/m4a/flac/ogg/webm, or live mic)
  |
  v normalize + resample to 16kHz mono           noahspeech/audio/io.py
  v VAD (speech segment detection)                noahspeech/inference/vad.py
  v [optional noise reduction - NOT IMPLEMENTED, see section 6]
  v Whisper feature extraction (log-mel spectrogram, via WhisperProcessor)
  v Whisper encoder/decoder, LoRA-adapted          noahspeech/model/loading.py
  v context engine (vocabulary logit bias +
    safe near-miss rescoring)                      noahspeech/inference/context_engine.py
  v postprocessing (casing, punctuation,
    short-segment merge)                           noahspeech/inference/postprocess.py
  v
text + segment/word timestamps
```

Streaming mode (`noahspeech/streaming/buffer.py`) wraps the same decode path
with VAD-gated chunk buffering: partial results on a rolling window, final
results on a detected silence gap, exposed over the `/v1/audio/stream`
WebSocket.

## 2. Base model choice: whisper-large-v3-turbo vs. medium vs. distil-whisper

**Labeled as public-knowledge reasoning, not measured here** — this sandbox
has no GPU to benchmark any of these.

| Model | Params | Relative latency | Relative VRAM (fp16) | Multilingual accuracy (general reputation) |
|---|---|---|---|---|
| whisper-large-v3 | 1.55B | baseline (slowest) | ~10GB | highest |
| whisper-large-v3-turbo (chosen) | 809M (4 decoder layers vs. 32) | ~5-8x faster than large-v3 | ~6GB | close to large-v3, small regression on rare languages/tail cases |
| whisper-medium | 769M | faster than large-v3, similar order to turbo | ~5GB | noticeably below large-v3/turbo on non-English |
| distil-whisper (distil-large-v3) | ~756M (2 decoder layers) | fastest, distillation-optimized for English | ~5GB | strong on English, publicly documented as English-focused — not a good PT-BR starting point |

**Choice: `whisper-large-v3-turbo`.** It keeps large-v3's encoder (where most
multilingual acoustic knowledge lives) while cutting decoder depth for
latency/VRAM, and — unlike distil-whisper's public releases — was distilled
with multilingual (not English-only) data, making it a defensible base for a
PT-BR LoRA fine-tune. `configs/model_variants.yaml` also plans nano
(whisper-base, for edge/CPU) and pro (whisper-large-v3, for max accuracy)
variants for later, but base/turbo is the only one this codebase currently
targets.

## 3. Dataset plan

Format: CSV with `audio_path,text` columns (`data/README.md`). Pipeline:
1. `scripts/clean_dataset.py` — flags/removes corrupt audio (unreadable by
   soundfile/ffmpeg), empty transcripts, out-of-range duration
   (<0.5s or >30s, configurable), duplicate audio paths, duplicate
   transcript text, near-silent clips (RMS below threshold), and abnormal
   volume (clipping ratio above threshold).
2. `scripts/prepare_dataset.py` — 90/5/5 train/val/test split, deduplicated
   by resolved audio path before splitting, with an explicit
   `assert_no_leakage` check that raises if any file appears in more than
   one split. This is enforced by a passing test
   (`tests/test_dataset_scripts.py::test_prepare_dataset_split_ratios_and_no_leakage`),
   not just documented.

No PT-BR audio corpus is present in this repository or sandbox. Real
options for someone running this with data: Common Voice PT-BR, CORAA,
MLS Portuguese, or a proprietary corpus in the CSV format above.

## 4. Training plan / hyperparameters

Starting LoRA config (`configs/lora_default.yaml`), as specified:
```yaml
r: 16
lora_alpha: 32
lora_dropout: 0.05
target_modules: [q_proj, v_proj]
```
`configs/lora_wide.yaml` is a documented fallback (r=32, wider target
modules) for a second pass if error analysis shows underfitting.

`scripts/train.py` implements: BF16 primary / FP16 fallback / FP32 last
resort (`select_dtype` in `noahspeech/utils/hardware.py`), gradient
accumulation, gradient checkpointing, linear warmup + decay, gradient
clipping, early stopping on validation WER, periodic checkpointing to
`checkpoints/last_checkpoint/` with auto-resume, and best-model tracking to
`checkpoints/best_model/`. Per-step logging captures device, VRAM, batch
size, learning rate, epoch, loss, WER/CER, and wall-clock duration.

**OOM auto-recovery ladder** (`OOM_LADDER` in `scripts/train.py`), applied in
order and cumulatively on a `torch.cuda.OutOfMemoryError`:
1. halve batch size
2. double gradient accumulation steps
3. enable gradient checkpointing
4. shrink max audio segment length
5. downgrade precision (bf16 → fp16 → fp32)
6. freeze more base-model parameters (encoder)
7. fall back to LoRA-only (freeze everything but adapter weights)

This is real, unit-testable logic (each rung mutates a config dict
deterministically) but **has never actually caught a real CUDA OOM** in this
sandbox, since there is no GPU here to trigger one.

Iterative improvement loop (planned, not executed): run `benchmark.py` then
bucket errors by category (proper nouns, numbers, accents, code-switching,
background noise) using WER-per-example breakdowns, then adjust LoRA target
modules / data mix / augmentation, then retrain, then re-benchmark. No error
analysis exists yet because no model has been trained.

## 5. Metric definitions

- **WER / CER**: word/character error rate via `jiwer`, standard
  Levenshtein-based edit distance over reference vs. hypothesis.
- **RTF (real-time factor)**: `inference_time_s / audio_duration_s`; <1.0
  means faster than real time.
- **Latency P50/P95/P99**: percentiles of per-example wall-clock inference
  time across the test set.
- **VRAM/RAM**: `torch.cuda.get_device_properties().total_memory` (VRAM) and
  `/proc/meminfo` MemTotal (RAM), via `noahspeech/utils/hardware.py`.
- **Model size**: sum of `param.numel() * param.element_size()` across all
  parameters, in MB.

All four are implemented in `scripts/evaluate.py` and wired into
`scripts/benchmark.py`'s markdown table.

## 6. Known gaps / not yet implemented

- **Noise reduction** stage is a documented no-op in the pipeline diagram —
  no denoising library is wired in. Next step: integrate a spectral-gating
  or RNNoise-based pass ahead of feature extraction, gated by a config flag.
- **Word-level timestamps**: the pipeline returns segment-level timestamps
  (VAD segment boundaries); per-word timestamps require Whisper's
  `return_timestamps="word"` / DTW-based alignment, which needs a loaded
  model to test — stubbed as an empty `words` list in `Segment` until then.
- **Knowledge distillation** script was in scope per the original spec but
  is not implemented — deprioritized versus getting the LoRA training loop,
  OOM ladder, and full pipeline correct and tested; would follow the same
  "requires GPU, fails loud without one" pattern as `train.py`.

## 7. Environment Constraints & What Was Actually Executed

**Hardware**: no NVIDIA GPU present (`nvidia-smi`: command not found).
`noahspeech.utils.hardware.detect_hardware()` was run in this sandbox and
returned (from the actual pytest run):

```
device: cpu
torch_available: True (version=2.13.0+cu130)
cuda_available: False (devices=0)
mps_available: False
vram_gb: None
recommended_dtype: float32
```
This is asserted by `tests/test_hardware.py::test_no_gpu_in_this_sandbox`.

**Dataset**: no PT-BR audio corpus is present anywhere in this repo or
sandbox. All dataset-script tests use small synthetic sine-wave WAV files
generated in `tests/conftest.py` / `tests/test_dataset_scripts.py`, not real
speech.

**Network**: PyPI was reachable (regular package installs succeeded); the
Hugging Face Hub was **not** reachable — every attempt to fetch
`openai/whisper-tiny` metadata or load a `WhisperProcessor`/
`WhisperForConditionalGeneration` failed with `httpx.ProxyError: 403
Forbidden` through the sandbox's proxy. This was tried directly (not
inferred) — running `python transcribe.py <nonexistent.wav>` fails at model
load, before ever reaching the missing-file problem, with:
```
huggingface_hub.hf_api.list_repo_tree(...)
  -> httpcore.ProxyError: 403 Forbidden
  -> transformers WhisperProcessor.from_pretrained(...) raises httpx.ProxyError
```
Because of this, **no Whisper checkpoint of any size — including
whisper-tiny — was downloaded or run in this sandbox**, and no smoke-test
transcription of real or synthetic speech audio through an actual model was
possible here.

**What successfully installed and import-verified in this sandbox**:
torch 2.13.0+cu130 (CPU build), transformers 5.15.1, peft 0.20.0,
accelerate 1.14.0, datasets 5.0.1, jiwer 4.0.0, soundfile, librosa 0.11.0,
pydub, ctranslate2 4.8.1, faster-whisper 1.2.1, fastapi, uvicorn, pyyaml,
pytest, pytest-asyncio, httpx.

**What failed to install/import**: `webrtcvad` installed via pip but fails
to `import` here (`ModuleNotFoundError: No module named 'pkg_resources'` —
setuptools not present at import time in this interpreter); the codebase
falls back to an energy-based VAD automatically (verified by passing tests
in `tests/test_vad.py`, which exercise whichever backend is actually
active). The `ffmpeg` binary is not installed, so mp3/m4a/webm/aac decoding
raises a clear `AudioLoadError` rather than working — this is by design
(see `noahspeech/audio/io.py`); the `Dockerfile` does install `ffmpeg` for a
real deployment.

**Test suite — actually run, real output**:
```
$ pytest tests/ -v
======================== 42 passed, 1 skipped in ~8.5s ========================
```
The single skip (`test_model_loading.py::test_load_model_downloads_and_loads_whisper`)
is explicitly marked `@pytest.mark.skip` with the reason "requires network
access to Hugging Face Hub to download whisper weights; not available in
this sandbox" — it is not disguised as a pass. Every other test, including
API tests (FastAPI `TestClient`, no live server/network needed), dataset
cleaning/splitting/leakage tests, VAD, context engine, audio I/O, hardware
detection, streaming buffer logic, and LoRA-wrapping (tested against a tiny
2-linear-layer `nn.Module`, not real Whisper weights — peft's LoRA wrapping
doesn't require model-specific weights to verify it attaches trainable
low-rank adapters and freezes the base), passed for real by executing the
code, not by mocking away the assertion.

**No WER/CER/RTF numbers for NoahSpeech vs. Whisper-1 exist anywhere in this
repository.** `scripts/benchmark.py`, run against any test set in this
sandbox, would report `noahspeech-1: not_run (reason: model load failed —
no HF Hub access)` — that is the honest current state, not a placeholder to
be filled in later by hand.

**Dataset pipeline end-to-end smoke test (actually run, real output)**: since
no PT-BR audio corpus is available here, `scripts/dev/generate_synthetic_sample.py`
writes 12 rows of sine-tone-plus-noise WAV files (not speech — useless for
training, only for exercising file-level logic) into `data/raw_sample/`,
with 7 rows deliberately defective: a reused audio path, a duplicate
transcript, an empty transcript, a near-silent file, a too-short file, a
clipped/too-loud file, and a corrupt (non-audio) file. Running
`scripts/clean_dataset.py data/raw_sample/manifest.csv` on it produced:
```
{
  "total_rows": 12, "clean_rows": 5, "rejected_rows": 7,
  "issue_counts": {
    "duplicate_audio_path": 2, "duplicate_transcript_text": 1,
    "empty_transcript": 1, "near_silent": 1, "duration_too_short": 1,
    "abnormal_volume_clipping": 1, "corrupt_audio": 1
  }
}
```
All 7 planted defects were caught correctly, 5 clean rows passed. Feeding
`manifest_clean.csv` into `scripts/prepare_dataset.py` then produced a
90/5/5 split (`train: 4, val: 0, test: 1` — val rounds to 0 at n=5, expected
at this tiny scale) with `"leakage_check": "passed"`. The full `pytest
tests/ -v` suite was re-run afterward and still reports **42 passed, 1
skipped**. This confirms the dataset pipeline's file-handling and validation
logic is correct; it does not and cannot validate transcript *quality*,
since the audio is not real speech.

**LoRA training-loop mechanics smoke test (actually run, real output)**:
`scripts/train.py`'s real forward/backward pass is stubbed with
`NotImplementedError` (see above) because there is no PT-BR dataset and no
downloadable Whisper checkpoint here. To validate the surrounding mechanics
that *don't* depend on either — LoRA adapter attachment, the OOM recovery
ladder's config mutations, gradient clipping, checkpoint save, and
checkpoint resume — `scripts/dev/train_smoke_test.py` builds a tiny,
randomly-initialized `WhisperForConditionalGeneration` locally via
`WhisperConfig` (no network call, ~13k params instead of whisper-large-v3
-turbo's ~809M), wraps it with the repo's real `configs/lora_default.yaml`
(r=16/alpha=32/dropout=0.05 on q_proj/v_proj), and runs real training steps
against random tensors of the correct shape. Real output:
```
LoRA applied: 3072/16496 params trainable (18.6%)
OOM ladder after 3 simulated OOMs: ['halve_batch_size', 'double_grad_accum', 'enable_grad_checkpointing']
resulting config: {'batch_size': 4, 'grad_accum_steps': 2, 'precision': 'bfloat16', 'gradient_checkpointing': True}
step 0: loss=4.3997
step 1: loss=4.4217
step 2: loss=4.3951
step 3: loss=4.4116
step 4: loss=4.3837
loss diff (same input, original vs resumed model): 0.000000
```
Losses fluctuate rather than monotonically decrease — expected for 5 steps
on random labels with no real signal to learn, not a claim of convergence.
The checkpoint-resume loss diff of exactly `0.000000` confirms save/resume
preserves the trained LoRA adapter weights bit-for-bit. This mechanics test
is now also a permanent pytest test
(`tests/test_train_mechanics.py::test_lora_train_checkpoint_resume_real_forward_backward`,
plus 3 pure-logic tests of the OOM ladder), so `pytest tests/ -v` now
reports **46 passed, 1 skipped** (up from 42 passed).

This proves the training *plumbing* is correct. It proves nothing about
transcription accuracy — that requires the real whisper-large-v3-turbo
checkpoint and a real PT-BR dataset, neither available here.

## 8. Next steps for someone with a GPU + PT-BR dataset

1. `pip install -r requirements.txt` on a machine with network access to
   Hugging Face Hub and a CUDA GPU.
2. Assemble a PT-BR CSV (`audio_path,text`) — e.g. from Common Voice PT-BR —
   and run `scripts/clean_dataset.py` then `scripts/prepare_dataset.py`.
3. `python scripts/train.py --config configs/training_base.yaml` — this will
   need the `NotImplementedError` placeholder in `run_training()` (the
   actual per-batch forward/backward loop against a `datasets.Dataset`) wired
   up to the prepared CSV splits; the surrounding OOM ladder, checkpointing,
   and logging infrastructure is already complete.
4. `python scripts/evaluate.py data/splits/test.csv --lora-adapter checkpoints/best_model`
   for real WER/CER/RTF/latency numbers.
5. `python scripts/benchmark.py data/splits/test.csv --include-openai-baseline`
   (with `OPENAI_API_KEY` set) for a real NoahSpeech-vs-Whisper-1 comparison
   table — only then would a performance claim be honest.
