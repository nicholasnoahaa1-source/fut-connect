#!/usr/bin/env python3
"""Export FP32/FP16/BF16/INT8 variants of a NoahSpeech checkpoint for
deployment tradeoffs (VRAM vs. accuracy vs. latency)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PRECISIONS = ("fp32", "fp16", "bf16", "int8")


def quantize(model_path: str, output_dir: Path, precision: str) -> Path:
    if precision not in PRECISIONS:
        raise ValueError(f"precision must be one of {PRECISIONS}, got {precision}")

    try:
        import torch
        from transformers import WhisperForConditionalGeneration
    except ImportError as e:
        raise SystemExit(f"quantize.py requires torch/transformers: {e}")

    model = WhisperForConditionalGeneration.from_pretrained(model_path)

    if precision == "fp32":
        model = model.to(torch.float32)
    elif precision == "fp16":
        model = model.to(torch.float16)
    elif precision == "bf16":
        model = model.to(torch.bfloat16)
    elif precision == "int8":
        try:
            model = torch.quantization.quantize_dynamic(model, {torch.nn.Linear}, dtype=torch.qint8)
        except Exception as e:
            raise SystemExit(
                f"dynamic INT8 quantization failed ({e}); for GPU INT8 use "
                "bitsandbytes load_in_8bit=True at load time instead."
            )

    out_path = output_dir / precision
    out_path.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out_path)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_path")
    parser.add_argument("--output-dir", type=Path, default=Path("checkpoints/quantized"))
    parser.add_argument("--precision", choices=PRECISIONS, action="append", dest="precisions")
    args = parser.parse_args()

    precisions = args.precisions or list(PRECISIONS)
    for precision in precisions:
        out_path = quantize(args.model_path, args.output_dir, precision)
        print(f"{precision}: saved to {out_path}")


if __name__ == "__main__":
    main()
