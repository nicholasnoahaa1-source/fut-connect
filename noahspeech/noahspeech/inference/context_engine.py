"""Context engine: biases decoding toward a user-supplied vocabulary (names,
jargon, product names) without inventing words that were never spoken.

Two complementary mechanisms, both bias-only (never force insertion):

1. `build_logit_bias`: a token-level positive bias added to the logits of
   tokens that begin a word in the supplied list, applied as a
   `LogitsProcessor` during beam search / greedy decoding. This nudges the
   model toward those spellings when the acoustic evidence is ambiguous, but
   a word absent from the audio still loses to the (much larger) acoustic
   likelihood of silence/other content — bias, not injection.
2. `rescore_transcript`: a post-hoc fuzzy-matching correction pass that only
   fires when the decoder already produced a phonetically close near-miss
   (edit distance below a strict threshold) for a context word — it corrects
   spelling/casing of things the model already attempted to say, and never
   inserts a context word that has no close match anywhere in the output.
"""

from __future__ import annotations

import dataclasses
import re


@dataclasses.dataclass
class ContextEngineConfig:
    vocabulary: list[str]
    bias_weight: float = 2.0
    max_edit_distance_ratio: float = 0.4  # of the word's length, for rescoring


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        prev = cur
    return prev[-1]


def build_logit_bias(vocabulary: list[str], tokenizer, bias_weight: float = 2.0) -> dict[int, float]:
    """Map token id -> additive logit bias for tokens that start a context word.

    Requires a HF tokenizer (encode/convert methods); returns {} gracefully if
    the vocabulary is empty so callers can always call this unconditionally.
    """
    if not vocabulary:
        return {}
    bias: dict[int, float] = {}
    for word in vocabulary:
        for variant in (word, f" {word}", word.capitalize(), f" {word.capitalize()}"):
            try:
                ids = tokenizer.encode(variant, add_special_tokens=False)
            except Exception:
                continue
            if ids:
                bias[ids[0]] = max(bias.get(ids[0], 0.0), bias_weight)
    return bias


_WORD_RE = re.compile(r"[\wÀ-ÿ]+", re.UNICODE)


def rescore_transcript(text: str, config: ContextEngineConfig) -> str:
    """Replace near-miss words in `text` with the closest context vocabulary
    word, only when they're already phonetically/orthographically close —
    this never adds words the model didn't already attempt.
    """
    if not config.vocabulary:
        return text

    def _replace(match: re.Match) -> str:
        token = match.group(0)
        best_word, best_dist = None, None
        for cand in config.vocabulary:
            if abs(len(cand) - len(token)) > max(2, len(cand)):
                continue
            dist = _levenshtein(token.lower(), cand.lower())
            threshold = max(1, int(len(cand) * config.max_edit_distance_ratio))
            if dist <= threshold and (best_dist is None or dist < best_dist):
                best_word, best_dist = cand, dist
        if best_word is None or best_word.lower() == token.lower():
            return token
        # preserve original casing style (capitalized vs lowercase)
        if token[:1].isupper():
            return best_word[:1].upper() + best_word[1:]
        return best_word

    return _WORD_RE.sub(_replace, text)
