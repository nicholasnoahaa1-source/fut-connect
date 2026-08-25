#!/usr/bin/env python3
"""NoahSpeech-1 CLI: transcribe a local audio file.

Usage:
    python transcribe.py audio.wav --language pt --model noahspeech-1-base \
        --device auto --timestamps --output json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

MODEL_TO_BASE = {
    "noahspeech-1-base": "openai/whisper-large-v3-turbo",
    "noahspeech-1-nano": "openai/whisper-base",
    "noahspeech-1-pro": "openai/whisper-large-v3",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio_path")
    parser.add_argument("--language", default="pt")
    parser.add_argument("--device", default="auto", choices=["auto", "cuda", "mps", "cpu"])
    parser.add_argument("--model", default="noahspeech-1-base", choices=list(MODEL_TO_BASE))
    parser.add_argument("--lora-adapter", default=None)
    parser.add_argument("--timestamps", action="store_true")
    parser.add_argument("--output", choices=["text", "json"], default="text")
    args = parser.parse_args()

    from noahspeech.utils.hardware import detect_hardware

    hw = detect_hardware()
    device = None if args.device == "auto" else args.device

    try:
        from noahspeech.inference.pipeline import TranscriptionPipeline
        from noahspeech.model.loading import load_model
    except ImportError as e:
        print(
            f"error: torch/transformers not installed ({e}). "
            f"Detected hardware: {hw.device} (torch_available={hw.torch_available}).",
            file=sys.stderr,
        )
        raise SystemExit(1)

    bundle = load_model(
        base_model_id=MODEL_TO_BASE[args.model],
        lora_adapter_path=args.lora_adapter,
        device=device,
    )
    pipeline = TranscriptionPipeline(model_bundle=bundle)
    result = pipeline.transcribe(args.audio_path, language=args.language, word_timestamps=args.timestamps)

    if args.output == "json":
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(result.text)
        if args.timestamps:
            for seg in result.segments:
                print(f"[{seg.start:.2f}s - {seg.end:.2f}s] {seg.text}")


if __name__ == "__main__":
    main()
