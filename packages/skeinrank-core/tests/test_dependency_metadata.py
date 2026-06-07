from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
LOCKFILE = ROOT / "poetry.lock"
README = ROOT / "README.md"


def test_core_install_metadata_keeps_zero_friction_sdk_lightweight() -> None:
    pyproject = PYPROJECT.read_text(encoding="utf-8")

    assert "keybert" not in pyproject.lower()
    assert "scikit-learn" not in pyproject.lower()
    assert "sentence-transformers" not in pyproject.lower()
    assert "gliner" not in pyproject.lower()
    assert "attribute-models" not in pyproject.lower()

    assert "transformers" not in pyproject.lower()
    assert "[tool.poetry.extras]" not in pyproject
    assert "pydantic" in pyproject


def test_core_lockfile_no_longer_exposes_legacy_attribute_model_extra() -> None:
    lockfile = LOCKFILE.read_text(encoding="utf-8")

    assert "attribute-models" not in lockfile
    assert 'name = "keybert"' not in lockfile
    assert 'name = "scikit-learn"' not in lockfile
    assert 'name = "sentence-transformers"' not in lockfile
    assert 'name = "transformers"' not in lockfile
    assert 'name = "torch"' not in lockfile
    assert 'name = "numpy"' not in lockfile
    assert 'name = "gliner"' not in lockfile


def test_core_readme_describes_lightweight_install_without_legacy_ml_extra() -> None:
    readme = README.read_text(encoding="utf-8")

    assert (
        "no Governance API, Elasticsearch, RabbitMQ, Celery, Docker, OpenRouter token, or ML dependencies are required"
        in readme
    )
    assert "no longer exposes heavyweight ML install extras" in readme
    assert "attribute-models" not in readme
    assert "KeyBERT" not in readme
