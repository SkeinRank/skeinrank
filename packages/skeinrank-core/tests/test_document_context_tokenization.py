from skeinrank import CandidateDiscoveryConfig, discover_candidates


def _values(report):
    return {candidate.normalized_value: candidate for candidate in report.candidates}


def _config(**overrides):
    values = {
        "min_frequency": 1,
        "min_word_length": 2,
        "max_candidates": 200,
    }
    values.update(overrides)
    return CandidateDiscoveryConfig(**values)


def test_markdown_code_blocks_are_weighted_as_code_without_hiding_real_terms():
    report = discover_candidates(
        [
            {
                "source": "docs/dags.md",
                "text": (
                    "AssetAlias is a project concept used by airflow.sdk.\n"
                    "\n"
                    "```python\n"
                    "catchup = False\n"
                    'start_date = pendulum.datetime(2025, 1, 1, tz="UTC")\n'
                    'AssetAlias("daily")\n'
                    "```\n"
                    "The new `airflow.sdk` package exposes AssetAlias.\n"
                ),
            }
        ],
        config=_config(),
    )

    values = _values(report)
    real_term = values["assetalias"]
    snippet_idiom = values["catchup false"]

    assert report.line_context_version == "context-v2"
    assert report.skipped_lines_by_reason["markdown_fence"] == 2
    assert real_term.score_breakdown is not None
    assert snippet_idiom.score_breakdown is not None
    assert real_term.score_breakdown.context_counts == {"code": 1, "prose": 2}
    assert real_term.score_breakdown.context_adjustment > 0
    assert snippet_idiom.score_breakdown.context_counts == {"code": 1}
    assert snippet_idiom.score_breakdown.context_adjustment < 0
    assert "code_only_context_penalty" in snippet_idiom.score_breakdown.reasons
    assert real_term.score > snippet_idiom.score


def test_markdown_tilde_fences_indented_blocks_and_inline_code_are_classified():
    report = discover_candidates(
        [
            {
                "source": "docs/examples.markdown",
                "text": (
                    "ProseConcept is documented for operators.\n"
                    "The `InlineAPI` helper is referenced here.\n"
                    "~~~~python\n"
                    "FenceOnlyAPI = True\n"
                    "~~~~\n"
                    "    IndentedOnlyAPI = True\n"
                ),
            }
        ],
        config=_config(include_phrase_candidates=False),
    )

    values = _values(report)
    assert values["proseconcept"].score_breakdown.context_counts == {"prose": 1}
    assert values["inlineapi"].score_breakdown.context_counts == {"code": 1}
    assert values["fenceonlyapi"].score_breakdown.context_counts == {"code": 1}
    assert values["indentedonlyapi"].score_breakdown.context_counts == {"code": 1}
    assert values["inlineapi"].evidence[0].context == "code"
    assert values["proseconcept"].evidence[0].context == "prose"


def test_rst_code_directives_and_literal_blocks_preserve_context_signals():
    report = discover_candidates(
        [
            {
                "source": "docs/storage.rst",
                "text": (
                    "ObjectStoragePath is a public project concept.\n"
                    "\n"
                    ".. code-block:: python\n"
                    "   :caption: Example\n"
                    "\n"
                    '   start_date = pendulum.datetime(2025, 1, 1, tz="UTC")\n'
                    '   ObjectStoragePath("s3://bucket/key")\n'
                    "\n"
                    "Another example::\n"
                    "\n"
                    "   catchup = False\n"
                    "\n"
                    "The ``ObjectStoragePath`` API remains supported.\n"
                    "\n"
                    ".. literalinclude:: storage_example.py\n"
                ),
            }
        ],
        config=_config(),
    )

    values = _values(report)
    real_term = values["objectstoragepath"]
    code_idiom = values["tz utc"]

    assert report.skipped_lines_by_reason["rst_directive"] == 2
    assert report.skipped_lines_by_reason["rst_option"] == 1
    assert real_term.score_breakdown.context_counts == {"code": 2, "prose": 1}
    assert real_term.score_breakdown.context_adjustment > 0
    assert code_idiom.score_breakdown.context_counts == {"code": 1}
    assert code_idiom.score_breakdown.context_adjustment < 0
    assert values["catchup false"].score_breakdown.context_counts == {"code": 1}


def test_apostrophes_do_not_create_token_fragments_or_cross_sentence_phrases():
    report = discover_candidates(
        [
            {
                "source": "docs/language.md",
                "text": (
                    "This doesn't work. It's fine. It won't break. "
                    "l'utilisateur arrive. Developers’ tools remain. "
                    "The C API exposes CPythonBridge."
                ),
            }
        ],
        config=_config(),
    )

    normalized = {candidate.normalized_value for candidate in report.candidates}
    forbidden = {
        "doesn t",
        "doesn t work",
        "it s",
        "won t",
        "it won t",
        "l utilisateur",
        "l utilisateur arrive",
        "fine it won",
        "break l utilisateur",
    }

    assert normalized.isdisjoint(forbidden)
    assert "c api" in normalized
    assert "cpythonbridge" in normalized


def test_code_only_context_penalty_can_be_disabled_with_context_weight():
    report = discover_candidates(
        [
            {
                "source": "docs/example.md",
                "text": "```python\nCodeOnlyConcept = True\n```",
            }
        ],
        config=_config(
            include_phrase_candidates=False,
            context_weight=0.0,
        ),
    )

    candidate = _values(report)["codeonlyconcept"]
    assert candidate.score_breakdown.context_score == -1.0
    assert candidate.score_breakdown.context_adjustment == 0.0
    assert candidate.score > 0
