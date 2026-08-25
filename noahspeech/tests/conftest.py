import numpy as np
import pytest


@pytest.fixture
def sine_wave():
    """1s of 440Hz sine at 16kHz, float32 mono — a deterministic synthetic clip."""
    sr = 16000
    t = np.linspace(0, 1.0, sr, endpoint=False)
    return (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32), sr


@pytest.fixture
def silence():
    sr = 16000
    return np.zeros(sr, dtype=np.float32), sr


@pytest.fixture
def speech_like_signal():
    """Silence -> tone burst -> silence, to exercise VAD segment boundaries."""
    sr = 16000
    silence_a = np.zeros(int(0.5 * sr), dtype=np.float32)
    t = np.linspace(0, 1.0, sr, endpoint=False)
    tone = (0.5 * np.sin(2 * np.pi * 200 * t)).astype(np.float32)
    silence_b = np.zeros(int(0.5 * sr), dtype=np.float32)
    return np.concatenate([silence_a, tone, silence_b]), sr


@pytest.fixture
def tmp_wav_file(tmp_path, sine_wave):
    import soundfile as sf

    data, sr = sine_wave
    path = tmp_path / "test.wav"
    sf.write(path, data, sr)
    return str(path)
