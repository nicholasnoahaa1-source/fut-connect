from noahspeech.utils.hardware import detect_hardware


def test_detect_hardware_returns_valid_info():
    hw = detect_hardware()
    assert hw.device in ("cuda", "mps", "cpu")
    assert hw.cpu_count >= 1
    assert hw.recommended_dtype in ("bfloat16", "float16", "float32")


def test_detect_hardware_never_raises():
    # detect_hardware must degrade gracefully rather than raising, even
    # without a GPU or torch installed.
    hw = detect_hardware()
    assert isinstance(hw.summary(), str)


def test_no_gpu_in_this_sandbox():
    """Documents the actual, measured environment this suite ran in."""
    hw = detect_hardware()
    assert hw.device == "cpu"
    assert hw.cuda_available is False
