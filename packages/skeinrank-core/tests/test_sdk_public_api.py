from pathlib import Path

import pytest
from skeinrank import (
    DRIFT_REPORT_SCHEMA_VERSION,
    BindingLagMetadata,
    CandidateDiscoveryConfig,
    CandidateDiscoveryDocument,
    CandidateDiscoveryReport,
    CandidateEvidence,
    CanonicalizedText,
    Dictionary,
    DictionaryAlias,
    DictionaryDraft,
    DictionaryStopListEntry,
    DictionarySuggestionConfig,
    DictionarySuggestionResult,
    DictionaryTerm,
    DictionaryValidationIssue,
    DictionaryValidationReport,
    DiscoveredCandidate,
    DraftCandidate,
    DraftFinding,
    DriftDraftConfig,
    DriftDraftResult,
    DriftEvidence,
    DriftFinding,
    DriftFindingType,
    DriftReportSummary,
    DriftScanConfig,
    DriftSeverity,
    EvidenceSnippet,
    ExtractionResult,
    OpenRouterAssistantError,
    OpenRouterDictionaryAssistantConfig,
    OpenRouterDictionaryAssistantResult,
    SkeinRank,
    TerminologyDriftReport,
    TermMatch,
    build_dictionary_from_docs,
    build_dictionary_from_documents,
    canonicalize,
    canonicalize_text,
    demo_dictionary,
    discover_candidates,
    discover_candidates_from_documents,
    drift_report_to_dictionary_draft,
    expand_document_paths,
    extract,
    extract_terms,
    import_dictionary,
    load_binding_metadata,
    load_dictionary,
    merge_binding_metadata,
    scan_dictionary_drift,
    scan_dictionary_drift_from_documents,
    suggest_dictionary,
    suggest_dictionary_from_documents,
    validate_dictionary,
    validate_imported_dictionary,
)


def _dictionary_payload():
    return {
        "profile_name": "infra_incidents",
        "profile_description": "Infra incident dictionary",
        "terms": [
            {
                "canonical_value": "kubernetes",
                "slot": "TOOL",
                "description": "Container orchestration platform",
                "tags": ["infra", "orchestration", "infra"],
                "aliases": [
                    "k8s",
                    {"value": "kube", "confidence": 0.95, "notes": "short form"},
                ],
            },
            {
                "canonical_value": "postgresql",
                "slot": "DATABASE",
                "aliases": ["postgres", "pg"],
            },
        ],
        "profile_stop_list": [
            {"value": "tmp", "target": "alias", "reason": "too generic"}
        ],
        "global_stop_list": [
            {"value": "unknown", "target": "both", "reason": "global noise"}
        ],
    }


def test_sdk_symbols_are_exported_from_public_api():
    assert CandidateDiscoveryConfig is not None
    assert CandidateDiscoveryDocument is not None
    assert CandidateDiscoveryReport is not None
    assert CandidateEvidence is not None
    assert DiscoveredCandidate is not None
    assert callable(discover_candidates)
    assert callable(discover_candidates_from_documents)
    assert Dictionary is not None
    assert DictionaryDraft is not None
    assert DraftCandidate is not None
    assert DraftFinding is not None
    assert EvidenceSnippet is not None
    assert DictionaryAlias is not None
    assert DictionaryTerm is not None
    assert DictionaryStopListEntry is not None
    assert DictionaryValidationIssue is not None
    assert DictionaryValidationReport is not None
    assert TermMatch is not None
    assert ExtractionResult is not None
    assert CanonicalizedText is not None
    assert callable(load_dictionary)
    assert callable(validate_dictionary)
    assert callable(extract_terms)
    assert callable(canonicalize_text)
    assert SkeinRank is not None
    assert callable(canonicalize)
    assert callable(extract)
    assert callable(demo_dictionary)
    assert OpenRouterAssistantError is not None
    assert OpenRouterDictionaryAssistantConfig is not None
    assert OpenRouterDictionaryAssistantResult is not None
    assert callable(build_dictionary_from_documents)
    assert callable(build_dictionary_from_docs)
    assert DictionarySuggestionConfig is not None
    assert DictionarySuggestionResult is not None
    assert callable(suggest_dictionary)
    assert callable(suggest_dictionary_from_documents)
    assert callable(expand_document_paths)
    assert callable(import_dictionary)
    assert callable(validate_imported_dictionary)
    assert TerminologyDriftReport is not None
    assert BindingLagMetadata is not None
    assert DriftScanConfig is not None
    assert DriftDraftConfig is not None
    assert DriftDraftResult is not None
    assert callable(drift_report_to_dictionary_draft)
    assert callable(load_binding_metadata)
    assert callable(merge_binding_metadata)
    assert callable(scan_dictionary_drift)
    assert callable(scan_dictionary_drift_from_documents)
    assert DriftFinding is not None
    assert DriftEvidence is not None
    assert DriftFindingType is not None
    assert DriftSeverity is not None
    assert DriftReportSummary is not None
    assert DRIFT_REPORT_SCHEMA_VERSION == "skeinrank.terminology_drift_report.v1"


