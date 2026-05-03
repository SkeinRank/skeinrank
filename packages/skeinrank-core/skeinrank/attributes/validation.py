from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .alias_map import AliasEntry, expand_profile_aliases
from .normalize import normalize_value
from .profiles import AttributeProfilePayload, load_attribute_profile
from .types import AttributeSlot

IssueSeverity = Literal["error", "warning", "info"]

DEFAULT_GENERIC_ALIASES = frozenset(
    {
        "api",
        "app",
        "application",
        "bug",
        "client",
        "component",
        "data",
        "error",
        "issue",
        "job",
        "node",
        "problem",
        "process",
        "queue",
        "request",
        "response",
        "server",
        "service",
        "system",
        "task",
        "worker",
    }
)

ALLOWED_ALIAS_STATUSES = frozenset(
    {"active", "deprecated", "disabled", "ambiguous", "pending", "rejected"}
)
ACTIVE_ALIAS_STATUSES = frozenset({"active", "deprecated"})
NON_PUBLISHABLE_ALIAS_STATUSES = frozenset(
    {"ambiguous", "pending", "rejected", "disabled"}
)
STRICT_ELEVATED_CODES = frozenset(
    {
        "ambiguous_alias_status",
        "deprecated_alias_status",
        "disabled_alias_status",
        "duplicate_alias",
        "empty_alias_list",
        "generic_alias",
        "pending_alias_status",
        "rejected_alias_status",
        "short_alias",
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
    publishable: bool
    strict: bool = False
    error_count: int
    warning_count: int
    info_count: int
    issues: list[ProfileValidationIssue] = Field(default_factory=list)

    def raise_for_errors(self) -> None:
        if self.error_count:
            raise ValueError(
                f"Attribute profile validation failed with {self.error_count} error(s)"
            )


class _FlatAliasRecord(BaseModel):
    alias: str
    canonical: str
    slot: str
    status: str = "active"
    confidence: float = 0.95

    def to_runtime_row(self) -> dict[str, Any]:
        return {
            "alias": self.alias,
            "canonical": self.canonical,
            "slot": self.slot,
            "confidence": self.confidence,
        }


def _profile_payload(
    profile: str | Path | Mapping[str, Any],
) -> AttributeProfilePayload:
    if isinstance(profile, (str, Path)):
        return load_attribute_profile(profile)
    return dict(profile)


def _strict_severity(
    severity: IssueSeverity, *, code: str, strict: bool
) -> IssueSeverity:
    if strict and severity == "warning" and code in STRICT_ELEVATED_CODES:
        return "error"
    return severity


def _issue(
    issues: list[ProfileValidationIssue],
    *,
    severity: IssueSeverity,
    code: str,
    message: str,
    strict: bool = False,
    alias: str | None = None,
    canonical: str | None = None,
    slot: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    resolved_severity = _strict_severity(severity, code=code, strict=strict)
    resolved_details = dict(details or {})
    if resolved_severity != severity:
        resolved_details["strict_elevated"] = True
    issues.append(
        ProfileValidationIssue(
            severity=resolved_severity,
            code=code,
            message=message,
            alias=alias,
            canonical=canonical,
            slot=slot,
            details=resolved_details,
        )
    )


def _status_value(raw_status: Any) -> str:
    if raw_status is None:
        return "active"
    return str(raw_status).strip().lower().replace("-", "_") or "active"


def _validate_alias_status(
    status: str,
    issues: list[ProfileValidationIssue],
    *,
    strict: bool,
    alias: str | None,
    canonical: str | None,
    slot: str | None,
    index: int,
) -> bool:
    if status not in ALLOWED_ALIAS_STATUSES:
        _issue(
            issues,
            severity="error",
            code="invalid_alias_status",
            message=(
                f"Alias status '{status}' is not supported. Use one of: "
                f"{', '.join(sorted(ALLOWED_ALIAS_STATUSES))}."
            ),
            alias=alias,
            canonical=canonical,
            slot=slot,
            details={"index": index, "status": status},
        )
        return False

    if status == "active":
        return True

    if status == "deprecated":
        _issue(
            issues,
            severity="warning",
            code="deprecated_alias_status",
            message=(
                "Deprecated aliases remain usable, but they should be reviewed "
                "before publishing a production snapshot."
            ),
            strict=strict,
            alias=alias,
            canonical=canonical,
            slot=slot,
            details={"index": index, "status": status},
        )
        return True

    code = f"{status}_alias_status"
    _issue(
        issues,
        severity="warning",
        code=code,
        message=(
            f"Alias status '{status}' is not an active deterministic runtime "
            "mapping. Keep it in a draft/governance store or remove it from "
            "published snapshots."
        ),
        strict=strict,
        alias=alias,
        canonical=canonical,
        slot=slot,
        details={"index": index, "status": status},
    )
    return True


def _validate_slot(
    slot: str | None,
    issues: list[ProfileValidationIssue],
    *,
    strict: bool,
    canonical: str | None,
    index: int,
) -> str | None:
    if slot is None:
        return None
    try:
        return AttributeSlot(slot).value
    except ValueError:
        _issue(
            issues,
            severity="error",
            code="invalid_slot",
            message=f"Slot '{slot}' is not a known attribute slot.",
            strict=strict,
            canonical=canonical,
            slot=slot,
            details={"index": index},
        )
        return None


def _append_alias_record(
    records: list[_FlatAliasRecord],
    issues: list[ProfileValidationIssue],
    *,
    raw_alias: Any,
    canonical: str | None,
    slot: str | None,
    status: str,
    confidence: float,
    strict: bool,
    index: int,
) -> None:
    if raw_alias is None:
        _issue(
            issues,
            severity="error",
            code="missing_alias_value",
            message="Alias value must not be null and must define 'alias' or 'value'.",
            strict=strict,
            canonical=canonical,
            slot=slot,
            details={"index": index},
        )
        return

    alias = str(raw_alias).strip()
    normalized_alias = normalize_value(alias)
    if not normalized_alias:
        _issue(
            issues,
            severity="error",
            code="empty_alias",
            message="Alias value must not be empty after normalization.",
            strict=strict,
            canonical=canonical,
            slot=slot,
            details={"index": index},
        )
        return

    if not any(char.isalnum() for char in normalized_alias):
        _issue(
            issues,
            severity="error",
            code="invalid_alias_value",
            message="Alias value must contain at least one alphanumeric character.",
            strict=strict,
            alias=normalized_alias,
            canonical=canonical,
            slot=slot,
            details={"index": index},
        )
        return

    if canonical is None or slot is None:
        return

    records.append(
        _FlatAliasRecord(
            alias=alias,
            canonical=canonical,
            slot=slot,
            status=status,
            confidence=confidence,
        )
    )


def _flatten_profile_aliases(
    raw_aliases: Any,
    issues: list[ProfileValidationIssue],
    *,
    strict: bool,
) -> list[_FlatAliasRecord]:
    records: list[_FlatAliasRecord] = []
    if not isinstance(raw_aliases, list):
        _issue(
            issues,
            severity="error",
            code="aliases_not_list",
            message="Profile field 'aliases' must be a list.",
            strict=strict,
            details={"type": type(raw_aliases).__name__},
        )
        return records

    for index, item in enumerate(raw_aliases):
        if not isinstance(item, dict):
            _issue(
                issues,
                severity="error",
                code="alias_entry_not_object",
                message="Alias entries must be JSON objects.",
                strict=strict,
                details={"index": index, "type": type(item).__name__},
            )
            continue

        canonical = str(item.get("canonical", "")).strip() or None
        slot = str(item.get("slot", "")).strip() or None
        normalized_canonical = normalize_value(canonical or "")
        item_status = _status_value(item.get("status"))
        default_confidence = float(item.get("confidence", 0.95))

        if "canonical" not in item or canonical is None:
            _issue(
                issues,
                severity="error",
                code="missing_canonical",
                message="Alias entry is missing required field 'canonical'.",
                strict=strict,
                details={"index": index},
            )
        elif not normalized_canonical:
            _issue(
                issues,
                severity="error",
                code="empty_canonical",
                message="Canonical value must not be empty after normalization.",
                strict=strict,
                canonical=canonical,
                details={"index": index},
            )
        elif not any(char.isalnum() for char in normalized_canonical):
            _issue(
                issues,
                severity="error",
                code="invalid_canonical_value",
                message="Canonical value must contain at least one alphanumeric character.",
                strict=strict,
                canonical=canonical,
                details={"index": index},
            )

        if "slot" not in item or slot is None:
            _issue(
                issues,
                severity="error",
                code="missing_slot",
                message="Alias entry is missing required field 'slot'.",
                strict=strict,
                canonical=canonical,
                details={"index": index},
            )
        slot = _validate_slot(
            slot, issues, strict=strict, canonical=canonical, index=index
        )

        _validate_alias_status(
            item_status,
            issues,
            strict=strict,
            alias=None,
            canonical=canonical,
            slot=slot,
            index=index,
        )

        if "alias" not in item and "aliases" not in item:
            _issue(
                issues,
                severity="error",
                code="missing_alias",
                message="Alias entry must define either 'alias' or 'aliases'.",
                strict=strict,
                canonical=canonical,
                slot=slot,
                details={"index": index},
            )
            continue

        if "alias" in item:
            _append_alias_record(
                records,
                issues,
                raw_alias=item.get("alias"),
                canonical=canonical,
                slot=slot,
                status=item_status,
                confidence=default_confidence,
                strict=strict,
                index=index,
            )

        if "aliases" not in item:
            continue

        raw_values = item["aliases"]
        if raw_values == []:
            _issue(
                issues,
                severity="warning",
                code="empty_alias_list",
                message="Grouped alias entry has an empty aliases list.",
                strict=strict,
                canonical=canonical,
                slot=slot,
                details={"index": index},
            )
            continue

        if isinstance(raw_values, str):
            raw_values = [raw_values]
        elif not isinstance(raw_values, list):
            _issue(
                issues,
                severity="error",
                code="invalid_aliases_type",
                message="Grouped alias field 'aliases' must be a string or list.",
                strict=strict,
                canonical=canonical,
                slot=slot,
                details={"index": index, "type": type(raw_values).__name__},
            )
            continue

        for raw_value in raw_values:
            alias_status = item_status
            alias_confidence = default_confidence
            raw_alias = raw_value
            if isinstance(raw_value, dict):
                raw_alias = raw_value.get("alias", raw_value.get("value"))
                alias_status = _status_value(raw_value.get("status", alias_status))
                alias_confidence = float(raw_value.get("confidence", alias_confidence))
                _validate_alias_status(
                    alias_status,
                    issues,
                    strict=strict,
                    alias=str(raw_alias).strip() if raw_alias is not None else None,
                    canonical=canonical,
                    slot=slot,
                    index=index,
                )

            _append_alias_record(
                records,
                issues,
                raw_alias=raw_alias,
                canonical=canonical,
                slot=slot,
                status=alias_status,
                confidence=alias_confidence,
                strict=strict,
                index=index,
            )

    return records


def _validate_entries(
    entries: list[AliasEntry],
    issues: list[ProfileValidationIssue],
    *,
    strict: bool,
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
                strict=strict,
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
                    "search precision. Prefer a more specific phrase such as "
                    "'api-server', 'payments-api', or a scoped alias."
                ),
                strict=strict,
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
                strict=strict,
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
                strict=strict,
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
            strict=strict,
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
    strict: bool = False,
    generic_aliases: set[str] | None = None,
    min_short_alias_length: int = 3,
) -> ProfileValidationReport:
    """Validate a terminology profile snapshot before runtime use.

    The validator is intentionally conservative: collisions are errors, while
    generic, short, deprecated, and non-active aliases are warnings by default.
    With ``strict=True``, governance warnings are elevated to errors so the
    command can be used as a pre-publish snapshot gate in CI.
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
            strict=strict,
        )
        return _report(None, issues, strict=strict)

    profile_id = payload.get("profile_id")
    if not isinstance(profile_id, str) or not profile_id.strip():
        _issue(
            issues,
            severity="error",
            code="missing_profile_id",
            message="Profile is missing non-empty field 'profile_id'.",
            strict=strict,
        )
        profile_id = None

    raw_aliases = payload.get("aliases")
    records = _flatten_profile_aliases(raw_aliases, issues, strict=strict)
    if not isinstance(raw_aliases, list):
        return _report(profile_id, issues, strict=strict)

    active_records = [
        record for record in records if record.status in ACTIVE_ALIAS_STATUSES
    ]
    if not active_records:
        _issue(
            issues,
            severity="error",
            code="no_active_alias_entries",
            message="Profile must contain at least one active or deprecated alias entry.",
            strict=strict,
        )
        return _report(profile_id, issues, strict=strict)

    try:
        entries = expand_profile_aliases(
            [record.to_runtime_row() for record in active_records]
        )
    except Exception as exc:  # noqa: BLE001 - validation should report bad shapes
        _issue(
            issues,
            severity="error",
            code="alias_expansion_error",
            message=str(exc),
            strict=strict,
        )
        return _report(profile_id, issues, strict=strict)

    _validate_entries(
        entries,
        issues,
        strict=strict,
        generic_aliases=generic_aliases,
        min_short_alias_length=min_short_alias_length,
    )
    return _report(profile_id, issues, strict=strict)


def _report(
    profile_id: Any, issues: list[ProfileValidationIssue], *, strict: bool
) -> ProfileValidationReport:
    error_count = sum(1 for issue in issues if issue.severity == "error")
    warning_count = sum(1 for issue in issues if issue.severity == "warning")
    info_count = sum(1 for issue in issues if issue.severity == "info")
    return ProfileValidationReport(
        profile_id=str(profile_id) if profile_id is not None else None,
        ok=error_count == 0,
        publishable=error_count == 0,
        strict=strict,
        error_count=error_count,
        warning_count=warning_count,
        info_count=info_count,
        issues=issues,
    )
