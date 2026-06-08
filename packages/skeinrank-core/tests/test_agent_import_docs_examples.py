from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_ROOT = REPO_ROOT / "packages" / "skeinrank-core"
NEW_DOCS = [
    REPO_ROOT / "docs" / "guides" / "import-dictionary.md",
    REPO_ROOT / "docs" / "guides" / "agent-dictionary-assistant.md",
    REPO_ROOT / "examples" / "import-dictionary" / "README.md",
    REPO_ROOT / "examples" / "suggest-dictionary" / "README.md",
    REPO_ROOT / "examples" / "agent-dictionary-assistant" / "README.md",
]
EXAMPLE_SCRIPTS = [
    REPO_ROOT / "examples" / "import-dictionary" / "import_existing_dictionary.py",
    REPO_ROOT / "examples" / "suggest-dictionary" / "suggest_from_docs.py",
    REPO_ROOT / "examples" / "agent-dictionary-assistant" / "offline_assisted_demo.py",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_agent_import_docs_are_product_facing_and_discoverable() -> None:
    docs_index = _read(REPO_ROOT / "docs" / "README.md")
    root_readme = _read(REPO_ROOT / "README.md")
    core_readme = _read(CORE_ROOT / "README.md")

    for path in NEW_DOCS:
        assert path.exists(), f"missing documentation file: {path}"
        content = _read(path)
        assert "Patch" not in content
        assert "patch" not in content
        assert (
            "import-dictionary" in content
            or "suggest-dictionary" in content
            or "assist-dictionary" in content
        )

    assert "guides/import-dictionary.md" in docs_index
    assert "guides/agent-dictionary-assistant.md" in docs_index
    assert "docs/guides/import-dictionary.md" in root_readme
    assert "docs/guides/agent-dictionary-assistant.md" in root_readme
    assert "../../docs/guides/import-dictionary.md" in core_readme
    assert "../../docs/guides/agent-dictionary-assistant.md" in core_readme


def test_agent_import_docs_use_existing_cli_surfaces() -> None:
    combined = "\n".join(_read(path) for path in NEW_DOCS)
    cli = _read(CORE_ROOT / "skeinrank" / "cli.py")

    for command in (
        "import-dictionary",
        "suggest-dictionary",
        "assist-dictionary",
    ):
        assert command in combined
        assert command in cli

    for option in (
        "--draft-out",
        "--json-report",
        "--strict-validate",
        "--profile-name",
        "--min-frequency",
        "--model",
        "--review",
    ):
        assert option in combined
        assert option in cli

    assert "migrate-dictionary" not in combined
    assert "skeinrank-migrate import" not in combined


def test_agent_import_examples_exist_and_remain_offline_safe() -> None:
    for path in EXAMPLE_SCRIPTS:
        assert path.exists(), f"missing example script: {path}"
        content = _read(path)
        assert "Patch" not in content
        assert "patch" not in content
        assert "OpenRouter" not in content or "fake_openrouter_transport" in content

    offline_demo = _read(
        REPO_ROOT
        / "examples"
        / "agent-dictionary-assistant"
        / "offline_assisted_demo.py"
    )
    assert "fake_openrouter_transport" in offline_demo
    assert "build_dictionary_from_docs" in offline_demo


def test_agent_import_example_scripts_run_without_network() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(CORE_ROOT)
    for script in EXAMPLE_SCRIPTS:
        completed = subprocess.run(
            [sys.executable, str(script)],
            cwd=CORE_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        assert (
            "production" in (completed.stdout + completed.stderr).lower()
            or "Local preview" in completed.stdout
        )
