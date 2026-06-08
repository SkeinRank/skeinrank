"""Bridge dictionary import reports to the public dictionary validator.

Dictionary import is candidate-oriented: it converts existing lists into a
reviewable local dictionary file. The bridge reuses the SDK validator so import
reports surface runtime-safety findings without duplicating validation logic.
"""

from __future__ import annotations

from collections.abc import Iterable

from skeinrank.sdk import Dictionary, validate_dictionary

from .models import ImportWarning, Severity

_RUNTIME_BLOCKING_CODES = frozenset(
    {
        "invalid_dictionary",
        "duplicate_canonical_value",
    }
)
_RISKY_SHORT_ALIAS_MAX_LENGTH = 2
_ALLOWED_SHORT_ALIASES = frozenset({"ai", "ml", "ui", "ux", "db", "id"})


def validate_imported_dictionary(
    dictionary: Dictionary,
    *,
    strict: bool = False,
    ignored_codes: Iterable[str] = (),
) -> list[ImportWarning]:
    """Return import-report findings from the public SDK dictionary validator.

    ``strict=False`` keeps import candidate generation review-friendly: validator
    errors are reported as warnings unless the issue makes the dictionary payload
    unusable. Callers that want a runtime-ready file can pass ``strict=True``.
    """

    ignored = set(ignored_codes)
    report = validate_dictionary(dictionary)
    findings: list[ImportWarning] = []

    for issue in report.issues:
        if issue.code in ignored:
            continue
        findings.append(_warning_from_validation_issue(issue, strict=strict))

    findings.extend(_short_alias_findings(dictionary))
    return findings


def _warning_from_validation_issue(issue: object, *, strict: bool) -> ImportWarning:
    code = getattr(issue, "code", "unknown")
    severity = getattr(issue, "severity", "warning")
    message = getattr(issue, "message", "Dictionary validation finding.")
    value = getattr(issue, "value", None)
    details = getattr(issue, "details", {}) or {}

    rendered = str(message)
    if value:
        rendered = f"{rendered} Value: {value}."
    if details:
        rendered = f"{rendered} Details: {details}."

    if strict and str(severity) == "error":
        mapped = Severity.FATAL
    elif code in _RUNTIME_BLOCKING_CODES:
        mapped = Severity.FATAL
    elif str(severity) == "error":
        mapped = Severity.WARN
    elif str(severity) == "warning":
        mapped = Severity.WARN
    else:
        mapped = Severity.INFO

    return ImportWarning(
        severity=mapped,
        code=f"validate.{code}",
        message=rendered,
        source="validate",
    )


def _short_alias_findings(dictionary: Dictionary) -> list[ImportWarning]:
    findings: list[ImportWarning] = []
    seen: set[str] = set()
    for term in dictionary.terms:
        for alias in term.aliases:
            normalized = " ".join(alias.value.casefold().split())
            if (
                len(normalized) <= _RISKY_SHORT_ALIAS_MAX_LENGTH
                and normalized not in _ALLOWED_SHORT_ALIASES
                and normalized not in seen
            ):
                seen.add(normalized)
                findings.append(
                    ImportWarning.warn(
                        code="validate.risky_short_alias",
                        message=(
                            f"Alias '{alias.value}' is very short and can create "
                            "false positives. Review its binding/context before "
                            "runtime use."
                        ),
                        source="validate",
                    )
                )
    return findings
