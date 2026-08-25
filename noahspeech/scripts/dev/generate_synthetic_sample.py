#!/usr/bin/env python3
"""Generate a small synthetic dataset manifest for exercising the dataset
pipeline (prepare_dataset.py / clean_dataset.py) end-to-end when no real
PT-BR speech corpus is available.

IMPORTANT: these are sine-tone + noise stand-ins, NOT real speech, and are
useless for training or evaluating an ASR model. They exist only to prove
the cleaning/splitting logic (corrupt file detection, duplicate detection,
near-silence, clipping, short duration, empty transcript, leakage-free
split) runs correctly against real audio files on disk.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 16000


def tone(freq: float, dur: float, amp: float = 0.3) -> np.ndarray:
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def main(out_dir: Path = Path("data/raw_sample")) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0)
    rows = []

    texts = [
        "Hoje eu fui jogar basquete.",
        "O trânsito estava terrível essa manhã.",
        "Vamos almoçar naquele restaurante nordestino.",
        "A reunião foi remarcada para sexta-feira.",
        "Está ventando muito forte no litoral.",
    ]
    for i, txt in enumerate(texts):
        audio = tone(200 + i * 40, 2.0) + 0.01 * rng.standard_normal(int(SR * 2.0)).astype(np.float32)
        path = out_dir / f"{i:06d}.wav"
        sf.write(path, audio, SR)
        rows.append({"audio_path": str(path), "text": txt})

    rows.append({"audio_path": str(out_dir / "000000.wav"), "text": "Texto duplicado do primeiro áudio."})
    rows.append({"audio_path": str(out_dir / "000001.wav"), "text": texts[0]})

    path = out_dir / "000006.wav"
    sf.write(path, tone(300, 1.5), SR)
    rows.append({"audio_path": str(path), "text": ""})

    path = out_dir / "000007.wav"
    sf.write(path, np.zeros(int(SR * 1.0), dtype=np.float32), SR)
    rows.append({"audio_path": str(path), "text": "Áudio quase silencioso de teste."})

    path = out_dir / "000008.wav"
    sf.write(path, tone(250, 0.1), SR)
    rows.append({"audio_path": str(path), "text": "Muito curto."})

    path = out_dir / "000009.wav"
    sf.write(path, np.clip(tone(220, 1.0, amp=2.0), -1.0, 1.0), SR)
    rows.append({"audio_path": str(path), "text": "Áudio com clipping de volume."})

    path = out_dir / "000010.wav"
    path.write_bytes(b"not a real wav file")
    rows.append({"audio_path": str(path), "text": "Arquivo de áudio corrompido."})

    manifest = out_dir / "manifest.csv"
    with open(manifest, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["audio_path", "text"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {len(rows)} rows to {manifest}")


if __name__ == "__main__":
    main()
