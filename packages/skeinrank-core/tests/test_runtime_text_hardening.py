from __future__ import annotations

import json

from skeinrank import (
    UnicodeFindingKind,
    canonicalize_text,
    demo_dictionary,
    extract_terms,
    normalize_text_for_matching,
    validate_dictionary,
)
from skeinrank.cli import main


def _runtime_dictionary() -> dict[str, object]:
    return {
        "profile_name": "runtime_text_hardening",
        "terms": [
            {
                "canonical_value": "kubernetes",
                "slot": "TECHNOLOGY",
                "aliases": ["k8s"],
            },
            {
                "canonical_value": "access token",
                "slot": "SECURITY_CONCEPT",
                "aliases": [],
            },
        ],
    }


def test_unicode_normalizer_builds_spaced_and_compact_views() -> None:
    result = normalize_text_for_matching("ｋ\u200b８ｓ\u00a0access\u200btoken\u202e")

    assert result.normalized_text == "k 8s access token"
    assert result.compact_text == "k8s accesstoken"
    assert result.changed is True
    assert result.has_bidi_control is True
    assert [finding.kind for finding in result.findings] == [
        UnicodeFindingKind.COMPATIBILITY,
        UnicodeFindingKind.ZERO_WIDTH,
        UnicodeFindingKind.COMPATIBILITY,
        UnicodeFindingKind.COMPATIBILITY,
        UnicodeFindingKind.NON_ASCII_SPACE,
        UnicodeFindingKind.ZERO_WIDTH,
        UnicodeFindingKind.BIDI_CONTROL,
    ]
    assert result.original_span(0, 4) == (0, 4)
    assert result.original_span(0, 3, compact=True) == (0, 4)


def test_extract_terms_matches_unicode_aliases_with_original_offsets() -> None:
    text = "use ｋ８ｓ and k\u200b8s now"

    result = extract_terms(text, dictionary=_runtime_dictionary())

    assert result.canonical_values == ["kubernetes"]
    assert [match.matched_text for match in result.matches] == ["ｋ８ｓ", "k\u200b8s"]
    assert [text[match.start : match.end] for match in result.matches] == [
        "ｋ８ｓ",
        "k\u200b8s",
    ]
    assert result.unicode_normalized is True
    assert result.unicode_has_bidi_control is False
    assert {finding.kind for finding in result.unicode_findings} == {
        UnicodeFindingKind.COMPATIBILITY,
        UnicodeFindingKind.ZERO_WIDTH,
    }


def test_extract_terms_supports_spaced_and_compact_zero_width_views() -> None:
    text = "rotate access\u200btoken before using k\u200b8s"

    result = extract_terms(text, dictionary=_runtime_dictionary())

    assert [match.canonical_value for match in result.matches] == [
        "access token",
        "kubernetes",
    ]
    assert [match.matched_text for match in result.matches] == [
        "access\u200btoken",
        "k\u200b8s",
    ]


def test_canonicalize_text_replaces_obfuscated_alias_and_reports_bidi_risk() -> None:
    text = "run k8\u202es now"

    result = canonicalize_text(text, dictionary=_runtime_dictionary())

    assert result.text == "run kubernetes now"
    assert result.replacements[0].matched_text == "k8\u202es"
    assert result.replacements[0].start == 4
    assert result.replacements[0].end == 8
    assert result.unicode_normalized is True
    assert result.unicode_has_bidi_control is True
    assert result.unicode_findings[0].kind == UnicodeFindingKind.BIDI_CONTROL
    assert result.unicode_findings[0].risk == "high"


def test_canonicalize_text_reports_bidi_risk_even_without_a_term_match() -> None:
    text = "review unknown\u202etext"

    result = canonicalize_text(text, dictionary=_runtime_dictionary())

    assert result.text == text
    assert result.replacements == []
    assert result.unicode_has_bidi_control is True
    assert result.unicode_findings[0].risk == "high"


def test_validator_warns_when_replacement_can_break_prose_grammar() -> None:
    report = validate_dictionary(
        {
            "profile_name": "grammar_check",
            "terms": [
                {
                    "canonical_value": "deployment",
                    "slot": "CHANGE_TYPE",
                    "aliases": ["deploy", "rollout"],
                }
            ],
        }
    )

    assert report.ok is True
    assert report.error_count == 0
    assert report.warning_count == 1
    issue = report.issues[0]
    assert issue.code == "replacement_form_mismatch"
    assert issue.value == "deploy"
    assert issue.details == {
        "canonical_value": "deployment",
        "recommended_mode": "extract",
    }


def test_demo_dictionary_avoids_verb_alias_for_noun_replacement() -> None:
    dictionary = demo_dictionary()
    deployment = next(
        term for term in dictionary.terms if term.canonical_value == "deployment"
    )

    assert "deploy" not in {alias.value for alias in deployment.aliases}
    assert validate_dictionary(dictionary).warning_count == 0
    result = canonicalize_text("we deploy on k8s", dictionary=dictionary)
    assert result.text == "we deploy on kubernetes"


def test_cli_json_surfaces_unicode_findings(capsys) -> None:
    exit_code = main(["extract", "k\u200b8s", "--text", "--compact"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["canonical_values"] == ["kubernetes"]
    assert payload["unicode_normalized"] is True
    assert payload["unicode_has_bidi_control"] is False
    assert payload["unicode_findings"][0]["kind"] == "zero_width"
