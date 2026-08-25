import numpy as np
import pytest

from noahspeech.audio.io import AudioLoadError, load_audio, normalize_peak, resample, to_mono


def test_load_wav_roundtrip(tmp_wav_file, sine_wave):
    data, sr = load_audio(tmp_wav_file)
    orig, orig_sr = sine_wave
    assert sr == orig_sr
    assert len(data) == pytest.approx(len(orig), abs=2)
    assert data.dtype == np.float32


def test_load_missing_file_raises():
    with pytest.raises(AudioLoadError):
        load_audio("/nonexistent/path/file.wav")


def test_load_empty_file_raises(tmp_path):
    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    with pytest.raises(AudioLoadError):
        load_audio(str(empty))


def test_load_unsupported_extension_raises(tmp_path):
    bad = tmp_path / "file.xyz"
    bad.write_bytes(b"not audio")
    with pytest.raises(AudioLoadError):
        load_audio(str(bad))


def test_to_mono_stereo():
    stereo = np.ones((100, 2), dtype=np.float32)
    stereo[:, 1] = 0.5
    mono = to_mono(stereo)
    assert mono.shape == (100,)
    assert np.allclose(mono, 0.75)


def test_to_mono_already_mono():
    mono_in = np.array([1.0, 2.0], dtype=np.float32)
    assert np.array_equal(to_mono(mono_in), mono_in)


def test_resample_changes_length():
    data = np.random.rand(16000).astype(np.float32)
    resampled = resample(data, 16000, 8000)
    assert len(resampled) == pytest.approx(8000, abs=1)


def test_resample_noop_same_rate():
    data = np.random.rand(100).astype(np.float32)
    assert np.array_equal(resample(data, 16000, 16000), data)


def test_normalize_peak():
    data = np.array([0.1, -0.5, 0.2], dtype=np.float32)
    norm = normalize_peak(data, target_peak=1.0)
    assert np.abs(norm).max() == pytest.approx(1.0, abs=1e-5)


def test_normalize_peak_silence_is_noop():
    data = np.zeros(10, dtype=np.float32)
    assert np.array_equal(normalize_peak(data), data)
