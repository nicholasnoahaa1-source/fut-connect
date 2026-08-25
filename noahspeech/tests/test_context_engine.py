from noahspeech.inference.context_engine import ContextEngineConfig, rescore_transcript


def test_rescore_corrects_near_miss():
    cfg = ContextEngineConfig(vocabulary=["Kubernetes"])
    text = "estamos usando Kubernets em producao"
    result = rescore_transcript(text, cfg)
    assert "Kubernetes" in result


def test_rescore_does_not_insert_unspoken_words():
    """Core safety property: a context word with no close match anywhere in
    the transcript must never be injected."""
    cfg = ContextEngineConfig(vocabulary=["Kubernetes"])
    text = "hoje o tempo esta bom"
    result = rescore_transcript(text, cfg)
    assert "Kubernetes" not in result
    assert result == text.strip()  # unchanged content-wise (clean_transcript not applied here)


def test_rescore_empty_vocabulary_is_noop():
    cfg = ContextEngineConfig(vocabulary=[])
    text = "qualquer coisa aqui"
    assert rescore_transcript(text, cfg) == text


def test_rescore_preserves_casing_style():
    cfg = ContextEngineConfig(vocabulary=["docker"])
    text = "usamos Dokcer para deploy"
    result = rescore_transcript(text, cfg)
    assert "Docker" in result
