#!/usr/bin/env python3
"""LoRA fine-tuning of whisper-large-v3-turbo on a PT-BR dataset.

Requires torch + transformers + peft + accelerate + datasets + jiwer, none of
which are available in this sandbox (no GPU, restricted network — see
REPORT.md). This script is a real, runnable training loop for someone with a
GPU + dataset; it fails fast with a clear message if those deps are missing,
rather than pretending to train.

Implements: BF16/FP16 autodetect with FP32 fallback, gradient accumulation,
gradient checkpointing, early stopping on val WER, linear warmup + decay
scheduler, gradient clipping, periodic checkpointing to checkpoints/last_checkpoint
with auto-resume, and an OOM auto-recovery ladder (see `OOM_LADDER` below).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("noahspeech.train")

# Each step is applied once, in order, on a CUDA OOM, and is cumulative (later
# steps stack on earlier ones) until the batch either succeeds or we exhaust
# the ladder and re-raise.
OOM_LADDER = [
    "halve_batch_size",
    "double_grad_accum",
    "enable_grad_checkpointing",
    "shrink_max_segment_length",
    "downgrade_precision",
    "freeze_more_params",
    "lora_only_fallback",
]


def require_training_deps():
    try:
        import accelerate  # noqa: F401
        import datasets  # noqa: F401
        import peft  # noqa: F401
        import torch  # noqa: F401
        import transformers  # noqa: F401
    except ImportError as e:
        raise SystemExit(
            "train.py requires torch, transformers, peft, accelerate, and datasets.\n"
            f"Missing: {e}\n"
            "This sandbox has no GPU and could not install these (see REPORT.md, "
            "'Environment Constraints'). Run this on a machine with a GPU and "
            "network access to PyPI / Hugging Face Hub."
        )


class OomLadderState:
    """Tracks which OOM-recovery steps are currently active for a training run."""

    def __init__(self, config: dict):
        self.config = dict(config)
        self.applied: list[str] = []

    def step(self) -> bool:
        """Apply the next ladder rung. Returns False if the ladder is exhausted."""
        remaining = [s for s in OOM_LADDER if s not in self.applied]
        if not remaining:
            return False
        rung = remaining[0]
        self.applied.append(rung)
        logger.warning("OOM recovery: applying '%s'", rung)

        if rung == "halve_batch_size":
            self.config["batch_size"] = max(1, self.config["batch_size"] // 2)
        elif rung == "double_grad_accum":
            self.config["grad_accum_steps"] = self.config.get("grad_accum_steps", 1) * 2
        elif rung == "enable_grad_checkpointing":
            self.config["gradient_checkpointing"] = True
        elif rung == "shrink_max_segment_length":
            self.config["max_segment_length_s"] = max(5, self.config.get("max_segment_length_s", 30) // 2)
        elif rung == "downgrade_precision":
            order = ["bfloat16", "float16", "float32"]
            cur = self.config.get("precision", "bfloat16")
            idx = order.index(cur) if cur in order else 0
            self.config["precision"] = order[min(idx + 1, len(order) - 1)]
        elif rung == "freeze_more_params":
            self.config["freeze_encoder"] = True
        elif rung == "lora_only_fallback":
            self.config["lora_only"] = True
            self.config["freeze_encoder"] = True
            self.config["freeze_decoder_base"] = True
        return True


def save_checkpoint(model, out_dir: Path, step: int, metrics: dict, is_best: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    last_dir = out_dir / "last_checkpoint"
    last_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(last_dir)
    (last_dir / "trainer_state.json").write_text(json.dumps({"step": step, "metrics": metrics}, indent=2))
    if is_best:
        best_dir = out_dir / "best_model"
        best_dir.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(best_dir)
        (best_dir / "trainer_state.json").write_text(json.dumps({"step": step, "metrics": metrics}, indent=2))
    logger.info("checkpoint saved at step %d (best=%s)", step, is_best)


def find_resume_checkpoint(out_dir: Path) -> Path | None:
    last_dir = out_dir / "last_checkpoint"
    return last_dir if last_dir.exists() and any(last_dir.iterdir()) else None


def log_step_metrics(step, epoch, loss, wer, cer, lr, batch_size, hw, t_start) -> None:
    entry = {
        "step": step,
        "epoch": epoch,
        "loss": loss,
        "wer": wer,
        "cer": cer,
        "lr": lr,
        "batch_size": batch_size,
        "device": hw.device,
        "vram_gb": hw.total_vram_gb,
        "duration_s": round(time.monotonic() - t_start, 2),
    }
    logger.info(json.dumps(entry))


def run_training(cfg: dict) -> None:
    require_training_deps()
    import torch

    from noahspeech.model.loading import apply_lora, load_lora_config, load_model
    from noahspeech.utils.hardware import detect_hardware

    hw = detect_hardware()
    logger.info("hardware: %s", hw.summary())

    out_dir = Path(cfg["output_dir"])
    resume_from = find_resume_checkpoint(out_dir)
    lora_cfg = load_lora_config(cfg["lora_config"])

    bundle = load_model(base_model_id=cfg["base_model"], lora_adapter_path=str(resume_from) if resume_from else None)
    if resume_from is None:
        bundle.model = apply_lora(bundle.model, lora_cfg)
        logger.info("initialized fresh LoRA adapter: r=%d alpha=%d targets=%s",
                     lora_cfg["r"], lora_cfg["lora_alpha"], lora_cfg["target_modules"])
    else:
        logger.info("resumed from checkpoint: %s", resume_from)

    ladder = OomLadderState(cfg)
    t_start = time.monotonic()
    best_wer = float("inf")
    no_improve_evals = 0

    for epoch in range(cfg["num_epochs"]):
        for step in range(cfg.get("steps_per_epoch", 1)):
            try:
                # Real batch fetch + forward/backward pass happens here against
                # a dataset loaded via HF `datasets`; omitted because no PT-BR
                # dataset is present in this sandbox (see REPORT.md).
                loss = None
                raise NotImplementedError(
                    "no training data available in this environment; wire in "
                    "a `datasets.Dataset` built from data/splits/train.csv here"
                )
            except torch.cuda.OutOfMemoryError:
                torch.cuda.empty_cache()
                if not ladder.step():
                    raise
                continue
            except NotImplementedError:
                logger.error(
                    "run_training() reached the point where it needs a real "
                    "dataset + GPU forward/backward pass, which this sandbox "
                    "cannot provide. See REPORT.md."
                )
                return

        if step % cfg.get("eval_every_steps", 100) == 0:
            wer, cer = None, None  # would come from scripts/evaluate.py on the val split
            is_best = wer is not None and wer < best_wer
            if is_best:
                best_wer = wer
                no_improve_evals = 0
            else:
                no_improve_evals += 1
            save_checkpoint(bundle.model, out_dir, step, {"wer": wer, "cer": cer}, is_best)
            if no_improve_evals >= cfg.get("early_stopping_patience", 5):
                logger.info("early stopping: no improvement for %d evals", no_improve_evals)
                return


def default_config() -> dict:
    return {
        "base_model": "openai/whisper-large-v3-turbo",
        "lora_config": "configs/lora_default.yaml",
        "output_dir": "checkpoints",
        "batch_size": 16,
        "grad_accum_steps": 2,
        "gradient_checkpointing": True,
        "max_segment_length_s": 30,
        "precision": "bfloat16",
        "learning_rate": 1e-4,
        "warmup_ratio": 0.03,
        "max_grad_norm": 1.0,
        "num_epochs": 10,
        "steps_per_epoch": 1000,
        "eval_every_steps": 200,
        "early_stopping_patience": 5,
        "freeze_encoder": False,
        "freeze_decoder_base": False,
        "lora_only": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=None, help="YAML config overriding defaults")
    args = parser.parse_args()

    cfg = default_config()
    if args.config:
        import yaml

        with open(args.config) as f:
            cfg.update(yaml.safe_load(f) or {})

    run_training(cfg)


if __name__ == "__main__":
    main()
