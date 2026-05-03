from __future__ import annotations

import json

from skeinrank import build_attribute_profile, enrich_texts, extract_attributes
from skeinrank.attributes.cli import extract_main


def _profile():
    return build_attribute_profile(
        profile_id="company_terms",
        aliases={
            "kubernetes": ["kubernetes", "k8s", "kube", "kuber"],
            "postgresql": ["postgresql", "postgres", "psql", "pg"],
        },
        slots={
            "kubernetes": "TOOL",
            "postgresql": "DB",
        },
        snapshot_version="company_terms@v1",
    )


def test_fuzzy_alias_fallback_is_disabled_by_default():
    pack = extract_attributes("kubernets timeout", profile=_profile())

    values = {item.value for item in pack.attributes}

    assert "kubernetes" not in values


def test_fuzzy_alias_fallback_finds_typo_when_enabled():
    pack = extract_attributes(
        "kubernets timeout",
        profile=_profile(),
        debug=True,
        enable_fuzzy=True,
        fuzzy_threshold=0.88,
    )

    attr = next(item for item in pack.attributes if item.value == "kubernetes")

    assert attr.source == "fuzzy_alias"
    assert attr.evidences[0].source == "fuzzy_alias"
    assert attr.evidences[0].matched_text == "kubernets"
    assert pack.passport is not None
    trace = next(item for item in pack.passport.accepted if item.value == "kubernetes")
    assert trace.reason == "fuzzy_match"
    assert trace.canonicalized_from == "kubernetes"


def test_fuzzy_alias_fallback_ignores_short_aliases():
    pack = extract_attributes(
        "px latency",
        profile=_profile(),
        enable_fuzzy=True,
        fuzzy_threshold=0.5,
    )

    assert {item.value for item in pack.attributes} == set()


def test_exact_alias_spans_are_not_reprocessed_as_fuzzy_candidates():
    pack = extract_attributes(
        "kubernetes issue",
        profile=_profile(),
        debug=True,
        enable_fuzzy=True,
        fuzzy_threshold=0.88,
    )

    assert pack.passport is not None
    kubernetes_traces = [
        item for item in pack.passport.proposed if item.value == "kubernetes"
    ]
    assert len(kubernetes_traces) == 1
    assert kubernetes_traces[0].source == "alias"


def test_extract_cli_supports_enable_fuzzy(tmp_path, capsys):
    profile_path = tmp_path / "company_terms.json"
    profile_path.write_text(json.dumps(_profile()), encoding="utf-8")

    exit_code = extract_main(
        [
            "--text",
            "kubernets timeout",
            "--profile-file",
            str(profile_path),
            "--enable-fuzzy",
            "--fuzzy-threshold",
            "0.88",
            "--compact",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert "kubernetes" in payload["canonical_values"]


def test_enrich_texts_supports_enable_fuzzy():
    rows = enrich_texts(
        [{"id": "doc-1", "text": "postgress latency"}],
        profile=_profile(),
        enable_fuzzy=True,
        fuzzy_threshold=0.87,
    )

    assert rows[0]["canonical_values"] == ["postgresql"]
    assert rows[0]["slots"] == {"DB": ["postgresql"]}
