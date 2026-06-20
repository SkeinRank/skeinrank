from pathlib import Path

from skeinrank import (
    CandidateDiscoveryConfig,
    CandidateDiscoveryDocument,
    CandidateDiscoveryReport,
    discover_candidates,
    discover_candidates_from_documents,
    load_dictionary,
)


def _dictionary_payload():
    return {
        "profile_name": "platform_ops",
        "terms": [
            {
                "canonical_value": "kubernetes",
                "slot": "TECHNOLOGY",
                "aliases": ["k8s", "kube"],
            },
            {
                "canonical_value": "postgresql",
                "slot": "DATABASE",
                "aliases": ["pg", "postgres"],
            },
        ],
    }


def test_candidate_discovery_public_api_finds_unmatched_terms_with_evidence():
    report = discover_candidates(
        [
            {
                "source": "incident-1.md",
                "text": "Kubelet OOM during deploy. Kubelet OOM restarted pods.",
            },
            {
                "source": "incident-2.md",
                "text": "Kubelet OOM also triggered HTTP500 from edge-gateway.",
            },
        ],
        dictionary=_dictionary_payload(),
        config=CandidateDiscoveryConfig(min_frequency=2),
    )

    assert isinstance(report, CandidateDiscoveryReport)
    values = {candidate.normalized_value: candidate for candidate in report.candidates}

    assert "kubelet" in values
    assert values["kubelet"].kind == "term"
    assert values["kubelet"].mention_count == 3
    assert values["kubelet"].document_count == 2
    assert values["kubelet"].evidence[0].source == "incident-1.md"
    assert "Kubelet OOM" in values["kubelet"].evidence[0].text

    assert "oom" in values
    assert values["oom"].kind == "acronym"
    assert values["oom"].score > values["kubelet"].score


def test_candidate_discovery_excludes_known_dictionary_aliases():
    dictionary = load_dictionary(_dictionary_payload())

    report = discover_candidates(
        ["k8s kube pg postgres Kubelet Kubelet pg-bloat pg-bloat"],
        dictionary=dictionary,
        config={"min_frequency": 1, "include_phrase_candidates": False},
    )

    normalized = {candidate.normalized_value for candidate in report.candidates}

    assert "k8s" not in normalized
    assert "kube" not in normalized
    assert "pg" not in normalized
    assert "postgres" not in normalized
    assert "kubelet" in normalized
    assert "pg bloat" in normalized


def test_candidate_discovery_can_emit_context_phrase_candidates():
    report = discover_candidates(
        [
            "pg bloat caused slow vacuum. pg bloat returned after migration.",
            "runbook mentions pg bloat and pg vacuum checks.",
        ],
        dictionary=_dictionary_payload(),
        config={"min_frequency": 2, "min_document_frequency": 2},
    )

    values = {candidate.normalized_value: candidate for candidate in report.candidates}

    assert "pg bloat" in values
    assert values["pg bloat"].kind == "phrase"
    assert values["pg bloat"].document_count == 2
    assert values["pg bloat"].mention_count == 3


def test_candidate_discovery_from_document_paths_uses_document_sources(tmp_path: Path):
    first = tmp_path / "incident-one.md"
    second = tmp_path / "incident-two.md"
    first.write_text("RedisEvict RedisEvict happened on edge-gateway", encoding="utf-8")
    second.write_text("RedisEvict also appeared in worker-pool logs", encoding="utf-8")

    report = discover_candidates_from_documents(
        [first, second],
        config={"min_frequency": 2, "min_document_frequency": 2},
    )

    candidate = next(
        item for item in report.candidates if item.normalized_value == "redisevict"
    )
    assert candidate.kind == "camel_case"
    assert candidate.document_count == 2
    assert candidate.evidence[0].source == str(first)


def test_candidate_discovery_config_filters_and_limits_candidates():
    report = discover_candidates(
        [
            CandidateDiscoveryDocument(
                source="doc.md",
                text="alphaTerm alphaTerm betaTerm betaTerm GammaID GammaID",
            )
        ],
        config=CandidateDiscoveryConfig(
            min_frequency=2,
            max_candidates=2,
            stop_words=["betaTerm"],
        ),
    )

    normalized = [candidate.normalized_value for candidate in report.candidates]

    assert "betaterm" not in normalized
    assert len(normalized) == 2
    assert report.top_candidates(1) == report.candidates[:1]
    assert report.top_candidates(0) == []


def test_candidate_discovery_scoring_prefers_jargon_over_background_language():
    report = discover_candidates(
        [
            "pcore pcore pcore server server server",
            "pcore pcore pcore server server server",
        ],
        config=CandidateDiscoveryConfig(
            min_frequency=2,
            min_word_length=2,
            include_phrase_candidates=False,
            stop_words=[],
            background_terms=["server"],
        ),
    )

    values = {candidate.normalized_value: candidate for candidate in report.candidates}

    assert values["pcore"].score > values["server"].score
    assert values["pcore"].score_breakdown is not None
    assert values["server"].score_breakdown is not None
    assert (
        values["pcore"].score_breakdown.jargon_score
        > values["server"].score_breakdown.jargon_score
    )
    assert values["server"].score_breakdown.background_penalty > 0
    assert "rare_against_background" in values["pcore"].score_breakdown.reasons


def test_candidate_discovery_score_breakdown_explains_code_shape_boost():
    report = discover_candidates(
        ["PAY-1842 PAY-1842 PAY-1842 payment payment payment"],
        config={
            "min_frequency": 2,
            "min_word_length": 2,
            "include_phrase_candidates": False,
            "stop_words": [],
            "background_terms": ["payment"],
        },
    )

    values = {candidate.normalized_value: candidate for candidate in report.candidates}

    assert values["pay 1842"].score > values["payment"].score
    assert values["pay 1842"].score_breakdown is not None
    assert values["pay 1842"].score_breakdown.code_shape_score > 0
    assert "mixed_alpha_digit" in values["pay 1842"].score_breakdown.reasons
