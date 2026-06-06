from __future__ import annotations

from pathlib import Path

from skeinrank_governance_api.dictionary_spec import load_mapping_document
from skeinrank_governance_api.schemas import ConsoleDictionaryPayload

REPO_ROOT = Path(__file__).resolve().parents[3]
DOC = REPO_ROOT / "docs/guides/terminology-as-code.md"
DOCS_README = REPO_ROOT / "docs/README.md"
ROOT_README = REPO_ROOT / "README.md"
API_DOC = REPO_ROOT / "docs/api/governance-api.md"
DICT_SPEC = REPO_ROOT / "docs/concepts/dictionary-spec-v1.md"
EXAMPLES_DIR = REPO_ROOT / "examples/terminology-as-code"
YAML_EXAMPLE = EXAMPLES_DIR / "platform_ops.dictionary.yaml"
JSON_EXAMPLE = EXAMPLES_DIR / "platform_ops.dictionary.json"
EXAMPLE_README = EXAMPLES_DIR / "README.md"
GOVERNANCE_API_README = REPO_ROOT / "packages/skeinrank-governance-api/README.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_terminology_as_code_docs_are_discoverable() -> None:
    root = _read(ROOT_README)
    docs = _read(DOCS_README)
    api = _read(API_DOC)
    spec = _read(DICT_SPEC)
    package_readme = _read(GOVERNANCE_API_README)

    assert DOC.exists()
    assert EXAMPLE_README.exists()
    assert "docs/guides/terminology-as-code.md" in root
    assert "examples/terminology-as-code" in root
    assert "guides/terminology-as-code.md" in docs
    assert "guides/dictionary-cli-planning.md" in docs
    assert "Terminology-as-Code import/export map" in api
    assert "../guides/terminology-as-code.md" in spec
    assert "docs/guides/terminology-as-code.md" in package_readme
    assert "docs/guides/dictionary-cli-planning.md" in package_readme
    assert "docs/deployment/gitops-delivery-runbook.md" in package_readme


def test_terminology_as_code_guide_uses_existing_cli_and_api_surfaces() -> None:
    doc = _read(DOC)

    expected_fragments = (
        "YAML outside, JSON inside.",
        "PostgreSQL is the control-plane source of truth",
        "schema_version: skeinrank.dictionary.v1",
        "skeinrank.runtime_snapshot_artifact.v1",
        "skeinrank-migrate validate",
        "skeinrank-migrate apply",
        "skeinrank-migrate export",
        "skeinrank-migrate snapshot-export",
        "skeinrank-migrate snapshot-inspect",
        "skeinrank-migrate snapshot-eval",
        "/v1/headless/dictionaries/validate",
        "/v1/headless/dictionaries/apply",
        "/v1/headless/dictionaries/export?profile_name=platform_ops",
        "/v1/headless/snapshots/export?binding_id=1",
        "skeinrank-migrate lint",
        "skeinrank-migrate plan --output plan.json",
        "skeinrank-migrate apply --plan-output applied-plan.json",
        "dictionary-cli-planning.md",
        "gitops-delivery-runbook.md",
    )
    for fragment in expected_fragments:
        assert fragment in doc

    # 60A must not document future command names as if they already exist.
    assert "skeinrank-cli apply" not in doc
    assert "skeinrank-cli lint" not in doc


def test_terminology_as_code_examples_are_valid_dictionary_spec_v1() -> None:
    assert YAML_EXAMPLE.exists()
    assert JSON_EXAMPLE.exists()

    yaml_payload = load_mapping_document(str(YAML_EXAMPLE))
    json_payload = load_mapping_document(str(JSON_EXAMPLE))

    assert yaml_payload["schema_version"] == "skeinrank.dictionary.v1"
    assert json_payload["schema_version"] == "skeinrank.dictionary.v1"
    assert (
        yaml_payload["profile_name"] == json_payload["profile_name"] == "platform_ops"
    )
    assert yaml_payload["terms"] == json_payload["terms"]
    assert yaml_payload["profile_stop_list"] == json_payload["profile_stop_list"]
    assert yaml_payload["global_stop_list"] == json_payload["global_stop_list"]

    yaml_model = ConsoleDictionaryPayload.model_validate(yaml_payload)
    json_model = ConsoleDictionaryPayload.model_validate(json_payload)

    assert yaml_model.profile_name == "platform_ops"
    assert json_model.profile_name == "platform_ops"
    assert [term.canonical_value for term in yaml_model.terms] == [
        "kubernetes",
        "postgresql",
    ]
    assert yaml_model.terms[0].tags == ["infra", "orchestration"]
    assert yaml_model.terms[1].tags == ["backend", "storage"]


def test_terminology_as_code_example_readme_keeps_current_commands() -> None:
    readme = _read(EXAMPLE_README)

    assert "poetry run skeinrank-migrate validate" in readme
    assert "platform_ops.dictionary.yaml" in readme
    assert "platform_ops.dictionary.json" in readme
    assert "skeinrank-cli" not in readme
