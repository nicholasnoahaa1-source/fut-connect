"""Audio I/O: load wav/mp3/m4a/flac/ogg/webm, normalize, resample, convert to mono.

soundfile handles the container formats libsndfile supports natively (wav,
flac, ogg). Anything else (mp3, m4a, webm) is transcoded to wav via ffmpeg
through pydub first. Both are optional dependencies: their absence degrades
to a clear AudioLoadError rather than an import-time crash, so this module is
always importable even in a stripped-down environment.
"""

from __future__ import annotations

import io
import shutil
import subprocess

import numpy as np

WHISPER_SAMPLE_RATE = 16_000

_NATIVE_FORMATS = {"wav", "flac", "ogg"}
_FFMPEG_FORMATS = {"mp3", "m4a", "webm", "aac", "mp4", "opus"}


class AudioLoadError(RuntimeError):
    """Raised when audio cannot be decoded (bad format, corrupt file, missing codec)."""


def _ext(path: str) -> str:
    return path.rsplit(".", 1)[-1].lower() if "." in path else ""


def _decode_with_ffmpeg(raw: bytes) -> tuple[np.ndarray, int]:
    if shutil.which("ffmpeg") is None:
        raise AudioLoadError(
            "ffmpeg not found on PATH; required to decode mp3/m4a/webm/aac. "
            "Install ffmpeg or convert the file to wav/flac/ogg first."
        )
    try:
        proc = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-i", "pipe:0",
                "-f", "f32le", "-ac", "1", "-ar", str(WHISPER_SAMPLE_RATE),
                "pipe:1",
            ],
            input=raw,
            capture_output=True,
            check=True,
            timeout=120,
        )
    except subprocess.CalledProcessError as e:
        raise AudioLoadError(f"ffmpeg failed to decode audio: {e.stderr.decode(errors='replace')}") from e
    except subprocess.TimeoutExpired as e:
        raise AudioLoadError("ffmpeg decode timed out") from e
    pcm = np.frombuffer(proc.stdout, dtype=np.float32)
    return pcm, WHISPER_SAMPLE_RATE


def load_audio(path: str, target_sr: int = WHISPER_SAMPLE_RATE, mono: bool = True) -> tuple[np.ndarray, int]:
    """Load an audio file to a float32 numpy array at target_sr, mono by default.

    Raises AudioLoadError on missing/corrupt/unsupported files instead of
    letting a raw decoder exception leak out, so callers (API, CLI, dataset
    cleaning) get one predictable exception type to handle.
    """
    ext = _ext(path)

    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise AudioLoadError(f"could not read file '{path}': {e}") from e

    if len(raw) == 0:
        raise AudioLoadError(f"file '{path}' is empty")

    if ext in _NATIVE_FORMATS or ext == "":
        try:
            import soundfile as sf
        except ImportError as e:
            raise AudioLoadError("soundfile is not installed") from e
        try:
            data, sr = sf.read(io.BytesIO(raw), dtype="float32", always_2d=False)
        except Exception as e:  # soundfile raises its own LibsndfileError subclasses
            raise AudioLoadError(f"failed to decode '{path}': {e}") from e
        if mono:
            data = to_mono(data)
        if sr != target_sr:
            data = resample(data, sr, target_sr)
            sr = target_sr
        return data.astype(np.float32), sr

    if ext in _FFMPEG_FORMATS:
        data, sr = _decode_with_ffmpeg(raw)
        return data, sr

    raise AudioLoadError(f"unsupported audio format '.{ext}' for file '{path}'")


def to_mono(data: np.ndarray) -> np.ndarray:
    if data.ndim == 1:
        return data
    return data.mean(axis=1).astype(np.float32)


def resample(data: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Linear-interpolation resample. Adequate for ASR feature extraction;
    swap for a polyphase filter (e.g. scipy.signal.resample_poly) if audible
    quality matters more than throughput."""
    if orig_sr == target_sr:
        return data
    duration = len(data) / orig_sr
    n_target = int(round(duration * target_sr))
    if n_target <= 0:
        return np.zeros(0, dtype=np.float32)
    x_orig = np.linspace(0.0, duration, num=len(data), endpoint=False)
    x_target = np.linspace(0.0, duration, num=n_target, endpoint=False)
    return np.interp(x_target, x_orig, data).astype(np.float32)


def normalize_peak(data: np.ndarray, target_peak: float = 0.95) -> np.ndarray:
    peak = np.abs(data).max() if data.size else 0.0
    if peak == 0:
        return data
    return (data * (target_peak / peak)).astype(np.float32)


def write_wav(path: str, data: np.ndarray, sr: int = WHISPER_SAMPLE_RATE) -> None:
    import soundfile as sf

    sf.write(path, data, sr, subtype="PCM_16")
