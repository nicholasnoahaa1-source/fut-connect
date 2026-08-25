import pytest

from noahspeech.inference.pipeline import TranscriptionPipeline


def test_pipeline_without_model_raises_clear_error(tmp_wav_file):
    pipeline = TranscriptionPipeline(model_bundle=None)
    with pytest.raises(RuntimeError, match="no model_bundle"):
        pipeline.transcribe(tmp_wav_file)


def test_pipeline_audio_loading_stage_runs_without_model(tmp_wav_file):
    """Exercises the audio-load + VAD stages directly (the parts that don't
    need a model), confirming the pre-decode pipeline stages work end-to-end
    even without weights."""
    from noahspeech.audio.io import load_audio, normalize_peak
    from noahspeech.inference.vad import detect_speech_segments

    audio, sr = load_audio(tmp_wav_file)
    audio = normalize_peak(audio)
    segments = detect_speech_segments(audio, sr)
    assert isinstance(segments, list)
