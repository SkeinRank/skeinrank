from __future__ import annotations

import json
import runpy
from pathlib import Path

import skeinrank
from skeinrank.cli import main

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLES_DIR = REPO_ROOT / "examples" / "sdk"
DEMO_DICTIONARY_JSON = EXAMPLES_DIR / "platform_ops_demo.dictionary.json"
DEMO_SCRIPT = EXAMPLES_DIR / "zero_friction_demo.py"
EXAMPLES_README = EXAMPLES_DIR / "README.md"


def test_builtin_demo_dictionary_is_compact_but_expressive() -> None:
    dictionary = skeinrank.demo_dictionary()
    aliases = [alias.value for term in dictionary.terms for alias in term.aliases]

    assert dictionary.profile_name == "platform_ops_demo"
    assert dictionary.validate().ok is True
    assert len(dictionary.terms) >= 30
    assert len(aliases) >= 80
    assert {term.canonical_value for term in dictionary.terms} >= {
        "kubernetes",
        "postgresql",
        "database migration",
        "github actions",
        "message queue",
        "page layout",
        "product group",
        "runtime snapshot",
        "ai inbox",
        "governance api",
    }


def test_builtin_demo_dictionary_supports_context_shaped_phrases() -> None:
    assert skeinrank.canonicalize("pg timeout") == "postgresql timeout"
    assert skeinrank.canonicalize("pg layout") == "page layout"
    assert skeinrank.canonicalize("pg dashboard") == "product group"
    assert skeinrank.canonicalize("sev1 on kube after pg migration") == (
        "critical incident on kubernetes after postgresql database migration"
    )
    assert skeinrank.extract("gha rollout hit rmq latency spike") == [
        "github actions",
        "deployment",
        "message queue",
        "latency",
    ]


def test_exported_demo_dictionary_example_matches_builtin_payload() -> None:
    exported = json.loads(DEMO_DICTIONARY_JSON.read_text(encoding="utf-8"))
    builtin = skeinrank.demo_dictionary_payload()

    assert exported == builtin
    assert (
        skeinrank.SkeinRank.from_file(DEMO_DICTIONARY_JSON).canonicalize(
            "api-server timed out after db migration"
        )
        == "api server timeout after database migration"
    )


def test_zero_friction_demo_script_runs(capsys) -> None:
    runpy.run_path(str(DEMO_SCRIPT), run_name="__main__")

    output = capsys.readouterr().out
    assert (
        "critical incident on kubernetes after postgresql database migration" in output
    )
    assert "pg layout   -> page layout" in output
    assert "pg dashboard -> product group" in output
    assert "api-server -> api server" in output


def test_examples_readme_mentions_real_commands_and_files() -> None:
    text = EXAMPLES_README.read_text(encoding="utf-8")

    assert "platform_ops_demo.dictionary.json" in text
    assert "zero_friction_demo.py" in text
    assert "skeinrank demo-dictionary" in text
    assert "skeinrank canonicalize" in text
    assert "Patch" not in text


def test_cli_can_print_builtin_demo_dictionary(capsys, tmp_path: Path) -> None:
    exit_code = main(["demo-dictionary", "--compact"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["profile_name"] == "platform_ops_demo"
    assert len(payload["terms"]) >= 30

    output_path = tmp_path / "demo.dictionary.json"
    exit_code = main(["demo-dictionary", "--output", str(output_path)])

    assert exit_code == 0
    assert output_path.exists()
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["profile_name"] == "platform_ops_demo"
