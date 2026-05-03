from __future__ import annotations

from skeinrank import build_attribute_profile
from skeinrank_provider_elasticsearch.enrichment import build_enrichment_payload


def test_elasticsearch_payload_supports_fuzzy_alias_fallback():
    profile = build_attribute_profile(
        profile_id="company_terms",
        aliases={"kubernetes": ["kubernetes", "k8s", "kube", "kuber"]},
        slots={"kubernetes": "TOOL"},
        snapshot_version="company_terms@v1",
    )

    payload = build_enrichment_payload(
        "kubernets timeout",
        profile=profile,
        enable_fuzzy=True,
        fuzzy_threshold=0.88,
        include_evidence=True,
    )

    assert payload["canonical_values"] == ["kubernetes"]
    assert payload["slots"] == {"TOOL": ["kubernetes"]}
    assert payload["attributes"][0]["source"] == "fuzzy_alias"
