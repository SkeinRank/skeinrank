import json
from pathlib import Path

from skeinrank import (
    CandidateDiscoveryConfig,
    DictionaryDraft,
    DictionarySuggestionConfig,
    DictionarySuggestionResult,
    expand_document_paths,
    suggest_dictionary,
    suggest_dictionary_from_documents,
)


def test_suggest_dictionary_returns_reviewable_draft_without_mutating_runtime():
    result = suggest_dictionary(
        [
            {"source": "incident-1.md", "text": "KubeletOOM after EdgeGateway deploy"},
            {"source": "incident-2.md", "text": "KubeletOOM returned on EdgeGateway"},
        ],
        config=DictionarySuggestionConfig(
            profile_name="platform_candidates",
            default_slot="PLATFORM_TERM",
            discovery=CandidateDiscoveryConfig(min_frequency=2, max_candidates=10),
        ),
    )

    assert isinstance(result, DictionarySuggestionResult)
    assert result.draft.profile_name == "platform_candidates"
    assert result.draft.source_format == "documents"
    assert result.draft.candidate_count >= 2
    assert result.draft.proposed_count == result.draft.candidate_count
    assert result.draft.accepted_count == 0
    assert any(
        candidate.canonical_value == "KubeletOOM"
        for candidate in result.draft.candidates
    )
    assert any(
        candidate.evidence and candidate.evidence[0].source == "incident-1.md"
        for candidate in result.draft.candidates
    )
    assert "No production state was changed" in result.review_markdown()


def test_suggest_dictionary_filters_existing_dictionary_terms():
    dictionary = {
        "profile_name": "known_terms",
        "terms": [
            {
                "canonical_value": "edge gateway",
                "slot": "SERVICE",
                "aliases": ["EdgeGateway"],
            }
        ],
    }

    result = suggest_dictionary(
        [
            "EdgeGateway emitted KubeletOOM during deploy",
            "EdgeGateway emitted KubeletOOM again",
        ],
        dictionary=dictionary,
        config={"discovery": {"min_frequency": 2, "max_candidates": 10}},
    )

    values = {
        candidate.canonical_value.casefold() for candidate in result.draft.candidates
    }
    assert "edgegateway" not in values
    assert "KubeletOOM" in {
        candidate.canonical_value for candidate in result.draft.candidates
    }


def test_suggest_dictionary_from_documents_expands_directories_and_saves(
    tmp_path: Path,
):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "incident-1.md").write_text("RedisEvict on EdgeGateway", encoding="utf-8")
    (docs / "incident-2.md").write_text("RedisEvict returned", encoding="utf-8")
    (docs / "ignore.bin").write_text("RedisEvict should not be read", encoding="utf-8")

    expanded = expand_document_paths([docs])
    assert [path.name for path in expanded] == ["incident-1.md", "incident-2.md"]

    result = suggest_dictionary_from_documents(
        [docs],
        config={
            "profile_name": "doc_candidates",
            "discovery": {"min_frequency": 2, "max_candidates": 5},
        },
    )
    out = tmp_path / "draft.json"
    result.save(out)

    loaded = DictionaryDraft.from_file(out)
    assert loaded.profile_name == "doc_candidates"
    assert any(
        candidate.canonical_value == "RedisEvict" for candidate in loaded.candidates
    )


def test_suggestion_draft_can_be_explicitly_converted_for_preview():
    result = suggest_dictionary(
        ["pg-bloat appeared", "pg-bloat appeared again"],
        config={"discovery": {"min_frequency": 2, "max_candidates": 5}},
    )
    accepted = result.draft.accept_all()
    dictionary = accepted.to_dictionary()

    assert dictionary.profile_name == "suggested_terms"
    assert dictionary.terms[0].canonical_value == "pg bloat"
    assert [alias.value for alias in dictionary.terms[0].aliases] == ["pg-bloat"]


def test_suggestion_json_payload_is_serializable():
    result = suggest_dictionary(
        ["HTTP500 appeared twice", "HTTP500 appeared again"],
        config={"discovery": {"min_frequency": 2, "max_candidates": 5}},
    )

    payload = result.draft.model_dump(mode="json", exclude_none=True)
    rendered = json.dumps(payload)
    assert "HTTP500" in rendered
    assert "suggestion.candidate_stats" in rendered
