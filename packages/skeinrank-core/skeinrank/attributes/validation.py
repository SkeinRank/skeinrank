from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .alias_map import AliasEntry, expand_profile_aliases
from .profiles import AttributeProfilePayload, load_attribute_profile

IssueSeverity = Literal["error", "warning", "info"]

DEFAULT_GENERIC_ALIASES = frozenset(
    {
        "api",
        "app",
        "application",
        "component",
        "data",
        "error",
        "issue",
        "job",
        "node",
        "problem",
        "service",
        "system",
        "worker",
    }
)


class ProfileValidationIssue(BaseModel):
    severity: IssueSeverity
    code: str
    message: str
    alias: str | None = None
    canonical: str | None = None
    slot: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ProfileValidationReport(BaseModel):
    profile_id: str | None = None
    ok: bool
    error_count: int
    warning_count: int
    info_count: int
    issues: list[ProfileValidationIssue] = Field(default_factory=list)

    def raise_for_errors(self) -> None:
        if self.error_count:
            raise ValueError(
                f"Attribute profile validation failed with {self.error_count} error(s)"
            )


def _profile_payload(
    profile: str | Path | Mapping[str, Any],
) -> AttributeProfilePayload:
    if isinstance(profile, (str, Path)):
        return load_attribute_profile(profile)
    return dict(profile)


