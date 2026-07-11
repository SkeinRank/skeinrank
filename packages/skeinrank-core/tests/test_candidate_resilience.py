import pytest
from skeinrank import (
    Candidate,
    ContractError,
    InvalidCandidatePolicy,
    RerankEngine,
    rerank,
    rerank_many,
    score,
)


def _candidates_with_blank_text():
    return [
        Candidate(id="good", text="kubernetes incident response"),
        Candidate(id="blank", text="   "),
    ]


def test_strict_candidate_validation_remains_default():
    engine = RerankEngine()

    with pytest.raises(ContractError, match="candidate.text must be non-empty"):
        engine.rerank("incident", _candidates_with_blank_text())


def test_rerank_can_skip_only_empty_text_and_reports_it_without_passport():
    engine = RerankEngine()

    result = engine.rerank(
        "incident",
        _candidates_with_blank_text(),
        invalid_candidate_policy="skip_empty_text",
        passport="off",
    )

    assert result.passport is None
    assert [item.id for item in result.ranked] == ["good"]
    assert result.candidate_validation is not None
    assert result.candidate_validation.policy == InvalidCandidatePolicy.SKIP_EMPTY_TEXT
    assert result.candidate_validation.input_count == 2
    assert result.candidate_validation.accepted_count == 1
    assert result.candidate_validation.skipped_count == 1
    assert result.candidate_validation.skipped_by_reason == {"empty_text": 1}
    assert result.candidate_validation.skipped_candidates[0].id == "blank"
    assert result.candidate_validation.skipped_candidates[0].index == 1
    payload = result.model_dump(mode="json")
    assert payload["candidate_validation"]["skipped_count"] == 1


def test_skipped_candidate_is_also_visible_in_passport_warnings():
    result = rerank(
        "incident",
        _candidates_with_blank_text(),
        invalid_candidate_policy=InvalidCandidatePolicy.SKIP_EMPTY_TEXT,
        passport="summary",
    )

    assert result.passport is not None
    assert any(
        warning == "candidate_skipped: empty_text (id=blank, index=1)"
        for warning in result.passport.warnings
    )


def test_score_supports_the_same_candidate_validation_policy():
    result = score(
        "incident",
        _candidates_with_blank_text(),
        invalid_candidate_policy="skip_empty_text",
        passport="off",
    )

    assert set(result.scores) == {"good"}
    assert result.candidate_validation is not None
    assert result.candidate_validation.skipped_count == 1


def test_rerank_many_returns_validation_summary_per_request():
    results = rerank_many(
        [
            {
                "query": "incident",
                "candidates": [
                    {"id": "one", "text": "incident runbook"},
                    {"id": "empty-one", "text": ""},
                ],
            },
            {
                "query": "database",
                "candidates": [
                    {"id": "two", "text": "postgresql database"},
                    {"id": "empty-two", "text": "  "},
                ],
            },
        ],
        invalid_candidate_policy="skip_empty_text",
        warmup=False,
        passport="off",
    )

    assert len(results) == 2
    assert results[0].candidate_validation is not None
    assert results[0].candidate_validation.skipped_candidates[0].id == "empty-one"
    assert results[1].candidate_validation is not None
    assert results[1].candidate_validation.skipped_candidates[0].id == "empty-two"


def test_skip_policy_does_not_hide_other_contract_errors():
    engine = RerankEngine()

    with pytest.raises(ContractError, match="candidate.id must be non-empty"):
        engine.rerank(
            "incident",
            [{"id": "", "text": ""}],
            invalid_candidate_policy="skip_empty_text",
        )

    with pytest.raises(ContractError, match="invalid candidate at index 0"):
        engine.rerank(
            "incident",
            [{"id": "missing-text"}],
            invalid_candidate_policy="skip_empty_text",
        )

    with pytest.raises(ContractError, match="invalid candidate at index 0"):
        engine.rerank(
            "incident",
            [{"id": "none-text", "text": None}],
            invalid_candidate_policy="skip_empty_text",
        )


def test_all_candidates_skipped_is_still_an_error():
    engine = RerankEngine()

    with pytest.raises(
        ContractError,
        match="at least one candidate with non-empty text after validation",
    ):
        engine.rerank(
            "incident",
            [Candidate(id="blank", text="")],
            invalid_candidate_policy="skip_empty_text",
        )


def test_unknown_candidate_policy_is_rejected():
    engine = RerankEngine()

    with pytest.raises(ContractError, match="invalid_candidate_policy"):
        engine.rerank(
            "incident",
            [Candidate(id="good", text="incident")],
            invalid_candidate_policy="skip_everything",
        )
