import numpy as np

from noahspeech.streaming.buffer import StreamingSession


def test_final_result_on_silence_gap():
    calls = []

    def fake_transcribe(chunk, sr):
        calls.append(len(chunk))
        return "transcricao falsa"

    session = StreamingSession(fake_transcribe, sample_rate=16000, silence_gap_s=0.3, partial_window_s=100)

    sr = 16000
    t = np.linspace(0, 0.8, int(0.8 * sr), endpoint=False)
    speech = (0.5 * np.sin(2 * np.pi * 200 * t)).astype(np.float32)
    trailing_silence = np.zeros(int(0.5 * sr), dtype=np.float32)

    results = session.push_chunk(speech)
    assert all(r.is_final is False for r in results)  # not enough silence yet

    results = session.push_chunk(trailing_silence)
    finals = [r for r in results if r.is_final]
    assert len(finals) == 1
    assert finals[0].text == "transcricao falsa"


def test_reset_clears_buffer():
    session = StreamingSession(lambda c, sr: "x", sample_rate=16000)
    session.push_chunk(np.ones(1000, dtype=np.float32))
    session.reset()
    assert len(session._buffer) == 0


def test_max_buffer_trims_overflow():
    session = StreamingSession(lambda c, sr: "x", sample_rate=16000, max_buffer_s=0.1, partial_window_s=1000)
    session.push_chunk(np.zeros(16000, dtype=np.float32))  # 1s of silence, > 0.1s cap
    assert len(session._buffer) <= 1600 + 1  # trimmed to ~max_buffer_s
