#!/usr/bin/env python3
"""Prepare a PT-BR ASR dataset from a CSV of (audio_path,text) into a
train/val/test split, with a hard guarantee against test-set leakage.

Input CSV format: header `audio_path,text` (extra columns are preserved).
Output: {out_dir}/train.csv, val.csv, test.csv, plus split_manifest.json
recording the split sizes and the random seed used, for reproducibility.

Split is 90/5/5 by default, split at the *source audio file* level (dedup by
resolved absolute path before splitting) so the same recording never appears
in more than one split even if it's listed twice in the input.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path


def load_rows(csv_path: Path) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or "audio_path" not in reader.fieldnames or "text" not in reader.fieldnames:
            raise ValueError(f"{csv_path} must have 'audio_path' and 'text' columns; got {reader.fieldnames}")
        return list(reader)


def split_rows(rows: list[dict], train: float, val: float, test: float, seed: int) -> dict[str, list[dict]]:
    if abs(train + val + test - 1.0) > 1e-6:
        raise ValueError(f"split ratios must sum to 1.0, got {train}+{val}+{test}={train+val+test}")

    # dedup by resolved audio_path, keeping first occurrence, so leakage cannot
    # occur even if the same file is listed under different text rows.
    seen = set()
    unique_rows = []
    for row in rows:
        key = str(Path(row["audio_path"]).resolve())
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)

    rng = random.Random(seed)
    shuffled = unique_rows[:]
    rng.shuffle(shuffled)

    n = len(shuffled)
    n_train = int(n * train)
    n_val = int(n * val)

    return {
        "train": shuffled[:n_train],
        "val": shuffled[n_train : n_train + n_val],
        "test": shuffled[n_train + n_val :],
    }


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def assert_no_leakage(splits: dict[str, list[dict]]) -> None:
    paths_by_split = {
        name: {str(Path(r["audio_path"]).resolve()) for r in rows} for name, rows in splits.items()
    }
    for a in paths_by_split:
        for b in paths_by_split:
            if a >= b:
                continue
            overlap = paths_by_split[a] & paths_by_split[b]
            if overlap:
                raise AssertionError(f"leakage detected between '{a}' and '{b}': {overlap}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("--out-dir", type=Path, default=Path("data/splits"))
    parser.add_argument("--train", type=float, default=0.90)
    parser.add_argument("--val", type=float, default=0.05)
    parser.add_argument("--test", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rows = load_rows(args.input_csv)
    if not rows:
        raise SystemExit(f"{args.input_csv} contains no rows")

    fieldnames = list(rows[0].keys())
    splits = split_rows(rows, args.train, args.val, args.test, args.seed)
    assert_no_leakage(splits)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name, split_rows_ in splits.items():
        write_csv(args.out_dir / f"{name}.csv", split_rows_, fieldnames)

    manifest = {
        "input_csv": str(args.input_csv),
        "seed": args.seed,
        "ratios": {"train": args.train, "val": args.val, "test": args.test},
        "counts": {name: len(r) for name, r in splits.items()},
        "leakage_check": "passed",
    }
    (args.out_dir / "split_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
