import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parents[1]
PYPROJECT = ROOT / "pyproject.toml"


def _pyproject():
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def test_core_package_metadata_is_ready_for_pypi():
    pyproject = _pyproject()
    poetry = pyproject["tool"]["poetry"]

    assert poetry["name"] == "skeinrank"
    assert poetry["version"] == "0.0.15"
    assert "canonicalization" in poetry["keywords"]
    assert "documents" in poetry["keywords"]
    assert poetry["license"] == "Apache-2.0"
    assert poetry["readme"] == "README.md"
    assert poetry["packages"] == [{"include": "skeinrank"}]
    assert "Development Status :: 3 - Alpha" in poetry["classifiers"]
    assert (
        "Topic :: Software Development :: Libraries :: Python Modules"
        in poetry["classifiers"]
    )


def test_core_package_exposes_local_cli_without_heavy_platform_dependencies():
    pyproject = _pyproject()
    poetry = pyproject["tool"]["poetry"]

    assert poetry["scripts"]["skeinrank"] == "skeinrank.cli:entrypoint"
    assert "fastapi" not in poetry["dependencies"]
    assert "sqlalchemy" not in poetry["dependencies"]
    assert "celery" not in poetry["dependencies"]


def test_core_package_includes_runtime_data_and_typing_marker():
    pyproject = _pyproject()
    include_paths = {item["path"] for item in pyproject["tool"]["poetry"]["include"]}

    assert "skeinrank/attributes/config/*.json" in include_paths
    assert "skeinrank/py.typed" in include_paths
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
