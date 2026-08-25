import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest
import soundfile as sf
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent


def _write_wav(path: Path, duration_s: float = 1.0, sr: int = 16000, amplitude: float = 0.3):
    t = np.linspace(0, duration_s, int(duration_s * sr), endpoint=False)
    data = (amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    sf.write(path, data, sr)


@pytest.fixture
def dataset_csv(tmp_path):
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    rows = []
    for i in range(20):
        p = audio_dir / f"clip{i}.wav"
        _write_wav(p)
        rows.append({"audio_path": str(p), "text": f"frase numero {i}"})

    csv_path = tmp_path / "dataset.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["audio_path", "text"])
        writer.writeheader()
        writer.writerows(rows)
    return csv_path


def test_prepare_dataset_split_ratios_and_no_leakage(dataset_csv, tmp_path):
    from scripts.prepare_dataset import assert_no_leakage, load_rows, split_rows

    rows = load_rows(dataset_csv)
    splits = split_rows(rows, 0.90, 0.05, 0.05, seed=42)
    assert_no_leakage(splits)
    total = sum(len(v) for v in splits.values())
    assert total == len(rows)
    assert len(splits["train"]) >= len(splits["val"])
    assert len(splits["train"]) >= len(splits["test"])


def test_prepare_dataset_cli_runs(dataset_csv, tmp_path):
    out_dir = tmp_path / "splits"
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "prepare_dataset.py"), str(dataset_csv), "--out-dir", str(out_dir)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    manifest = json.loads((out_dir / "split_manifest.json").read_text())
    assert manifest["leakage_check"] == "passed"
    assert (out_dir / "train.csv").exists()
    assert (out_dir / "val.csv").exists()
    assert (out_dir / "test.csv").exists()


def test_split_rejects_bad_ratios():
    from scripts.prepare_dataset import split_rows

    with pytest.raises(ValueError):
        split_rows([{"audio_path": "a", "text": "b"}], 0.5, 0.3, 0.3, seed=0)


def test_clean_dataset_flags_issues(tmp_path):
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()

    good = audio_dir / "good.wav"
    _write_wav(good, duration_s=1.0, amplitude=0.3)

    silent = audio_dir / "silent.wav"
    _write_wav(silent, duration_s=1.0, amplitude=0.0)

    too_short = audio_dir / "short.wav"
    _write_wav(too_short, duration_s=0.05, amplitude=0.3)

    rows = [
        {"audio_path": str(good), "text": "texto valido"},
        {"audio_path": str(silent), "text": "silencio"},
        {"audio_path": str(too_short), "text": "curto demais"},
        {"audio_path": str(good), "text": "duplicado"},  # duplicate audio path
        {"audio_path": "/nonexistent.wav", "text": "arquivo corrompido"},
        {"audio_path": str(audio_dir / "empty_text.wav"), "text": ""},
    ]
    # write the "empty_text" audio so only the transcript is the failure mode
    _write_wav(audio_dir / "empty_text.wav", duration_s=1.0, amplitude=0.3)

    csv_path = tmp_path / "raw.csv"
    with open(csv_path, "w", newline="") as f:
        import csv as csv_mod

        writer = csv_mod.DictWriter(f, fieldnames=["audio_path", "text"])
        writer.writeheader()
        writer.writerows(rows)

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "clean_dataset.py"), str(csv_path)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["total_rows"] == 6
    assert summary["clean_rows"] == 1  # only "good" row passes every check
    assert "near_silent" in summary["issue_counts"]
    assert "duration_too_short" in summary["issue_counts"]
    assert "duplicate_audio_path" in summary["issue_counts"]
    assert "empty_transcript" in summary["issue_counts"]
    assert any("corrupt_audio" in k for k in summary["issue_counts"])
