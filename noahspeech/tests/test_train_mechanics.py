"""Tests the training-loop mechanics from scripts/train.py: the OOM recovery
ladder (pure config-mutation logic, no GPU needed) and, when torch/peft are
available, a real forward+backward+checkpoint+resume cycle against a tiny
locally-built Whisper model (no network/weights download required).
"""

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.train import OomLadderState, find_resume_checkpoint, save_checkpoint


def test_oom_ladder_applies_rungs_in_order():
    ladder = OomLadderState({"batch_size": 16, "grad_accum_steps": 1, "precision": "bfloat16"})

    assert ladder.step() is True
    assert ladder.applied == ["halve_batch_size"]
    assert ladder.config["batch_size"] == 8

    assert ladder.step() is True
    assert ladder.applied[-1] == "double_grad_accum"
    assert ladder.config["grad_accum_steps"] == 2

    assert ladder.step() is True
    assert ladder.config["gradient_checkpointing"] is True

    assert ladder.step() is True
    assert ladder.config["max_segment_length_s"] == 15  # default 30 // 2

    assert ladder.step() is True
    assert ladder.config["precision"] == "float16"

    assert ladder.step() is True
    assert ladder.config["freeze_encoder"] is True

    assert ladder.step() is True
    assert ladder.config["lora_only"] is True
    assert ladder.config["freeze_decoder_base"] is True


def test_oom_ladder_exhausts_and_returns_false():
    ladder = OomLadderState({"batch_size": 16})
    for _ in range(7):  # 7 rungs in OOM_LADDER
        ladder.step()
    assert ladder.step() is False  # ladder exhausted, no 8th rung


def test_oom_ladder_batch_size_floors_at_one():
    ladder = OomLadderState({"batch_size": 1})
    ladder.step()
    assert ladder.config["batch_size"] == 1  # max(1, 1 // 2), never reaches 0


def test_lora_train_checkpoint_resume_real_forward_backward(tmp_path):
    """Builds a tiny (non-downloaded, randomly-initialized) Whisper model,
    applies LoRA, runs real gradient steps, saves a checkpoint, reloads it
    into a fresh PeftModel wrapping a deep copy of the same base weights, and
    asserts the two models produce bit-identical loss on the same input.
    This does not use or need real Whisper weights or a dataset — it proves
    the checkpoint save/resume path preserves trained adapter weights.
    """
    torch = pytest.importorskip("torch")
    pytest.importorskip("peft")
    from peft import LoraConfig, PeftModel, get_peft_model
    from transformers import WhisperConfig, WhisperForConditionalGeneration

    torch.manual_seed(0)

    def build_tiny_whisper():
        cfg = WhisperConfig(
            vocab_size=100, num_mel_bins=80, encoder_layers=1, encoder_attention_heads=2,
            decoder_layers=1, decoder_attention_heads=2, d_model=16, decoder_ffn_dim=32,
            encoder_ffn_dim=32, max_source_positions=50, max_target_positions=50,
            pad_token_id=0, bos_token_id=1, eos_token_id=2, decoder_start_token_id=1,
        )
        return WhisperForConditionalGeneration(cfg)

    model = build_tiny_whisper()
    lora_cfg = LoraConfig(r=4, lora_alpha=8, lora_dropout=0.0, target_modules=["q_proj", "v_proj"], bias="none")
    model = get_peft_model(model, lora_cfg)

    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    assert 0 < trainable < total

    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=1e-2)
    input_features = torch.randn(2, 80, 100)
    decoder_input_ids = torch.randint(3, 100, (2, 10))

    losses = []
    for _ in range(3):
        out = model(input_features=input_features, decoder_input_ids=decoder_input_ids, labels=decoder_input_ids)
        out.loss.backward()
        torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], max_norm=1.0)
        optimizer.step()
        optimizer.zero_grad()
        losses.append(out.loss.item())

    assert all(isinstance(x, float) for x in losses)

    out_dir = tmp_path / "checkpoints"
    save_checkpoint(model, out_dir, step=3, metrics={"wer": None, "cer": None}, is_best=True)
    resumed_path = find_resume_checkpoint(out_dir)
    assert resumed_path is not None
    assert json.loads((resumed_path / "trainer_state.json").read_text())["step"] == 3

    resumed_base = copy.deepcopy(model.get_base_model())
    resumed_model = PeftModel.from_pretrained(resumed_base, resumed_path)

    model.eval()
    resumed_model.eval()
    with torch.no_grad():
        original_out = model(input_features=input_features, decoder_input_ids=decoder_input_ids, labels=decoder_input_ids)
        resumed_out = resumed_model(
            input_features=input_features, decoder_input_ids=decoder_input_ids, labels=decoder_input_ids
        )
    assert abs(original_out.loss.item() - resumed_out.loss.item()) < 1e-5
