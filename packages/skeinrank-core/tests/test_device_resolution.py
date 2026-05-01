import pytest
from skeinrank.backends.device import resolve_device
from skeinrank.domain.errors import ModelUnavailable


def test_resolve_device_cpu():
    r = resolve_device(
        requested="cpu",
        device_preference=["cuda", "cpu"],
        cuda_available=False,
        strict_cuda=False,
    )
    assert r.resolved == "cpu"
    assert r.fallback is False


def test_resolve_device_cuda_available():
    r = resolve_device(
        requested="cuda",
        device_preference=["cuda", "cpu"],
        cuda_available=True,
        strict_cuda=True,
    )
    assert r.resolved == "cuda"
    assert r.fallback is False


def test_resolve_device_cuda_missing_strict_raises():
    with pytest.raises(ModelUnavailable):
        _ = resolve_device(
            requested="cuda",
            device_preference=["cuda", "cpu"],
            cuda_available=False,
            strict_cuda=True,
        )


def test_resolve_device_auto_prefers_cuda_then_cpu():
    r = resolve_device(
        requested="auto",
        device_preference=["cuda", "cpu"],
        cuda_available=False,
        strict_cuda=False,
    )
    assert r.resolved == "cpu"
    assert r.fallback is True
