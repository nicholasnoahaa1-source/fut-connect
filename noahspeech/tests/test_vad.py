from noahspeech.inference.vad import detect_speech_segments


def test_detects_speech_in_tone_burst(speech_like_signal):
    audio, sr = speech_like_signal
    segments = detect_speech_segments(audio, sr)
    assert len(segments) >= 1
    seg = segments[0]
    # tone burst starts around 0.5s and lasts 1s; allow generous tolerance
    # since VAD frame boundaries and both backends (webrtcvad/energy) differ.
    assert 0.0 <= seg.start_s <= 1.0
    assert seg.end_s > seg.start_s


def test_silence_yields_no_segments(silence):
    audio, sr = silence
    segments = detect_speech_segments(audio, sr)
    assert segments == []


def test_segment_properties_consistent(speech_like_signal):
    audio, sr = speech_like_signal
    for seg in detect_speech_segments(audio, sr):
        assert seg.sample_rate == sr
        assert seg.end_sample > seg.start_sample
        assert seg.end_s > seg.start_s
