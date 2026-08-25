#!/usr/bin/env python3
"""End-to-end smoke test of the LoRA training mechanics from scripts/train.py,
without downloading any Whisper weights (impossible in this sandbox — see
REPORT.md). Builds a tiny, randomly-initialized WhisperForConditionalGeneration
locally via WhisperConfig (same architecture family, ~13k params instead of
809M), so every step below is real: real forward pass, real backward pass,
real optimizer step, real loss values, real checkpoint save/resume via PEFT.

This does NOT prove NoahSpeech-1 transcribes anything, or that its loss goes
down on real speech — it proves the *training loop plumbing* (LoRA attach,
gradient flow, checkpointing, resume, OOM-ladder config mutation) is correct
and runs, which is a prerequisite for training on real hardware.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import torch
from peft import LoraConfig, PeftModel, get_peft_model
from transformers import WhisperConfig, WhisperForConditionalGeneration

from scripts.train import OomLadderState, find_resume_checkpoint, save_checkpoint
from noahspeech.model.loading import load_lora_config


def build_tiny_whisper() -> WhisperForConditionalGeneration:
    cfg = WhisperConfig(
        vocab_size=100,
        num_mel_bins=80,
        encoder_layers=1,
        encoder_attention_heads=2,
        decoder_layers=1,
        decoder_attention_heads=2,
        d_model=16,
        decoder_ffn_dim=32,
        encoder_ffn_dim=32,
        max_source_positions=50,
        max_target_positions=50,
        pad_token_id=0,
        bos_token_id=1,
        eos_token_id=2,
        decoder_start_token_id=1,
    )
    return WhisperForConditionalGeneration(cfg)


def main() -> None:
    torch.manual_seed(0)
    out_dir = Path("checkpoints/smoke_test")
    for p in [out_dir / "last_checkpoint", out_dir / "best_model"]:
        if p.exists():
            import shutil

            shutil.rmtree(p)

    model = build_tiny_whisper()
    lora_cfg_dict = load_lora_config("configs/lora_default.yaml")
    lora_cfg = LoraConfig(
        r=lora_cfg_dict["r"],
        lora_alpha=lora_cfg_dict["lora_alpha"],
        lora_dropout=lora_cfg_dict["lora_dropout"],
        target_modules=lora_cfg_dict["target_modules"],
        bias="none",
    )
    model = get_peft_model(model, lora_cfg)
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print(f"LoRA applied: {trainable}/{total} params trainable ({100*trainable/total:.1f}%)")

    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=1e-3)

    ladder = OomLadderState({"batch_size": 8, "grad_accum_steps": 1, "precision": "bfloat16"})
    for _ in range(3):
        ladder.step()
    print(f"OOM ladder after 3 simulated OOMs: {ladder.applied}")
    print(f"resulting config: {ladder.config}")

    losses = []
    for step in range(5):
        input_features = torch.randn(2, 80, 100)
        decoder_input_ids = torch.randint(3, 100, (2, 10))
        out = model(input_features=input_features, decoder_input_ids=decoder_input_ids, labels=decoder_input_ids)
        out.loss.backward()
        torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], max_norm=1.0)
        optimizer.step()
        optimizer.zero_grad()
        losses.append(out.loss.item())
        print(f"step {step}: loss={out.loss.item():.4f}")

    save_checkpoint(model, out_dir, step=5, metrics={"wer": None, "cer": None}, is_best=True)

    resumed_path = find_resume_checkpoint(out_dir)
    assert resumed_path is not None, "checkpoint resume path not found after save"
    # LoRA checkpoints only contain adapter weights, not the (frozen) base
    # model — a real workflow reloads the *same* pretrained base checkpoint
    # both times. Here we reuse the in-memory base directly (deepcopy of the
    # already-tested base) rather than re-instantiating with a new random
    # init, which would make base weights differ and the comparison below
    # meaningless.
    import copy

    resumed_base = copy.deepcopy(model.get_base_model())
    resumed_model = PeftModel.from_pretrained(resumed_base, resumed_path)
    trainer_state = json.loads((resumed_path / "trainer_state.json").read_text())
    print(f"resumed checkpoint trainer_state: {trainer_state}")

    model.eval()
    resumed_model.eval()
    with torch.no_grad():
        input_features = torch.randn(2, 80, 100)
        decoder_input_ids = torch.randint(3, 100, (2, 10))
        original_out = model(input_features=input_features, decoder_input_ids=decoder_input_ids, labels=decoder_input_ids)
        resumed_out = resumed_model(
            input_features=input_features, decoder_input_ids=decoder_input_ids, labels=decoder_input_ids
        )
    loss_diff = abs(original_out.loss.item() - resumed_out.loss.item())
    print(f"loss diff (same input, original vs resumed model): {loss_diff:.6f}")
    assert loss_diff < 1e-4, "resumed model does not match saved model's weights"

    print(json.dumps({
        "status": "smoke_test_passed",
        "losses": losses,
        "loss_decreased": losses[-1] < losses[0],
        "trainable_params": trainable,
        "total_params": total,
        "oom_ladder_applied": ladder.applied,
        "checkpoint_resume_verified": True,
    }, indent=2))


if __name__ == "__main__":
    main()
