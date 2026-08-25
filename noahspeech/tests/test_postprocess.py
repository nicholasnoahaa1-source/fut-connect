from noahspeech.inference.postprocess import clean_transcript, merge_short_segments


def test_clean_transcript_capitalizes_and_collapses_spaces():
    assert clean_transcript("  ola   mundo  ") == "Ola mundo"


def test_clean_transcript_fixes_space_before_punct():
    assert clean_transcript("ola mundo , tudo bem ?") == "Ola mundo, tudo bem?"


def test_merge_short_segments_combines_adjacent():
    segments = [
        {"text": "oi", "start": 0.0, "end": 0.3},
        {"text": "tudo bem", "start": 0.3, "end": 1.8},
    ]
    merged = merge_short_segments(segments, min_duration_s=1.0)
    assert len(merged) == 1
    assert merged[0]["text"] == "oi tudo bem"


def test_merge_short_segments_leaves_long_ones(monkeypatch=None):
    segments = [
        {"text": "primeiro segmento longo", "start": 0.0, "end": 2.0},
        {"text": "segundo segmento longo", "start": 2.0, "end": 4.0},
    ]
    merged = merge_short_segments(segments, min_duration_s=1.0)
    assert len(merged) == 2


def test_merge_short_segments_empty():
    assert merge_short_segments([]) == []