def _issue(
    issues: list[ProfileValidationIssue],
    *,
    severity: IssueSeverity,
    code: str,
    message: str,
    alias: str | None = None,
    canonical: str | None = None,
    slot: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    issues.append(
        ProfileValidationIssue(
            severity=severity,
            code=code,
            message=message,
            alias=alias,
            canonical=canonical,
            slot=slot,
            details=details or {},
        )
    )


def _check_grouped_alias_shapes(
    raw_aliases: Any, issues: list[ProfileValidationIssue]
) -> None:
    if not isinstance(raw_aliases, list):
        _issue(
            issues,
            severity="error",
            code="aliases_not_list",
            message="Profile field 'aliases' must be a list.",
            details={"type": type(raw_aliases).__name__},
        )
        return

    for index, item in enumerate(raw_aliases):
        if not isinstance(item, dict):
            _issue(
                issues,
                severity="error",
                code="alias_entry_not_object",
                message="Alias entries must be JSON objects.",
                details={"index": index, "type": type(item).__name__},
            )
            continue

        canonical = str(item.get("canonical", "")).strip() or None
        slot = str(item.get("slot", "")).strip() or None
        if "canonical" not in item:
            _issue(
                issues,
                severity="error",
                code="missing_canonical",
                message="Alias entry is missing required field 'canonical'.",
                details={"index": index},
            )
        if "slot" not in item:
            _issue(
                issues,
                severity="error",
                code="missing_slot",
                message="Alias entry is missing required field 'slot'.",
                canonical=canonical,
                details={"index": index},
            )

        if "alias" not in item and "aliases" not in item:
            _issue(
                issues,
                severity="error",
                code="missing_alias",
                message="Alias entry must define either 'alias' or 'aliases'.",
                canonical=canonical,
                slot=slot,
                details={"index": index},
            )
            continue

        if "aliases" in item:
            raw_values = item["aliases"]
            if raw_values == []:
                _issue(
                    issues,
                    severity="warning",
                    code="empty_alias_list",
                    message="Grouped alias entry has an empty aliases list.",
                    canonical=canonical,
                    slot=slot,
                    details={"index": index},
                )
            if not isinstance(raw_values, (list, str)):
                _issue(
                    issues,
                    severity="error",
                    code="invalid_aliases_type",
                    message="Grouped alias field 'aliases' must be a string or list.",
                    canonical=canonical,
                    slot=slot,
                    details={"index": index, "type": type(raw_values).__name__},
                )


def _validate_entries(
    entries: list[AliasEntry],
    issues: list[ProfileValidationIssue],
    *,
    generic_aliases: set[str],
    min_short_alias_length: int,
) -> None:
    by_alias: dict[str, list[AliasEntry]] = defaultdict(list)
    by_alias_canonical_slot: dict[tuple[str, str, str], int] = defaultdict(int)

    for entry in entries:
        normalized_alias = entry.normalized_alias
        normalized_canonical = entry.normalized_canonical
        slot = entry.slot.value
        if not normalized_alias:
            _issue(
                issues,
                severity="error",
                code="empty_alias",
                message="Alias value must not be empty after normalization.",
                canonical=normalized_canonical,
                slot=slot,
            )
            continue
        by_alias[normalized_alias].append(entry)
        by_alias_canonical_slot[(normalized_alias, normalized_canonical, slot)] += 1

        if normalized_alias in generic_aliases:
            _issue(
                issues,
                severity="warning",
                code="generic_alias",
                message=(
                    f"Alias '{normalized_alias}' is very generic and may degrade "
                    "search precision. Prefer a more specific phrase or scoped rule."
                ),
                alias=normalized_alias,
                canonical=normalized_canonical,
                slot=slot,
            )

        if (
            0 < len(normalized_alias) < min_short_alias_length
            and normalized_alias.replace("_", "").isalnum()
        ):
            _issue(
                issues,
                severity="warning",
                code="short_alias",
                message=(
                    f"Alias '{normalized_alias}' is short. Short aliases are useful "
                    "but should be reviewed for collisions and word-boundary behavior."
                ),
                alias=normalized_alias,
                canonical=normalized_canonical,
                slot=slot,
            )

    for (alias, canonical, slot), count in sorted(by_alias_canonical_slot.items()):
        if count > 1:
            _issue(
                issues,
                severity="warning",
                code="duplicate_alias",
                message=(
                    f"Alias '{alias}' is defined {count} times for canonical "
                    f"'{canonical}' in slot '{slot}'."
                ),
                alias=alias,
                canonical=canonical,
                slot=slot,
                details={"count": count},
            )

    for alias, alias_entries in sorted(by_alias.items()):
        targets = {
            (entry.normalized_canonical, entry.slot.value) for entry in alias_entries
        }
        if len(targets) <= 1:
            continue
        _issue(
            issues,
            severity="error",
            code="alias_collision",
            message=(
                f"Alias '{alias}' maps to multiple canonical terms. Split it into "
                "a scoped alias or mark it as ambiguous before publishing."
            ),
            alias=alias,
            details={
                "targets": [
                    {"canonical": canonical, "slot": slot}
                    for canonical, slot in sorted(targets)
                ]
            },
        )


def validate_attribute_profile(
    profile: str | Path | Mapping[str, Any],
    *,
    generic_aliases: set[str] | None = None,
    min_short_alias_length: int = 3,
) -> ProfileValidationReport:
    """Validate a terminology profile snapshot before runtime use.

    The validator is intentionally conservative: collisions are errors, while
    generic and short aliases are warnings. This protects retrieval quality
    without blocking useful short aliases such as ``pg`` by default.
    """
    issues: list[ProfileValidationIssue] = []
    generic_aliases = set(generic_aliases or DEFAULT_GENERIC_ALIASES)

    try:
        payload = _profile_payload(profile)
    except Exception as exc:  # noqa: BLE001 - validation should report bad inputs
        _issue(
            issues,
            severity="error",
            code="profile_load_error",
            message=str(exc),
        )
        return _report(None, issues)

    profile_id = payload.get("profile_id")
    if not isinstance(profile_id, str) or not profile_id.strip():
        _issue(
            issues,
            severity="error",
            code="missing_profile_id",
            message="Profile is missing non-empty field 'profile_id'.",
        )
        profile_id = None

    raw_aliases = payload.get("aliases")
    _check_grouped_alias_shapes(raw_aliases, issues)
    if not isinstance(raw_aliases, list):
        return _report(profile_id, issues)

    try:
        entries = expand_profile_aliases(raw_aliases)
    except Exception as exc:  # noqa: BLE001 - validation should report bad shapes
        _issue(
            issues,
            severity="error",
            code="alias_expansion_error",
            message=str(exc),
        )
        return _report(profile_id, issues)

    if not entries:
        _issue(
            issues,
            severity="error",
            code="no_alias_entries",
            message="Profile must contain at least one usable alias entry.",
        )
        return _report(profile_id, issues)

    _validate_entries(
        entries,
        issues,
        generic_aliases=generic_aliases,
        min_short_alias_length=min_short_alias_length,
    )
    return _report(profile_id, issues)


def _report(
    profile_id: Any, issues: list[ProfileValidationIssue]
) -> ProfileValidationReport:
    error_count = sum(1 for issue in issues if issue.severity == "error")
    warning_count = sum(1 for issue in issues if issue.severity == "warning")
    info_count = sum(1 for issue in issues if issue.severity == "info")
    return ProfileValidationReport(
        profile_id=str(profile_id) if profile_id is not None else None,
        ok=error_count == 0,
        error_count=error_count,
        warning_count=warning_count,
        info_count=info_count,
        issues=issues,
    )
