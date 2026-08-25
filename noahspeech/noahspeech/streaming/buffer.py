"""Streaming session: mic/PCM buffering, VAD-gated chunking, partial + final
results for low-latency real-time transcription (WebSocket-driven, see api/).
"""

from __future__ import annotations

import dataclasses

import numpy as np

from noahspeech.audio.io import WHISPER_SAMPLE_RATE
from noahspeech.inference.vad import detect_speech_segments


@dataclasses.dataclass
class PartialResult:
    text: str
    is_final: bool
    chunk_start_s: float
    chunk_end_s: float


class StreamingSession:
    """Accumulates raw PCM chunks, emits a `PartialResult` (final=False) as soon
    as a rolling window is buffered and a `PartialResult` (final=True) whenever
    VAD detects a trailing silence gap that closes an utterance.

    `transcribe_fn` is injected so this class stays decoupled from the model
    (and is unit-testable without one): it must accept a numpy float32 array +
    sample_rate and return decoded text.
    """

    def __init__(
        self,
        transcribe_fn,
        sample_rate: int = WHISPER_SAMPLE_RATE,
        partial_window_s: float = 2.0,
        max_buffer_s: float = 30.0,
        silence_gap_s: float = 0.6,
    ):
        self.transcribe_fn = transcribe_fn
        self.sample_rate = sample_rate
        self.partial_window_s = partial_window_s
        self.max_buffer_s = max_buffer_s
        self.silence_gap_s = silence_gap_s
        self._buffer = np.zeros(0, dtype=np.float32)
        self._committed_s = 0.0
        self._samples_since_partial = 0

    def reset(self) -> None:
        self._buffer = np.zeros(0, dtype=np.float32)
        self._committed_s = 0.0
        self._samples_since_partial = 0

    def push_chunk(self, pcm: np.ndarray) -> list[PartialResult]:
        """Feed raw float32 mono PCM at self.sample_rate. Returns zero or more
        results produced by this chunk (partial and/or final)."""
        self._buffer = np.concatenate([self._buffer, pcm.astype(np.float32)])
        self._samples_since_partial += len(pcm)
        results: list[PartialResult] = []

        segments = detect_speech_segments(self._buffer, self.sample_rate)
        if segments:
            last = segments[-1]
            trailing_silence_s = (len(self._buffer) - last.end_sample) / self.sample_rate
            if trailing_silence_s >= self.silence_gap_s:
                chunk = self._buffer[: last.end_sample]
                text = self.transcribe_fn(chunk, self.sample_rate)
                results.append(
                    PartialResult(
                        text=text,
                        is_final=True,
                        chunk_start_s=self._committed_s,
                        chunk_end_s=self._committed_s + last.end_sample / self.sample_rate,
                    )
                )
                self._committed_s += last.end_sample / self.sample_rate
                self._buffer = self._buffer[last.end_sample :]
                self._samples_since_partial = 0
                return results

        window_samples = int(self.partial_window_s * self.sample_rate)
        if self._samples_since_partial >= window_samples and len(self._buffer) > 0:
            text = self.transcribe_fn(self._buffer, self.sample_rate)
            results.append(
                PartialResult(
                    text=text,
                    is_final=False,
                    chunk_start_s=self._committed_s,
                    chunk_end_s=self._committed_s + len(self._buffer) / self.sample_rate,
                )
            )
            self._samples_since_partial = 0

        max_samples = int(self.max_buffer_s * self.sample_rate)
        if len(self._buffer) > max_samples:
            overflow = len(self._buffer) - max_samples
            self._buffer = self._buffer[overflow:]
            self._committed_s += overflow / self.sample_rate

        return results
