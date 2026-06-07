from __future__ import annotations

import json

import skeinrank
from skeinrank import CanonicalizedText, ExtractionResult, SkeinRank
from skeinrank.cli import main


def test_module_level_canonicalize_uses_demo_dictionary_by_default() -> None:
    assert skeinrank.canonicalize("k8s pg timeout") == ("kubernetes postgresql timeout")


def test_module_level_extract_returns_canonical_values_by_default() -> None:
    assert skeinrank.extract("sev1 on kube after deploy") == [
        "critical incident",
        "kubernetes",
        "deployment",
    ]


def test_module_level_extract_can_return_explainable_result() -> None:
    result = skeinrank.extract("k8s pg timeout", explain=True)

    assert isinstance(result, ExtractionResult)
    assert result.profile_name == "platform_ops_demo"
    assert result.canonical_values == ["kubernetes", "postgresql", "timeout"]
    assert result.matches[0].alias == "k8s"
    assert "<mark>k8s</mark>" in result.matches[0].highlighted_fragment


def test_facade_accepts_simple_python_mapping() -> None:
    sr = SkeinRank(
        {
            "kubernetes": ["k8s", "kube"],
            "postgresql": ["pg", "psql"],
        },
        profile_name="company_terms",
    )

    assert sr.extract("kube timeout on pg") == ["kubernetes", "postgresql"]
    assert sr.canonicalize("kube timeout on pg") == ("kubernetes timeout on postgresql")


def test_facade_accepts_simple_mapping_with_slots_tags_and_explainability() -> None:
    sr = SkeinRank(
        {
            "kubernetes": {
                "slot": "TECHNOLOGY",
                "tags": ["infra"],
                "aliases": ["k8s"],
            }
        }
    )

    result = sr.extract("k8s rollout", explain=True)
    canonicalized = sr.canonicalize("k8s rollout", explain=True)

    assert isinstance(result, ExtractionResult)
    assert result.slots == ["TECHNOLOGY"]
    assert isinstance(canonicalized, CanonicalizedText)
    assert canonicalized.text == "kubernetes rollout"


def test_demo_dictionary_is_fresh_and_valid() -> None:
    first = skeinrank.demo_dictionary()
    second = skeinrank.demo_dictionary()

    assert first is not second
    assert first.profile_name == "platform_ops_demo"
    assert first.validate().ok is True
    assert {term.canonical_value for term in first.terms} >= {
        "kubernetes",
        "postgresql",
        "critical incident",
    }


def test_cli_canonicalize_uses_demo_dictionary_when_dictionary_is_omitted(
    capsys,
) -> None:
    exit_code = main(["canonicalize", "k8s pg timeout", "--text"])

    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "kubernetes postgresql timeout"


def test_cli_extract_uses_demo_dictionary_when_dictionary_is_omitted(capsys) -> None:
    exit_code = main(["extract", "k8s pg timeout", "--text", "--compact"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["profile_name"] == "platform_ops_demo"
    assert payload["canonical_values"] == ["kubernetes", "postgresql", "timeout"]
