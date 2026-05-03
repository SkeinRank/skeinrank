import pytest
from skeinrank import build_attribute_profile, enrich_texts


def _company_profile():
    return build_attribute_profile(
        profile_id="company_terms",
        aliases={
            "kubernetes": ["k8s", "kube", "kuber"],
            "postgresql": ["pg", "postgres"],
        },
        slots={
            "kubernetes": "TOOL",
            "postgresql": "DB",
        },
        snapshot_version="company_terms@v1",
    )


def test_enrich_texts_accepts_strings_with_custom_profile():
    rows = enrich_texts(
        ["kuber timeout", "pg latency"],
        profile=_company_profile(),
    )

    assert [row["id"] for row in rows] == ["0", "1"]
    assert rows[0]["canonical_values"] == ["kubernetes"]
    assert rows[0]["slots"] == {"TOOL": ["kubernetes"]}
    assert rows[1]["canonical_values"] == ["postgresql"]
    assert rows[1]["slots"] == {"DB": ["postgresql"]}
    assert rows[0]["snapshot_version"] == "company_terms@v1"


def test_enrich_texts_accepts_dict_records_and_custom_field_names():
    rows = enrich_texts(
        [
            {"doc_id": "runbook-1", "body": "k8s timeout"},
            {"doc_id": "runbook-2", "body": "postgres backup"},
        ],
        profile=_company_profile(),
        id_field="doc_id",
        text_field="body",
        include_text=False,
    )

    assert rows[0]["id"] == "runbook-1"
    assert "text" not in rows[0]
    assert rows[0]["canonical_values"] == ["kubernetes"]
    assert rows[1]["canonical_values"] == ["postgresql"]


def test_enrich_texts_can_include_attributes_and_passport():
    rows = enrich_texts(
        [{"id": "doc-1", "text": "kuber on pg"}],
        profile=_company_profile(),
        include_attributes=True,
        include_passport=True,
    )

    row = rows[0]
    assert row["id"] == "doc-1"
    assert {item["value"] for item in row["attributes"]} == {
        "kubernetes",
        "postgresql",
    }
    assert row["passport"]["profile_id"] == "company_terms"
    assert "stage_status" not in row["passport"]


def test_enrich_texts_returns_empty_list_for_empty_input():
    assert enrich_texts([], profile=_company_profile()) == []


def test_enrich_texts_rejects_records_without_text_field():
    with pytest.raises(ValueError, match="missing text field"):
        enrich_texts([{"id": "doc-1", "body": "k8s"}], profile=_company_profile())
