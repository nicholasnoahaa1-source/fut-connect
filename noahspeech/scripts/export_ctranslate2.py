#!/usr/bin/env python3
"""Convert a (LoRA-merged) NoahSpeech checkpoint to CTranslate2 format for
faster-whisper-style optimized inference."""

from __future__ import annotations

import argparse
from pathlib import Path


def merge_lora_if_needed(model_path: str, lora_adapter: str | None, merged_dir: Path) -> str:
    if not lora_adapter:
        return model_path
    try:
        from peft import PeftModel
        from transformers import WhisperForConditionalGeneration
    except ImportError as e:
        raise SystemExit(f"merging LoRA requires transformers+peft: {e}")

    base = WhisperForConditionalGeneration.from_pretrained(model_path)
    merged = PeftModel.from_pretrained(base, lora_adapter).merge_and_unload()
    merged_dir.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(merged_dir)
    return str(merged_dir)


def export_ctranslate2(model_path: str, output_dir: Path, quantization: str) -> None:
    try:
        import ctranslate2.converters  # noqa: F401
    except ImportError as e:
        raise SystemExit(
            f"export_ctranslate2.py requires the `ctranslate2` package: {e}\n"
            "Install it (pip install ctranslate2) on a machine with network access."
        )

    from ctranslate2.converters.transformers import TransformersConverter

    converter = TransformersConverter(model_path)
    converter.convert(str(output_dir), quantization=quantization, force=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_path")
    parser.add_argument("--lora-adapter", default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("checkpoints/ctranslate2"))
    parser.add_argument("--merged-dir", type=Path, default=Path("checkpoints/merged"))
    parser.add_argument("--quantization", default="int8_float16",
                         choices=["float32", "float16", "bfloat16", "int8", "int8_float16", "int8_bfloat16"])
    args = parser.parse_args()

    resolved_path = merge_lora_if_needed(args.model_path, args.lora_adapter, args.merged_dir)
    export_ctranslate2(resolved_path, args.output_dir, args.quantization)
    print(f"CTranslate2 model exported to {args.output_dir} (quantization={args.quantization})")
    print("Use with faster-whisper: WhisperModel(str(output_dir), device=..., compute_type=...)")


if __name__ == "__main__":
    main()
