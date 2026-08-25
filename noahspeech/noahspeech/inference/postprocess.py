"""Postprocessing: casing/punctuation normalization and PT-BR text cleanup
applied after decoding, before results are returned to callers."""

from __future__ import annotations

import re

_MULTI_SPACE = re.compile(r"\s+")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.!?;:])")


def clean_transcript(text: str) -> str:
    text = text.strip()
    text = _MULTI_SPACE.sub(" ", text)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    if text and text[0].islower():
        text = text[0].upper() + text[1:]
    return text


def merge_short_segments(segments: list[dict], min_duration_s: float = 1.0) -> list[dict]:
    """Merge adjacent segments shorter than min_duration_s into their neighbor,
    so downstream consumers (subtitles, UI) don't see noisy micro-segments."""
    if not segments:
        return []
    merged = [dict(segments[0])]
    for seg in segments[1:]:
        prev = merged[-1]
        if (prev["end"] - prev["start"]) < min_duration_s:
            prev["end"] = seg["end"]
            prev["text"] = (prev["text"].rstrip() + " " + seg["text"].lstrip()).strip()
            if "words" in prev and "words" in seg:
                prev["words"] = prev["words"] + seg["words"]
        else:
            merged.append(dict(seg))
    return merged
