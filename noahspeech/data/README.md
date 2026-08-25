# Dataset format

`scripts/prepare_dataset.py` expects a CSV with (at minimum) these columns:

```csv
audio_path,text
/data/raw/clip0001.wav,bom dia como posso ajudar
/data/raw/clip0002.wav,o resultado do jogo foi dois a um
```

- `audio_path`: path to an audio file (wav/mp3/m4a/flac/ogg/webm).
- `text`: ground-truth transcript, PT-BR orthography.
- Extra columns (speaker id, source, duration) are preserved through
  `prepare_dataset.py` and `clean_dataset.py` but not otherwise used.

## Pipeline

1. `scripts/clean_dataset.py raw.csv` — flags/removes corrupt audio, empty
   transcripts, invalid duration, duplicates, near-silence, abnormal volume.
   Produces `raw_clean.csv` + `raw_report.json`.
2. `scripts/prepare_dataset.py raw_clean.csv --out-dir data/splits` — 90/5/5
   train/val/test split, deduplicated by resolved audio path so no file can
   leak across splits. Produces `data/splits/{train,val,test}.csv` +
   `split_manifest.json`.

No PT-BR audio dataset is present in this repository or this sandbox — these
scripts are validated against small synthetic CSVs in `tests/`, not real
speech data. See `REPORT.md` for what to run once real data is available.
