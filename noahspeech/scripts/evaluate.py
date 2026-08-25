#!/usr/bin/env python3
"""Compute WER/CER (via jiwer), RTF, latency percentiles (P50/P95/P99),
VRAM/RAM usage, and model size for a NoahSpeech (or any Whisper-compatible)
model against a test CSV (audio_path,text).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import jiwer

from noahspeech.utils.hardware import detect_hardware


def percentile(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    idx = min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))
    return s[idx]


def model_size_mb(model) -> float:
    total_bytes = sum(p.numel() * p.element_size() for p in model.parameters())
    return round(total_bytes / (1024 * 1024), 2)


def evaluate(pipeline, test_csv: Path, language: str = "pt") -> dict:
    with open(test_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    references, hypotheses, latencies, rtfs = [], [], [], []

    for row in rows:
        t0 = time.monotonic()
        result = pipeline.transcribe(row["audio_path"], language=language)
        elapsed = time.monotonic() - t0

        references.append(row["text"])
        hypotheses.append(result.text)
        latencies.append(elapsed)
        if result.duration_s > 0:
            rtfs.append(elapsed / result.duration_s)

    wer = jiwer.wer(references, hypotheses) if references else float("nan")
    cer = jiwer.cer(references, hypotheses) if references else float("nan")
    hw = detect_hardware()

    metrics = {
        "n_examples": len(rows),
        "wer": wer,
        "cer": cer,
        "rtf_mean": sum(rtfs) / len(rtfs) if rtfs else float("nan"),
        "latency_p50_s": percentile(latencies, 50),
        "latency_p95_s": percentile(latencies, 95),
        "latency_p99_s": percentile(latencies, 99),
        "device": hw.device,
        "vram_gb": hw.total_vram_gb,
        "ram_gb": hw.total_ram_gb,
    }
    if pipeline.model_bundle is not None:
        metrics["model_size_mb"] = model_size_mb(pipeline.model_bundle.model)
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("test_csv", type=Path)
    parser.add_argument("--base-model", default="openai/whisper-large-v3-turbo")
    parser.add_argument("--lora-adapter", default=None)
    parser.add_argument("--language", default="pt")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    try:
        from noahspeech.inference.pipeline import TranscriptionPipeline
        from noahspeech.model.loading import load_model
    except ImportError as e:
        raise SystemExit(f"evaluate.py requires torch/transformers to be installed: {e}")

    bundle = load_model(base_model_id=args.base_model, lora_adapter_path=args.lora_adapter)
    pipeline = TranscriptionPipeline(model_bundle=bundle)
    metrics = evaluate(pipeline, args.test_csv, language=args.language)

    output = json.dumps(metrics, indent=2)
    print(output)
    if args.output:
        args.output.write_text(output)


if __name__ == "__main__":
    main()
