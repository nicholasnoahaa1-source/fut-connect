#!/usr/bin/env python3
"""Validate and clean a dataset CSV (audio_path,text): flags corrupt audio,
empty transcripts, invalid/out-of-range duration, exact/near duplicates,
near-silent audio, and abnormal (clipping/too-quiet) volume.

Writes {out}_clean.csv (rows that passed all checks) and {out}_report.json
(per-row issue list + summary counts). Never mutates the input file.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from noahspeech.audio.io import AudioLoadError, load_audio


def text_hash(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def check_row(
    row: dict,
    min_duration_s: float,
    max_duration_s: float,
    silence_rms_threshold: float,
    clip_ratio_threshold: float,
) -> list[str]:
    issues = []
    text = row.get("text", "")
    if not text or not text.strip():
        issues.append("empty_transcript")

    audio_path = row.get("audio_path", "")
    try:
        audio, sr = load_audio(audio_path)
    except AudioLoadError as e:
        issues.append(f"corrupt_audio: {e}")
        return issues  # can't run further audio checks without decoded audio

    duration = len(audio) / sr
    if duration < min_duration_s:
        issues.append(f"duration_too_short ({duration:.2f}s < {min_duration_s}s)")
    if duration > max_duration_s:
        issues.append(f"duration_too_long ({duration:.2f}s > {max_duration_s}s)")

    if len(audio):
        rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
        if rms < silence_rms_threshold:
            issues.append(f"near_silent (rms={rms:.5f})")

        clip_ratio = float(np.mean(np.abs(audio) >= 0.999))
        if clip_ratio > clip_ratio_threshold:
            issues.append(f"abnormal_volume_clipping (ratio={clip_ratio:.4f})")

    return issues


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("--out-prefix", type=Path, default=None)
    parser.add_argument("--min-duration", type=float, default=0.5)
    parser.add_argument("--max-duration", type=float, default=30.0)
    parser.add_argument("--silence-rms-threshold", type=float, default=0.002)
    parser.add_argument("--clip-ratio-threshold", type=float, default=0.01)
    args = parser.parse_args()

    out_prefix = args.out_prefix or args.input_csv.with_suffix("")

    with open(args.input_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    seen_audio_paths: set[str] = set()
    seen_text_hashes: set[str] = set()
    clean_rows = []
    report = []

    for i, row in enumerate(rows):
        issues = check_row(
            row, args.min_duration, args.max_duration, args.silence_rms_threshold, args.clip_ratio_threshold
        )

        resolved_path = str(Path(row.get("audio_path", "")).resolve())
        if resolved_path in seen_audio_paths:
            issues.append("duplicate_audio_path")
        seen_audio_paths.add(resolved_path)

        h = text_hash(row.get("text", ""))
        if h in seen_text_hashes and row.get("text", "").strip():
            issues.append("duplicate_transcript_text")
        seen_text_hashes.add(h)

        report.append({"row": i, "audio_path": row.get("audio_path"), "issues": issues})
        if not issues:
            clean_rows.append(row)

    with open(f"{out_prefix}_clean.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(clean_rows)

    summary = {
        "total_rows": len(rows),
        "clean_rows": len(clean_rows),
        "rejected_rows": len(rows) - len(clean_rows),
        "issue_counts": {},
    }
    for entry in report:
        for issue in entry["issues"]:
            key = issue.split(":")[0].split(" (")[0]
            summary["issue_counts"][key] = summary["issue_counts"].get(key, 0) + 1

    with open(f"{out_prefix}_report.json", "w") as f:
        json.dump({"summary": summary, "rows": report}, f, indent=2)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
