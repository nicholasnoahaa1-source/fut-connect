#!/usr/bin/env python3
"""Compare a baseline model (Whisper, local or OpenAI Whisper-1 API) against
NoahSpeech on a PT-BR test set, and emit a markdown comparison table.

The OpenAI Whisper-1 API baseline is only used if OPENAI_API_KEY is set in
the environment; the key is read via os.environ and never logged, printed,
or embedded in output files.

IMPORTANT: this script does not fabricate results. If a model can't be
loaded (missing deps/weights/API key), its row is marked "not run" rather
than filled with invented numbers.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.evaluate import evaluate


def run_noahspeech(test_csv: Path, base_model: str, lora_adapter: str | None, language: str) -> dict:
    try:
        from noahspeech.inference.pipeline import TranscriptionPipeline
        from noahspeech.model.loading import load_model
    except ImportError as e:
        return {"status": "not_run", "reason": f"missing deps: {e}"}

    try:
        bundle = load_model(base_model_id=base_model, lora_adapter_path=lora_adapter)
    except Exception as e:
        return {"status": "not_run", "reason": f"model load failed: {e}"}

    pipeline = TranscriptionPipeline(model_bundle=bundle)
    metrics = evaluate(pipeline, test_csv, language=language)
    return {"status": "ok", **metrics}


def run_openai_whisper1(test_csv: Path, language: str) -> dict:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {"status": "not_run", "reason": "OPENAI_API_KEY not set"}

    try:
        import csv as csv_mod

        import jiwer
        from openai import OpenAI
    except ImportError as e:
        return {"status": "not_run", "reason": f"missing deps: {e}"}

    client = OpenAI(api_key=api_key)
    with open(test_csv, newline="", encoding="utf-8") as f:
        rows = list(csv_mod.DictReader(f))

    references, hypotheses, latencies = [], [], []
    for row in rows:
        t0 = time.monotonic()
        with open(row["audio_path"], "rb") as audio_file:
            resp = client.audio.transcriptions.create(model="whisper-1", file=audio_file, language=language)
        latencies.append(time.monotonic() - t0)
        references.append(row["text"])
        hypotheses.append(resp.text)

    return {
        "status": "ok",
        "n_examples": len(rows),
        "wer": jiwer.wer(references, hypotheses) if references else float("nan"),
        "cer": jiwer.cer(references, hypotheses) if references else float("nan"),
        "latency_mean_s": sum(latencies) / len(latencies) if latencies else float("nan"),
    }


def to_markdown_table(results: dict[str, dict]) -> str:
    cols = ["model", "status", "wer", "cer", "rtf_mean", "latency_p50_s", "model_size_mb", "reason"]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for name, r in results.items():
        row = [name] + [str(r.get(c, "")) for c in cols[1:]]
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("test_csv", type=Path)
    parser.add_argument("--base-model", default="openai/whisper-large-v3-turbo")
    parser.add_argument("--lora-adapter", default=None)
    parser.add_argument("--language", default="pt")
    parser.add_argument("--include-openai-baseline", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("benchmark_results.md"))
    args = parser.parse_args()

    results = {"noahspeech-1": run_noahspeech(args.test_csv, args.base_model, args.lora_adapter, args.language)}
    if args.include_openai_baseline:
        results["whisper-1-api"] = run_openai_whisper1(args.test_csv, args.language)

    table = to_markdown_table(results)
    header = (
        "# NoahSpeech Benchmark\n\n"
        "Rows marked `not_run` were not executed (missing hardware/deps/API key) "
        "and carry no invented numbers — see `reason`.\n\n"
    )
    args.output.write_text(header + table + "\n")
    print(header + table)


if __name__ == "__main__":
    main()
