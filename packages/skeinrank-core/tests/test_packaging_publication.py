from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
PYPROJECT = ROOT / "pyproject.toml"


def _pyproject_text() -> str:
    return PYPROJECT.read_text(encoding="utf-8")


def test_core_package_metadata_is_ready_for_pypi():
    content = _pyproject_text()

    assert 'name = "skeinrank"' in content
    assert 'version = "0.15.0"' in content
    assert '"canonicalization"' in content
    assert '"documents"' in content
    assert 'license = "Apache-2.0"' in content
    assert 'readme = "README.md"' in content
    assert 'packages = [{ include = "skeinrank" }]' in content
    assert 'python = ">=3.10,<4.0"' in content
    assert '"Programming Language :: Python :: 3.10"' in content
    assert '"Development Status :: 3 - Alpha"' in content
    assert '"Topic :: Software Development :: Libraries :: Python Modules"' in content


def test_core_package_exposes_local_cli_without_heavy_platform_dependencies():
    content = _pyproject_text()

    assert 'skeinrank = "skeinrank.cli:entrypoint"' in content
    assert "fastapi" not in content
    assert "sqlalchemy" not in content
    assert "celery" not in content


def test_core_package_includes_runtime_data_and_typing_marker():
    content = _pyproject_text()

    assert "skeinrank/attributes/config/*.json" in content
    assert "skeinrank/py.typed" in content
    assert (ROOT / "skeinrank" / "py.typed").exists()


def test_manual_publish_workflow_is_testpypi_first_and_dry_run_by_default():
    workflow = REPO_ROOT / ".github" / "workflows" / "publish-skeinrank-core.yml"
    content = workflow.read_text(encoding="utf-8")

    assert "workflow_dispatch" in content
    assert "default: true" in content
    assert "repository-url: https://test.pypi.org/legacy/" in content
    assert "Publish to PyPI" in content
    assert "poetry build" in content
    assert "twine check dist/*" in content
    assert "Smoke-test built wheel" in content


def test_publishing_checklist_documents_testpypi_before_pypi():
    checklist = ROOT / "docs" / "PUBLISHING.md"
    content = checklist.read_text(encoding="utf-8")

    assert "Publish to TestPyPI first" in content
    assert "Install from TestPyPI" in content
    assert "Publish to PyPI" in content
    assert "Never publish directly to PyPI" in content
