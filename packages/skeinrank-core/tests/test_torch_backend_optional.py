import pytest
from skeinrank import ModelUnavailable, RerankEngine


def test_torch_backend_missing_has_clear_error(monkeypatch):
    # Force-disable torch backend even if torch is installed in the environment.
    monkeypatch.setenv("SKEINRANK_FORCE_NO_TORCH", "1")

    with pytest.raises(ModelUnavailable) as e:
        _ = RerankEngine(profile="e5_fast_torch")

    msg = str(e.value).lower()
    assert "torch" in msg