def test_load_dictionary_from_console_migration_payload():
    dictionary = load_dictionary(_dictionary_payload())

    assert dictionary.profile_name == "infra_incidents"
    assert dictionary.terms[0].canonical_value == "kubernetes"
    assert dictionary.terms[0].tags == ["infra", "orchestration"]
    assert dictionary.terms[0].aliases[1].value == "kube"
    assert dictionary.terms[0].aliases[1].confidence == 0.95
    assert dictionary.terms[1].slot == "DATABASE"


def test_load_dictionary_from_file(tmp_path: Path):
    path = tmp_path / "dictionary.json"
    path.write_text(Dictionary.from_payload(_dictionary_payload()).model_dump_json())

    dictionary = load_dictionary(path)

    assert dictionary.profile_name == "infra_incidents"
    assert dictionary.terms[0].aliases[0].value == "k8s"


def test_extract_terms_returns_canonical_values_offsets_and_highlighted_evidence():
    dictionary = load_dictionary(_dictionary_payload())

    result = extract_terms(
        "This instruction helps deploy 500 k8s servers backed by Postgres.",
        dictionary=dictionary,
    )

    assert result.profile_name == "infra_incidents"
    assert result.canonical_values == ["kubernetes", "postgresql"]
    assert result.slots == ["TOOL", "DATABASE"]
    assert result.match_count == 2
    first = result.matches[0]
    assert first.alias == "k8s"
    assert first.canonical_value == "kubernetes"
    assert first.matched_text == "k8s"
    assert (
        first.fragment
        == "This instruction helps deploy 500 k8s servers backed by Postgres."
    )
    assert "<mark>k8s</mark>" in first.highlighted_fragment
    assert result.text[first.start : first.end] == "k8s"


def test_extract_terms_honors_stop_lists_and_non_runtime_statuses():
    payload = _dictionary_payload()
    payload["terms"].append(
        {
            "canonical_value": "temporary",
            "slot": "STATE",
            "aliases": ["tmp"],
        }
    )
    payload["terms"].append(
        {
            "canonical_value": "draft term",
            "slot": "STATE",
            "status": "pending",
            "aliases": ["drafty"],
        }
    )
    dictionary = load_dictionary(payload)

    result = extract_terms("tmp drafty k8s unknown", dictionary=dictionary)

    assert result.canonical_values == ["kubernetes"]
    assert result.matches[0].matched_text == "k8s"


def test_canonicalize_text_replaces_aliases_with_canonical_values():
    canonicalized = canonicalize_text(
        "k8s rollout uses pg database",
        dictionary=_dictionary_payload(),
    )

    assert canonicalized.text == "kubernetes rollout uses postgresql database"
    assert [item.alias for item in canonicalized.replacements] == ["k8s", "pg"]


def test_validate_dictionary_reports_alias_collisions_and_duplicates():
    payload = _dictionary_payload()
    payload["terms"].append(
        {"canonical_value": "kubernetes", "slot": "TOOL", "aliases": []}
    )
    payload["terms"].append(
        {"canonical_value": "containerd", "slot": "TOOL", "aliases": ["k8s"]}
    )

    report = validate_dictionary(payload)

    assert report.ok is False
    assert report.error_count == 2
    assert {issue.code for issue in report.issues} == {
        "alias_collision",
        "duplicate_canonical_value",
    }
    with pytest.raises(ValueError, match="Dictionary validation failed"):
        report.raise_for_errors()


def test_validate_dictionary_reports_parse_errors():
    report = validate_dictionary({"terms": "not-a-list"})

    assert report.ok is False
    assert report.error_count == 1
    assert report.issues[0].code == "invalid_dictionary"


def test_load_dictionary_keeps_schema_version():
    payload = _dictionary_payload()
    payload["schema_version"] = "skeinrank.dictionary.v1"

    dictionary = load_dictionary(payload)

    assert dictionary.schema_version == "skeinrank.dictionary.v1"


def test_load_dictionary_rejects_unsupported_schema_version():
    payload = _dictionary_payload()
    payload["schema_version"] = "skeinrank.dictionary.v999"

    with pytest.raises(ValueError, match="Unsupported dictionary schema_version"):
        load_dictionary(payload)


def test_load_dictionary_from_yaml_file(tmp_path: Path):
    pytest.importorskip("yaml")
    path = tmp_path / "dictionary.yaml"
    path.write_text(
        "schema_version: skeinrank.dictionary.v1\n"
        "profile_name: infra_incidents\n"
        "terms:\n"
        "  - canonical_value: kubernetes\n"
        "    slot: TOOL\n"
        "    aliases:\n"
        "      - k8s\n",
        encoding="utf-8",
    )

    dictionary = load_dictionary(path)

    assert dictionary.schema_version == "skeinrank.dictionary.v1"
    assert dictionary.profile_name == "infra_incidents"
    assert dictionary.terms[0].aliases[0].value == "k8s"
