import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

from fastapi.testclient import TestClient

from api.app import app

client = TestClient(app)


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["device"] in ("cuda", "mps", "cpu")


def test_models_endpoint_lists_variants():
    resp = client.get("/models")
    assert resp.status_code == 200
    ids = [m["id"] for m in resp.json()["data"]]
    assert "noahspeech-1-base" in ids
    assert "noahspeech-1-nano" in ids
    assert "noahspeech-1-pro" in ids


def test_transcriptions_endpoint_with_unknown_model_returns_404(tmp_wav_file):
    with open(tmp_wav_file, "rb") as f:
        resp = client.post(
            "/v1/audio/transcriptions",
            files={"file": ("test.wav", f, "audio/wav")},
            data={"model": "not-a-real-model"},
        )
    assert resp.status_code == 404


def test_transcriptions_endpoint_no_model_weights_returns_503_or_success(tmp_wav_file):
    """In this sandbox no Whisper weights have been downloaded (no network to
    the Hub), so a real model load is expected to fail; the endpoint must
    surface that as a clean 503, not a 500 crash. If weights ever ARE cached
    locally this simply exercises the success path instead."""
    with open(tmp_wav_file, "rb") as f:
        resp = client.post(
            "/v1/audio/transcriptions",
            files={"file": ("test.wav", f, "audio/wav")},
            data={"model": "noahspeech-1-base", "language": "pt"},
        )
    assert resp.status_code in (200, 503)
