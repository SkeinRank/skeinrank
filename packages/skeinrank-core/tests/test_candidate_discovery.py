from pathlib import Path

from skeinrank import (
    CandidateCluster,
    CandidateDiscoveryConfig,
    CandidateDiscoveryDocument,
    CandidateDiscoveryReport,
    CandidateTokenizerSignal,
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


def test_candidate_discovery_exposes_lightweight_surface_risk_without_tokenizer():
    report = discover_candidates(
        ["PAY-1842 PAY-1842 PAY-1842 server server server"],
        config={
            "min_frequency": 2,
            "min_word_length": 2,
            "include_phrase_candidates": False,
            "stop_words": [],
            "background_terms": ["server"],
        },
    )

    values = {candidate.normalized_value: candidate for candidate in report.candidates}
    breakdown = values["pay 1842"].score_breakdown

    assert breakdown is not None
    assert breakdown.surface_risk_score > 0
    assert breakdown.tokenizer_signal_status == "unavailable"
    assert breakdown.oov_score is None
    assert breakdown.token_fragmentation_score is None
    assert "alpha_digit_tokenizer_risk" in breakdown.reasons


class _FakeTokenizerSignalProvider:
    def analyze(self, surface: str):
        normalized = surface.casefold()
        if "pay" in normalized:
            return CandidateTokenizerSignal(
                token_count=1,
                subtoken_count=6,
                unknown_token_count=1,
                fragmentation_score=0.9,
                oov_score=0.85,
                reasons=["fake_provider_signal"],
            )
        return CandidateTokenizerSignal(
            token_count=1,
            subtoken_count=1,
            fragmentation_score=0.0,
            oov_score=0.0,
        )


def test_candidate_discovery_uses_optional_tokenizer_signal_provider():
    report = discover_candidates(
        ["PAY-1842 PAY-1842 server server"],
        config=CandidateDiscoveryConfig(
            min_frequency=2,
            min_word_length=2,
            include_phrase_candidates=False,
            stop_words=[],
            background_terms=["server"],
            tokenizer_signal_provider=_FakeTokenizerSignalProvider(),
        ),
    )

    values = {candidate.normalized_value: candidate for candidate in report.candidates}
    breakdown = values["pay 1842"].score_breakdown

    assert values["pay 1842"].score > values["server"].score
    assert breakdown is not None
    assert breakdown.tokenizer_signal_status == "available"
    assert breakdown.oov_score == 0.85
    assert breakdown.token_fragmentation_score == 0.9
    assert "fake_provider_signal" in breakdown.reasons
    assert "oov_tokenizer_signal" in breakdown.reasons


def test_candidate_discovery_classifies_code_style_surfaces():
    report = discover_candidates(
        [
            "PAY-1842 PAY-1842 checkout-v2 checkout-v2 payment_service payment_service",
            "PAY-1842 checkout-v2 payment_service",
        ],
        config=CandidateDiscoveryConfig(
            min_frequency=2,
            min_word_length=2,
            include_phrase_candidates=False,
            stop_words=[],
            background_terms=["checkout", "payment", "service"],
        ),
    )

    values = {candidate.normalized_value: candidate for candidate in report.candidates}

    assert values["pay 1842"].kind == "ticket_id"
    assert values["checkout v2"].kind == "versioned_name"
    assert values["payment service"].kind == "snake_case"
    assert values["pay 1842"].score_breakdown is not None
    assert values["pay 1842"].score_breakdown.surface_class == "ticket_id"
    assert "ticket_id_surface" in values["pay 1842"].score_breakdown.reasons
    assert "versioned_name_surface" in values["checkout v2"].score_breakdown.reasons
    assert "snake_case_surface" in values["payment service"].score_breakdown.reasons


def test_candidate_discovery_emits_trigram_phrase_candidates():
    report = discover_candidates(
        [
            "blue deploy ring failed during rollout. blue deploy ring recovered.",
            "runbook says blue deploy ring needs manual approval.",
        ],
        config=CandidateDiscoveryConfig(
            min_frequency=2,
            min_document_frequency=2,
            min_word_length=2,
            stop_words=["during", "says"],
        ),
    )

    values = {candidate.normalized_value: candidate for candidate in report.candidates}

    assert "blue deploy ring" in values
    assert values["blue deploy ring"].kind == "phrase"
    assert values["blue deploy ring"].document_count == 2
    assert values["blue deploy ring"].mention_count == 3


def test_candidate_discovery_builds_review_clusters():
    report = discover_candidates(
        [
            "blue deploy ring failed. blue deploy ring recovered. blue deploy failed.",
            "runbook says blue deploy ring uses blue deploy safeguards.",
        ],
        config=CandidateDiscoveryConfig(
            min_frequency=2,
            min_document_frequency=2,
            min_word_length=2,
            stop_words=["failed", "says", "uses"],
        ),
    )

    assert report.cluster_count == len(report.candidate_clusters)
    assert report.top_clusters(1) == report.candidate_clusters[:1]
    cluster = next(
        item
        for item in report.candidate_clusters
        if "blue deploy ring" in item.normalized_representative
        or "blue deploy ring" in item.surface_values
    )

    assert isinstance(cluster, CandidateCluster)
    assert cluster.candidate_count >= 2
    assert "blue deploy ring" in cluster.surface_values
    assert "blue deploy" in cluster.surface_values
    assert "related_surface_cluster" in cluster.reasons
    assert cluster.evidence


def test_candidate_discovery_skips_rst_directives_and_options():
    report = discover_candidates(
        [
            {
                "source": "docs/guide.rst",
                "text": (
                    ".. code-block:: python\n"
                    "   :header-rows: 1\n"
                    "\n"
                    "The DagProcessor coordinates DagRun state.\n"
                ),
            }
        ],
        config={
            "min_frequency": 1,
            "include_phrase_candidates": False,
            "min_word_length": 3,
        },
    )

    values = {candidate.normalized_value for candidate in report.candidates}
    assert "code block" not in values
    assert "header rows" not in values
    assert "dagprocessor" in values
    assert report.skipped_lines_by_reason == {
        "rst_directive": 1,
        "rst_option": 1,
    }
    assert report.skipped_line_count == 2


def test_candidate_discovery_filters_repeated_boilerplate_across_documents():
    license_line = (
        "WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied."
    )
    documents = [
        {
            "source": f"src/module_{index}.py",
            "text": f"{license_line}\n# DagProcessor{index} coordinates scheduler state.\n",
        }
        for index in range(1, 5)
    ]

    report = discover_candidates(
        documents,
        config={
            "min_frequency": 1,
            "include_phrase_candidates": False,
            "min_word_length": 3,
        },
    )

    values = {candidate.normalized_value for candidate in report.candidates}
    assert "warranties" not in values
    assert report.boilerplate_line_pattern_count == 1
    assert report.skipped_lines_by_reason["boilerplate"] == 4
    assert any(value.startswith("dagprocessor") for value in values)


def test_candidate_discovery_keeps_repeated_lines_in_small_corpora():
    shared = "The FluxCapacitor coordinates the TemporalRouter."
    report = discover_candidates(
        [
            {"source": "docs/a.md", "text": shared},
            {"source": "docs/b.md", "text": shared},
        ],
        config={
            "min_frequency": 2,
            "include_phrase_candidates": False,
            "min_word_length": 3,
        },
    )

    values = {candidate.normalized_value for candidate in report.candidates}
    assert "fluxcapacitor" in values
    assert report.boilerplate_line_pattern_count == 0
    assert report.skipped_line_count == 0


def test_candidate_discovery_context_signal_prefers_prose_and_code_support():
    report = discover_candidates(
        [
            {
                "source": "src/runtime.py",
                "text": (
                    "# FrozzleBundle is the exported runtime unit.\n"
                    "class FrozzleBundle:\n"
                    "    pass\n"
                    "class GrizzleBundle:\n"
                    "    pass\n"
                    "value = GrizzleBundle()\n"
                ),
            }
        ],
        config={
            "min_frequency": 2,
            "include_phrase_candidates": False,
            "min_word_length": 3,
        },
    )

    values = {candidate.normalized_value: candidate for candidate in report.candidates}
    mixed = values["frozzlebundle"]
    code_only = values["grizzlebundle"]

    assert mixed.score_breakdown is not None
    assert code_only.score_breakdown is not None
    assert mixed.score_breakdown.context_counts == {"code": 1, "comment": 1}
    assert mixed.score_breakdown.context_adjustment > 0
    assert code_only.score_breakdown.context_adjustment < 0
    assert mixed.score > code_only.score
    assert {item.context for item in mixed.evidence} == {"comment", "code"}
    assert report.line_context_version == "context-v2"
