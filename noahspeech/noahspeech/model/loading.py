"""Model loading: base Whisper checkpoint + optional LoRA adapter.

Architecture notes
-------------------
NoahSpeech-1 does not train a Whisper architecture from scratch. It fine-tunes
a pretrained `openai/whisper-large-v3-turbo` (encoder-decoder transformer,
4 decoder layers vs. 32 in large-v3, ~809M params) using LoRA adapters
injected into the attention projections (default: q_proj, v_proj) of the
decoder, per configs/lora_default.yaml. This keeps the base weights frozen,
trains a small number of adapter params, and produces a checkpoint that is
cheap to store/swap/merge. See REPORT.md for the base-model tradeoff
discussion (turbo vs. medium vs. distil-whisper).
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import yaml


@dataclasses.dataclass
class ModelBundle:
    model: object
    processor: object
    device: str
    dtype: str
    base_model_id: str
    lora_adapter_path: str | None


def load_lora_config(path: str | Path) -> dict:
    with open(path) as f:
        cfg = yaml.safe_load(f)
    required = {"r", "lora_alpha", "lora_dropout", "target_modules"}
    missing = required - cfg.keys()
    if missing:
        raise ValueError(f"LoRA config {path} missing keys: {missing}")
    return cfg


def load_model(
    base_model_id: str = "openai/whisper-large-v3-turbo",
    lora_adapter_path: str | None = None,
    device: str | None = None,
    dtype: str | None = None,
) -> ModelBundle:
    """Load base Whisper + processor, optionally applying a LoRA adapter.

    Requires `transformers` (and `peft` if `lora_adapter_path` is given).
    Raises ImportError with a clear message if unavailable, rather than
    letting an unrelated stack trace surface — this environment has neither
    installed by default, so callers must expect and handle that.
    """
    try:
        import torch
        from transformers import WhisperForConditionalGeneration, WhisperProcessor
    except ImportError as e:
        raise ImportError(
            "load_model() requires torch and transformers to be installed. "
            "In this sandbox they are unavailable (no GPU, restricted network); "
            "install them on a machine with GPU + network access to run this."
        ) from e

    from noahspeech.utils.hardware import detect_hardware, select_dtype

    hw = detect_hardware()
    device = device or hw.device
    torch_dtype = select_dtype(hw) if dtype is None else getattr(torch, dtype)

    processor = WhisperProcessor.from_pretrained(base_model_id)
    model = WhisperForConditionalGeneration.from_pretrained(base_model_id, torch_dtype=torch_dtype)
    model = model.to(device)

    if lora_adapter_path:
        try:
            from peft import PeftModel
        except ImportError as e:
            raise ImportError("lora_adapter_path was given but peft is not installed") from e
        model = PeftModel.from_pretrained(model, lora_adapter_path)

    return ModelBundle(
        model=model,
        processor=processor,
        device=device,
        dtype=str(torch_dtype),
        base_model_id=base_model_id,
        lora_adapter_path=lora_adapter_path,
    )


def apply_lora(model, lora_config: dict):
    """Wrap `model` with a fresh (untrained) LoRA adapter per `lora_config`,
    for starting a new fine-tuning run."""
    try:
        from peft import LoraConfig, get_peft_model
    except ImportError as e:
        raise ImportError("apply_lora() requires peft to be installed") from e

    config = LoraConfig(
        r=lora_config["r"],
        lora_alpha=lora_config["lora_alpha"],
        lora_dropout=lora_config["lora_dropout"],
        target_modules=lora_config["target_modules"],
        bias="none",
    )
    return get_peft_model(model, config)
