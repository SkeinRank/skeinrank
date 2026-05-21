from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "examples/platform_ops_demo/seed_platform_demo.py"
DICTIONARY_PATH = REPO_ROOT / "examples/platform_ops_demo/platform_ops_dictionary.json"
BULK_PATH = REPO_ROOT / "examples/platform_ops_demo/platform_knowledge_base.ndjson"
README_PATH = REPO_ROOT / "examples/platform_ops_demo/README.md"
MAKEFILE_PATH = REPO_ROOT / "Makefile"
DOCKER_GUIDE_PATH = REPO_ROOT / "docs/deployment/docker-compose.md"
ROOT_README_PATH = REPO_ROOT / "README.md"


def _load_seed_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("platform_ops_demo_seed", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_platform_ops_demo_assets_exist_and_are_wired() -> None:
    assert SCRIPT_PATH.exists()
    assert DICTIONARY_PATH.exists()
    assert BULK_PATH.exists()
    assert README_PATH.exists()
    assert MAKEFILE_PATH.exists()

    makefile = MAKEFILE_PATH.read_text(encoding="utf-8")
    assert "demo-seed:" in makefile
    assert "demo-reset:" in makefile
    assert "demo-status:" in makefile
    assert "examples/platform_ops_demo/seed_platform_demo.py" in makefile


def test_platform_ops_dictionary_matches_preview_dataset_shape() -> None:
    payload = json.loads(DICTIONARY_PATH.read_text(encoding="utf-8"))
    assert payload["profile_name"] == "platform_ops"
    assert len(payload["terms"]) == 15
    assert sum(len(term.get("aliases", [])) for term in payload["terms"]) == 29
    assert len(payload["profile_stop_list"]) == 2
    assert len(payload["global_stop_list"]) == 2

    canonical_values = {term["canonical_value"] for term in payload["terms"]}
    assert {"kubernetes", "postgresql", "project phoenix"} <= canonical_values


def test_platform_ops_bulk_file_is_valid_ndjson_pairs() -> None:
    lines = [
        line for line in BULK_PATH.read_text(encoding="utf-8").splitlines() if line
    ]
    assert len(lines) == 48

    for index in range(0, len(lines), 2):
        action = json.loads(lines[index])
        document = json.loads(lines[index + 1])
        assert action["index"]["_index"] == "platform_knowledge_base"
        assert document["title"]
        assert document["body"]
        assert document["updated_at"]


def test_seed_script_helpers_are_safe_and_deterministic() -> None:
    module = _load_seed_module()

    assert module.is_local_url("http://127.0.0.1:8010")
    assert module.is_local_url("http://localhost:8010")
    assert not module.is_local_url("https://example.com")

    dictionary = module.load_json_file(DICTIONARY_PATH)
    assert module.dictionary_summary(dictionary) == {
        "terms": 15,
        "aliases": 29,
        "profile_stop_list": 2,
        "global_stop_list": 2,
    }
    assert module.count_bulk_documents(BULK_PATH) == 24

    binding = module.build_binding_payload()
    assert binding["profile_name"] == "platform_ops"
    assert binding["index_name"] == "platform_knowledge_base"
    assert binding["write_strategy"] == "reindex_alias_swap"
    assert binding["filter_field"] == "team"
    assert binding["filter_value"] == "platform"


def test_seed_script_selects_existing_binding_and_suggestion() -> None:
    module = _load_seed_module()

    binding = module.find_existing_binding(
        [
            {
                "id": 1,
                "name": "Other binding",
                "profile_name": "platform_ops",
                "index_name": "platform_knowledge_base",
            },
            {
                "id": 2,
                "name": "Production knowledge base",
                "profile_name": "platform_ops",
                "index_name": "platform_knowledge_base",
            },
        ]
    )
    assert binding["id"] == 2

    suggestion = module.find_existing_suggestion(
        [
            {
                "id": 10,
                "status": "pending",
                "canonical_value": "kubernetes",
                "alias_value": "EKS",
            }
        ],
        canonical_value="Kubernetes",
        alias_value="eks",
    )
    assert suggestion["id"] == 10


def test_demo_seed_docs_are_discoverable_from_primary_guides() -> None:
    root_readme = ROOT_README_PATH.read_text(encoding="utf-8")
    docker_guide = DOCKER_GUIDE_PATH.read_text(encoding="utf-8")
    demo_readme = README_PATH.read_text(encoding="utf-8")

    for content in (root_readme, docker_guide, demo_readme):
        assert "make demo-reset" in content
        assert "platform_ops" in content
        assert "platform_knowledge_base" in content

    assert "k8s pg timeout during phoenix rollout" in demo_readme
    assert "examples/platform_ops_demo/seed_platform_demo.py" in docker_guide
