from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / "packages" / "skeinrank-core"
DRIFT_GUIDE = ROOT / "docs" / "guides" / "terminology-drift-report.md"
DRIFT_EXAMPLE = ROOT / "examples" / "drift-scan" / "README.md"
DOCS_INDEX = ROOT / "docs" / "README.md"
ROOT_README = ROOT / "README.md"
CORE_README = CORE / "README.md"
CLI = CORE / "skeinrank" / "cli.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_terminology_drift_guide_is_product_facing_and_uses_real_commands() -> None:
    guide = _read(DRIFT_GUIDE)

    assert "# Terminology drift report" in guide
    assert "skeinrank drift export-draft" in guide
    assert "TerminologyDriftReport" in guide
    assert "Drift Monitor" not in guide
    assert "real-time monitor" in guide
    assert "does not call model providers" in guide
    assert "no automatic production proposal creation" in guide
    assert "migrate-dictionary" not in guide
    assert "Patch" not in guide


def test_drift_examples_are_discoverable_from_project_docs() -> None:
    docs_index = _read(DOCS_INDEX)
    root_readme = _read(ROOT_README)
    core_readme = _read(CORE_README)
    example = _read(DRIFT_EXAMPLE)

    assert "guides/terminology-drift-report.md" in docs_index
    assert "examples/drift-scan" in docs_index
    assert "docs/guides/terminology-drift-report.md" in root_readme
    assert "examples/drift-scan" in root_readme
    assert "../../docs/guides/terminology-drift-report.md" in core_readme
    assert "run_drift_scan.py" in example
    assert "export_drift_draft.py" in example
    assert "Patch" not in example


def test_drift_docs_reference_existing_cli_options() -> None:
    guide = _read(DRIFT_GUIDE)
    example = _read(DRIFT_EXAMPLE)
    cli = _read(CLI)

    for option in [
        "--dictionary",
        "--docs",
        "--binding-metadata",
        "--out",
        "--markdown",
        "--min-frequency",
        "--min-document-frequency",
        "--max-candidates",
        "--no-stale-terms",
        "--no-binding-lag",
        "--no-ambiguity-signals",
        "--review",
    ]:
        assert option in cli

    for command in [
        "skeinrank drift scan",
        "skeinrank drift export-draft",
    ]:
        assert command in guide
        assert command in example


def test_drift_example_scripts_keep_source_checkout_imports_inside_main() -> None:
    scripts = [
        ROOT / "examples" / "drift-scan" / "run_drift_scan.py",
        ROOT / "examples" / "drift-scan" / "export_drift_draft.py",
    ]

    for script in scripts:
        source = _read(script)
        main_index = source.index("def main()")
        assert "from skeinrank import" not in source[:main_index]
        assert "from skeinrank import" in source[main_index:]


def test_drift_example_scripts_run_without_network() -> None:
    scripts = [
        ROOT / "examples" / "drift-scan" / "run_drift_scan.py",
        ROOT / "examples" / "drift-scan" / "export_drift_draft.py",
    ]

    for script in scripts:
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=CORE,
            check=True,
            text=True,
            capture_output=True,
        )
        assert "OpenRouter" not in result.stderr
        assert "Traceback" not in result.stderr
        assert result.stdout.strip()

    scan_output = subprocess.run(
        [sys.executable, str(scripts[0])],
        cwd=CORE,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    assert "# Terminology drift report" in scan_output
    assert "alias_drift" in scan_output

    draft_output = subprocess.run(
        [sys.executable, str(scripts[1])],
        cwd=CORE,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    assert "Dictionary draft review" in draft_output
    assert "drift.alias_drift" in draft_output
