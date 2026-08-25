# Checkpoint layout

`scripts/train.py` writes here:

```
checkpoints/
├── last_checkpoint/    # most recent step; auto-resumed on restart
│   ├── adapter_model.safetensors  (LoRA weights only)
│   ├── adapter_config.json
│   └── trainer_state.json         (step, loss, WER/CER at save time)
├── best_model/          # checkpoint with the lowest validation WER seen so far
│   └── ... (same layout)
├── quantized/           # output of scripts/quantize.py: fp32/, fp16/, bf16/, int8/
├── ctranslate2/         # output of scripts/export_ctranslate2.py
└── merged/              # LoRA-merged full weights (intermediate, for ctranslate2 export)
```

Nothing is committed here beyond `.gitkeep` — no training has been run in
this sandbox (no GPU, no dataset). See `REPORT.md`.
