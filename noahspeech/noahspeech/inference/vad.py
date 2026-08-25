"""Voice activity detection: webrtcvad by default, with a pure-numpy energy-based
fallback so the pipeline degrades gracefully rather than requiring a native
dependency to run at all.
"""

from __future__ import annotations

import dataclasses

import numpy as np

from noahspeech.audio.io import WHISPER_SAMPLE_RATE


@dataclasses.dataclass
class SpeechSegment:
    start_sample: int
    end_sample: int
    sample_rate: int

    @property
    def start_s(self) -> float:
        return self.start_sample / self.sample_rate

    @property
    def end_s(self) -> float:
        return self.end_sample / self.sample_rate


def _energy_vad(
    audio: np.ndarray,
    sample_rate: int,
    frame_ms: int = 30,
    energy_threshold: float = 0.01,
    min_speech_ms: int = 200,
    min_silence_ms: int = 300,
) -> list[SpeechSegment]:
    frame_len = int(sample_rate * frame_ms / 1000)
    if frame_len <= 0 or len(audio) == 0:
        return []
    n_frames = len(audio) // frame_len
    voiced = np.zeros(n_frames, dtype=bool)
    for i in range(n_frames):
        frame = audio[i * frame_len : (i + 1) * frame_len]
        rms = np.sqrt(np.mean(frame.astype(np.float64) ** 2))
        voiced[i] = rms > energy_threshold

    min_speech_frames = max(1, min_speech_ms // frame_ms)
    min_silence_frames = max(1, min_silence_ms // frame_ms)

    segments: list[SpeechSegment] = []
    i = 0
    while i < n_frames:
        if voiced[i]:
            start = i
            j = i
            silence_run = 0
            while j < n_frames:
                if voiced[j]:
                    silence_run = 0
                else:
                    silence_run += 1
                    if silence_run >= min_silence_frames:
                        break
                j += 1
            end = min(j - silence_run + 1, n_frames) if silence_run >= min_silence_frames else j
            end = max(end, start + 1)
            if end - start >= min_speech_frames:
                segments.append(
                    SpeechSegment(start * frame_len, min(end * frame_len, len(audio)), sample_rate)
                )
            i = j + 1
        else:
            i += 1
    return segments


def detect_speech_segments(
    audio: np.ndarray,
    sample_rate: int = WHISPER_SAMPLE_RATE,
    aggressiveness: int = 2,
) -> list[SpeechSegment]:
    """Return speech segments in `audio`. Prefers webrtcvad (frame-level, robust
    to background noise); falls back to a simple energy-based VAD if
    webrtcvad isn't installed, since it's a compiled dependency that may not
    build in every environment.
    """
    try:
        import webrtcvad
    except ImportError:
        return _energy_vad(audio, sample_rate)

    if sample_rate not in (8000, 16000, 32000, 48000):
        raise ValueError(f"webrtcvad requires sample_rate in (8000,16000,32000,48000), got {sample_rate}")

    vad = webrtcvad.Vad(aggressiveness)
    frame_ms = 30
    frame_len = int(sample_rate * frame_ms / 1000)
    pcm16 = np.clip(audio * 32768, -32768, 32767).astype(np.int16)

    segments: list[SpeechSegment] = []
    n_frames = len(pcm16) // frame_len
    in_speech = False
    seg_start = 0
    for i in range(n_frames):
        frame_bytes = pcm16[i * frame_len : (i + 1) * frame_len].tobytes()
        is_speech = vad.is_speech(frame_bytes, sample_rate)
        if is_speech and not in_speech:
            in_speech = True
            seg_start = i * frame_len
        elif not is_speech and in_speech:
            in_speech = False
            segments.append(SpeechSegment(seg_start, i * frame_len, sample_rate))
    if in_speech:
        segments.append(SpeechSegment(seg_start, n_frames * frame_len, sample_rate))
    return segments
