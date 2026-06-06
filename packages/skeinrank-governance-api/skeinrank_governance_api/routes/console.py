"""User console endpoints for dictionary migration workflows."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Query, status
from skeinrank_governance import set_term_tags
from skeinrank_governance.models import (
    ALIAS_STATUSES,
    STOP_LIST_TARGETS,
    TERM_STATUSES,
    AuditEvent,
    CanonicalTerm,
    GovernanceGlobalStopListEntry,
    GovernanceStopListEntry,
    TermAlias,
    TerminologyProfile,
    normalize_profile_name,
    normalize_value,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import AuthContext, require_roles, require_scopes
from ..dependencies import get_session
from ..dictionary_spec import (
    DICTIONARY_SCHEMA_VERSION,
    is_supported_dictionary_schema_version,
    resolve_dictionary_schema_version,
)
from ..prompt_injection import (
    build_prompt_injection_risk_summary,
    scan_untrusted_payload,
)
from ..schemas import (
    ConsoleDictionaryAliasInput,
    ConsoleDictionaryExportResponse,
    ConsoleDictionaryIssue,
    ConsoleDictionaryPayload,
    ConsoleDictionaryReport,
    ConsoleDictionarySummary,
    ConsoleDictionaryTermInput,
    ConsoleStopListInput,
)

router = APIRouter(prefix="/v1/console", tags=["console"])

IMPORT_MODES = ("upsert", "strict")


@dataclass(frozen=True)
class NormalizedAliasInput:
    value: str
    normalized_value: str
    confidence: float
    status: str
    notes: str | None
    context_triggers: list[str]
    term_normalized_value: str
    path: str


@dataclass(frozen=True)
class NormalizedTermInput:
    canonical_value: str
    normalized_value: str
    slot: str
    description: str | None
    status: str
    tags: list[str]
    aliases: list[NormalizedAliasInput]
    path: str


@dataclass(frozen=True)
class NormalizedStopListInput:
    value: str
    normalized_value: str
    target: str
    reason: str | None
    is_active: bool
    path: str


@dataclass(frozen=True)
class ExistingState:
    profile: TerminologyProfile | None
    terms_by_value: dict[str, CanonicalTerm]
    aliases_by_value: dict[str, TermAlias]
    profile_stop_by_key: dict[tuple[str, str], GovernanceStopListEntry]
    global_stop_by_key: dict[tuple[str, str], GovernanceGlobalStopListEntry]
    active_profile_stop_values: dict[str, set[str]]
    active_global_stop_values: dict[str, set[str]]


@router.post(
    "/dictionary/validate",
    response_model=ConsoleDictionaryReport,
)
def validate_console_dictionary(
    request: ConsoleDictionaryPayload,
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    _scope: AuthContext = Depends(require_scopes("migration:validate")),
    session: Session = Depends(get_session),
) -> ConsoleDictionaryReport:
    """Validate a dictionary migration payload without writing to the database."""

    return _build_console_dictionary_report(session, request, applied=False)


@router.post(
    "/dictionary/import",
    response_model=ConsoleDictionaryReport,
)
def import_console_dictionary(
    request: ConsoleDictionaryPayload,
    current_user: AuthContext = Depends(require_roles("admin", "moderator")),
    _scope: AuthContext = Depends(require_scopes("migration:apply")),
    session: Session = Depends(get_session),
) -> ConsoleDictionaryReport:
    """Validate and apply a dictionary migration payload in one transaction."""

    report = _build_console_dictionary_report(session, request, applied=False)
    if report.errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "message": "Dictionary import validation failed.",
                "report": report.model_dump(mode="json"),
            },
        )
    if report.profile_exists is False and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin users can create profiles during console import.",
        )

    try:
        applied_report = _apply_console_dictionary(session, request, current_user)
        session.commit()
        return applied_report
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Database integrity error: {exc.orig}",
        ) from exc


@router.get(
    "/dictionary/export",
    response_model=ConsoleDictionaryExportResponse,
)
def export_console_dictionary(
    profile_name: str = Query(..., min_length=1, max_length=128),
    include_global_stop_list: bool = Query(default=True),
    _current_user: AuthContext = Depends(
        require_roles("admin", "moderator", "contributor")
    ),
    _scope: AuthContext = Depends(require_scopes("migration:export")),
    session: Session = Depends(get_session),
) -> ConsoleDictionaryExportResponse:
    """Export a profile dictionary in the stable user-console import shape."""

    profile = _get_profile_or_404(session, profile_name)
    terms = list(
        session.scalars(
            select(CanonicalTerm)
            .where(CanonicalTerm.profile_id == profile.id)
            .order_by(CanonicalTerm.slot, CanonicalTerm.normalized_value)
        )
    )
    exported_terms: list[ConsoleDictionaryTermInput] = []
    for term in terms:
        aliases = list(
            session.scalars(
                select(TermAlias)
                .where(TermAlias.term_id == term.id)
                .order_by(TermAlias.normalized_alias)
            )
        )
        exported_terms.append(
            ConsoleDictionaryTermInput(
                canonical_value=term.canonical_value,
                slot=term.slot,
                description=term.description,
                status=term.status,
                tags=[
                    tag.value
                    for tag in sorted(term.tags, key=lambda item: item.normalized_value)
                ],
                aliases=[
                    ConsoleDictionaryAliasInput(
                        value=alias.alias_value,
                        confidence=alias.confidence,
                        status=alias.status,
                        notes=alias.notes,
                        context_triggers=list(alias.context_triggers or []),
                    )
                    for alias in aliases
                ],
            )
        )

    profile_stop_entries = list(
        session.scalars(
            select(GovernanceStopListEntry)
            .where(GovernanceStopListEntry.profile_id == profile.id)
            .order_by(
                GovernanceStopListEntry.target,
                GovernanceStopListEntry.normalized_value,
            )
        )
    )
    global_stop_entries: list[GovernanceGlobalStopListEntry] = []
    if include_global_stop_list:
        global_stop_entries = list(
            session.scalars(
                select(GovernanceGlobalStopListEntry).order_by(
                    GovernanceGlobalStopListEntry.target,
                    GovernanceGlobalStopListEntry.normalized_value,
                )
            )
        )

    return ConsoleDictionaryExportResponse(
        schema_version=DICTIONARY_SCHEMA_VERSION,
        profile_name=profile.name,
        profile_description=profile.description,
        terms=exported_terms,
        profile_stop_list=[_export_stop_entry(entry) for entry in profile_stop_entries],
        global_stop_list=[
            _export_global_stop_entry(entry) for entry in global_stop_entries
        ],
    )


def _build_console_dictionary_report(
    session: Session,
    request: ConsoleDictionaryPayload,
    *,
    applied: bool,
) -> ConsoleDictionaryReport:
    schema_version = resolve_dictionary_schema_version(request.model_dump())
    normalized_profile_name = normalize_profile_name(request.profile_name)
    profile = _find_profile(session, request.profile_name)
    terms = _normalize_terms(request.terms)
    profile_stop_entries = _normalize_stop_entries(
        request.profile_stop_list, base_path="profile_stop_list"
    )
    global_stop_entries = _normalize_stop_entries(
        request.global_stop_list, base_path="global_stop_list"
    )
    summary = ConsoleDictionarySummary(
        terms_total=len(terms),
        aliases_total=sum(len(term.aliases) for term in terms),
        profile_stop_list_total=len(profile_stop_entries),
        global_stop_list_total=len(global_stop_entries),
    )
    errors: list[ConsoleDictionaryIssue] = []
    warnings: list[ConsoleDictionaryIssue] = []

    if not is_supported_dictionary_schema_version(request.model_dump()):
        _add_error(
            errors,
            summary,
            code="unsupported_schema_version",
            message=(
                "Unsupported dictionary schema_version: "
                f"{schema_version}. Supported version: {DICTIONARY_SCHEMA_VERSION}."
            ),
            path="schema_version",
        )

    if request.mode not in IMPORT_MODES:
        _add_error(
            errors,
            summary,
            code="invalid_import_mode",
            message=f"Invalid import mode: {request.mode}. Allowed values: upsert, strict.",
            path="mode",
        )

    if profile is None and not request.create_profile:
        _add_error(
            errors,
            summary,
            code="profile_missing",
            message=f"Profile does not exist and create_profile is false: {request.profile_name}",
            path="profile_name",
        )

    state = _load_existing_state(session, profile)
    payload_profile_stops = _stop_values_by_target(profile_stop_entries)
    payload_global_stops = _stop_values_by_target(global_stop_entries)
    _validate_stop_entries(
        profile_stop_entries,
        existing_by_key=state.profile_stop_by_key,
        errors=errors,
        warnings=warnings,
        summary=summary,
        scope="profile",
        mode=request.mode,
    )
    _validate_stop_entries(
        global_stop_entries,
        existing_by_key=state.global_stop_by_key,
        errors=errors,
        warnings=warnings,
        summary=summary,
        scope="global",
        mode=request.mode,
    )
    _validate_terms(
        terms,
        state=state,
        payload_profile_stops=payload_profile_stops,
        payload_global_stops=payload_global_stops,
        errors=errors,
        warnings=warnings,
        summary=summary,
        mode=request.mode,
    )
    risk_findings = scan_untrusted_payload(
        request.model_dump(mode="json", exclude_none=True),
        base_path="$",
    )
    _add_prompt_injection_warnings(warnings, summary, risk_findings)
    _set_issue_totals(summary, errors, warnings)
    return ConsoleDictionaryReport(
        status="applied" if applied else ("valid" if not errors else "invalid"),
        schema_version=schema_version,
        profile_name=request.profile_name,
        normalized_profile_name=normalized_profile_name,
        profile_exists=profile is not None,
        mode=request.mode,
        summary=summary,
        errors=errors,
        warnings=warnings,
        risk_findings=[finding.to_dict() for finding in risk_findings],
    )


def _apply_console_dictionary(
    session: Session,
    request: ConsoleDictionaryPayload,
    current_user: AuthContext,
) -> ConsoleDictionaryReport:
    report = _build_console_dictionary_report(session, request, applied=False)
    summary = report.summary
    profile = _find_profile(session, request.profile_name)
    if profile is None:
        profile = TerminologyProfile(
            name=request.profile_name,
            description=request.profile_description,
        )
        session.add(profile)
        session.flush()
    elif request.profile_description is not None:
        profile.description = request.profile_description

    terms = _normalize_terms(request.terms)
    for term_input in terms:
        term = session.scalar(
            select(CanonicalTerm).where(
                CanonicalTerm.profile_id == profile.id,
                CanonicalTerm.normalized_value == term_input.normalized_value,
            )
        )
        if term is None:
            term = CanonicalTerm(
                profile=profile,
                canonical_value=term_input.canonical_value,
                slot=term_input.slot,
                description=term_input.description,
                status=term_input.status,
            )
            session.add(term)
            session.flush()
            summary.created_terms += 1
        else:
            term.canonical_value = term_input.canonical_value
            term.slot = term_input.slot
            term.description = term_input.description
            term.status = term_input.status
            summary.updated_terms += 1

        set_term_tags(session, term, term_input.tags)

        for alias_input in term_input.aliases:
            alias = session.scalar(
                select(TermAlias).where(
                    TermAlias.profile_id == profile.id,
                    TermAlias.normalized_alias == alias_input.normalized_value,
                )
            )
            if alias is None:
                alias = TermAlias(
                    profile=profile,
                    term=term,
                    alias_value=alias_input.value,
                    confidence=alias_input.confidence,
                    status=alias_input.status,
                    notes=alias_input.notes,
                    context_triggers=list(alias_input.context_triggers),
                )
                session.add(alias)
                session.flush()
                summary.created_aliases += 1
            else:
                alias.term = term
                alias.alias_value = alias_input.value
                alias.confidence = alias_input.confidence
                alias.status = alias_input.status
                alias.notes = alias_input.notes
                alias.context_triggers = list(alias_input.context_triggers)
                summary.updated_aliases += 1

    for entry_input in _normalize_stop_entries(
        request.profile_stop_list, base_path="profile_stop_list"
    ):
        entry = session.scalar(
            select(GovernanceStopListEntry).where(
                GovernanceStopListEntry.profile_id == profile.id,
                GovernanceStopListEntry.target == entry_input.target,
                GovernanceStopListEntry.normalized_value
                == entry_input.normalized_value,
            )
        )
        if entry is None:
            entry = GovernanceStopListEntry(
                profile=profile,
                value=entry_input.value,
                target=entry_input.target,
                reason=entry_input.reason,
                is_active=entry_input.is_active,
            )
            session.add(entry)
            summary.created_profile_stop_list_entries += 1
        else:
            entry.value = entry_input.value
            entry.reason = entry_input.reason
            entry.is_active = entry_input.is_active
            summary.updated_profile_stop_list_entries += 1

    for entry_input in _normalize_stop_entries(
        request.global_stop_list, base_path="global_stop_list"
    ):
        entry = session.scalar(
            select(GovernanceGlobalStopListEntry).where(
                GovernanceGlobalStopListEntry.target == entry_input.target,
                GovernanceGlobalStopListEntry.normalized_value
                == entry_input.normalized_value,
            )
        )
        if entry is None:
            entry = GovernanceGlobalStopListEntry(
                value=entry_input.value,
                target=entry_input.target,
                reason=entry_input.reason,
                is_active=entry_input.is_active,
            )
            session.add(entry)
            summary.created_global_stop_list_entries += 1
        else:
            entry.value = entry_input.value
            entry.reason = entry_input.reason
            entry.is_active = entry_input.is_active
            summary.updated_global_stop_list_entries += 1

    session.add(
        AuditEvent(
            profile=profile,
            actor=current_user.username,
            action="console_dictionary_imported",
            entity_type="dictionary_import",
            entity_id=profile.normalized_name,
            payload_json={
                "mode": request.mode,
                "terms_total": summary.terms_total,
                "aliases_total": summary.aliases_total,
                "profile_stop_list_total": summary.profile_stop_list_total,
                "global_stop_list_total": summary.global_stop_list_total,
            },
        )
    )
    _set_issue_totals(summary, report.errors, report.warnings)
    return ConsoleDictionaryReport(
        status="applied",
        schema_version=resolve_dictionary_schema_version(request.model_dump()),
        profile_name=profile.name,
        normalized_profile_name=profile.normalized_name,
        profile_exists=True,
        mode=request.mode,
        summary=summary,
        errors=report.errors,
        warnings=report.warnings,
    )


def _normalize_tag_values(values: list[str]) -> list[str]:
    return sorted({normalize_value(value) for value in values if value.strip()})


def _normalize_context_triggers(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized_value = normalize_value(str(value))
        if normalized_value and normalized_value not in seen:
            normalized.append(normalized_value)
            seen.add(normalized_value)
    return normalized


def _normalize_terms(
    items: list[ConsoleDictionaryTermInput],
) -> list[NormalizedTermInput]:
    terms: list[NormalizedTermInput] = []
    for index, item in enumerate(items):
        normalized_value = normalize_value(item.canonical_value)
        aliases = [
            _normalize_alias(
                alias_item,
                term_normalized=normalized_value,
                path=f"terms[{index}].aliases[{alias_index}]",
            )
            for alias_index, alias_item in enumerate(item.aliases)
        ]
        terms.append(
            NormalizedTermInput(
                canonical_value=item.canonical_value,
                normalized_value=normalized_value,
                slot=item.slot.strip().upper(),
                description=item.description,
                status=item.status.strip().lower(),
                tags=_normalize_tag_values(item.tags),
                aliases=aliases,
                path=f"terms[{index}]",
            )
        )
    return terms


def _normalize_alias(
    item: str | ConsoleDictionaryAliasInput,
    *,
    term_normalized: str,
    path: str,
) -> NormalizedAliasInput:
    if isinstance(item, str):
        return NormalizedAliasInput(
            value=item,
            normalized_value=normalize_value(item),
            confidence=1.0,
            status="active",
            notes=None,
            context_triggers=[],
            term_normalized_value=term_normalized,
            path=path,
        )
    return NormalizedAliasInput(
        value=item.value,
        normalized_value=normalize_value(item.value),
        confidence=item.confidence,
        status=item.status.strip().lower(),
        notes=item.notes,
        context_triggers=_normalize_context_triggers(item.context_triggers),
        term_normalized_value=term_normalized,
        path=path,
    )


def _normalize_stop_entries(
    items: list[str | ConsoleStopListInput], *, base_path: str
) -> list[NormalizedStopListInput]:
    entries: list[NormalizedStopListInput] = []
    for index, item in enumerate(items):
        if isinstance(item, str):
            entries.append(
                NormalizedStopListInput(
                    value=item,
                    normalized_value=normalize_value(item),
                    target="both",
                    reason=None,
                    is_active=True,
                    path=f"{base_path}[{index}]",
                )
            )
            continue
        entries.append(
            NormalizedStopListInput(
                value=item.value,
                normalized_value=normalize_value(item.value),
                target=item.target.strip().lower(),
                reason=item.reason,
                is_active=item.is_active,
                path=f"{base_path}[{index}]",
            )
        )
    return entries


def _validate_terms(
    terms: list[NormalizedTermInput],
    *,
    state: ExistingState,
    payload_profile_stops: dict[str, set[str]],
    payload_global_stops: dict[str, set[str]],
    errors: list[ConsoleDictionaryIssue],
    warnings: list[ConsoleDictionaryIssue],
    summary: ConsoleDictionarySummary,
    mode: str,
) -> None:
    seen_terms: dict[str, NormalizedTermInput] = {}
    seen_aliases: dict[str, NormalizedAliasInput] = {}

    for term in terms:
        if not term.normalized_value:
            _add_error(
                errors,
                summary,
                code="empty_canonical_value",
                message="Canonical value is empty after normalization.",
                path=f"{term.path}.canonical_value",
            )
            continue
        if term.status not in TERM_STATUSES:
            _add_error(
                errors,
                summary,
                code="invalid_term_status",
                message=f"Invalid term status: {term.status}.",
                path=f"{term.path}.status",
            )
        previous = seen_terms.get(term.normalized_value)
        if previous is not None:
            _add_error(
                errors,
                summary,
                code="duplicate_canonical_value",
                message=f"Duplicate canonical term in payload: {term.canonical_value}",
                path=term.path,
            )
            continue
        seen_terms[term.normalized_value] = term

        if _is_blocked(
            term.normalized_value,
            "canonical",
            state,
            payload_profile_stops,
            payload_global_stops,
        ):
            _add_error(
                errors,
                summary,
                code="canonical_stoplisted",
                message=f"Canonical term is blocked by stop list: {term.canonical_value}",
                path=f"{term.path}.canonical_value",
                blocked=True,
            )

        existing_term = state.terms_by_value.get(term.normalized_value)
        if existing_term is None:
            summary.would_create_terms += 1
        else:
            if mode == "strict":
                _add_error(
                    errors,
                    summary,
                    code="canonical_exists",
                    message=f"Canonical term already exists: {term.canonical_value}",
                    path=term.path,
                    conflict=True,
                )
            summary.would_update_terms += 1

        for alias in term.aliases:
            if not alias.normalized_value:
                _add_error(
                    errors,
                    summary,
                    code="empty_alias_value",
                    message="Alias value is empty after normalization.",
                    path=f"{alias.path}.value",
                )
                continue
            if alias.status not in ALIAS_STATUSES:
                _add_error(
                    errors,
                    summary,
                    code="invalid_alias_status",
                    message=f"Invalid alias status: {alias.status}.",
                    path=f"{alias.path}.status",
                )
            previous_alias = seen_aliases.get(alias.normalized_value)
            if previous_alias is not None:
                if previous_alias.term_normalized_value == term.normalized_value:
                    _add_warning(
                        warnings,
                        summary,
                        code="duplicate_alias",
                        message=f"Duplicate alias repeated in the same term: {alias.value}",
                        path=alias.path,
                    )
                else:
                    _add_error(
                        errors,
                        summary,
                        code="alias_payload_collision",
                        message=f"Alias is assigned to multiple canonical terms in payload: {alias.value}",
                        path=alias.path,
                        conflict=True,
                    )
                continue
            seen_aliases[alias.normalized_value] = alias

            if _is_blocked(
                alias.normalized_value,
                "alias",
                state,
                payload_profile_stops,
                payload_global_stops,
            ):
                _add_error(
                    errors,
                    summary,
                    code="alias_stoplisted",
                    message=f"Alias is blocked by stop list: {alias.value}",
                    path=f"{alias.path}.value",
                    blocked=True,
                )

            existing_alias = state.aliases_by_value.get(alias.normalized_value)
            if existing_alias is None:
                summary.would_create_aliases += 1
            elif existing_alias.term.normalized_value != term.normalized_value:
                _add_error(
                    errors,
                    summary,
                    code="alias_existing_collision",
                    message=f"Alias already exists for another canonical term: {alias.value}",
                    path=alias.path,
                    conflict=True,
                )
            else:
                if mode == "strict":
                    _add_error(
                        errors,
                        summary,
                        code="alias_exists",
                        message=f"Alias already exists: {alias.value}",
                        path=alias.path,
                        conflict=True,
                    )
                summary.would_update_aliases += 1


def _validate_stop_entries(
    entries: list[NormalizedStopListInput],
    *,
    existing_by_key: dict[
        tuple[str, str], GovernanceStopListEntry | GovernanceGlobalStopListEntry
    ],
    errors: list[ConsoleDictionaryIssue],
    warnings: list[ConsoleDictionaryIssue],
    summary: ConsoleDictionarySummary,
    scope: str,
    mode: str,
) -> None:
    seen_entries: list[NormalizedStopListInput] = []
    for entry in entries:
        if not entry.normalized_value:
            _add_error(
                errors,
                summary,
                code="empty_stop_list_value",
                message="Stop-list value is empty after normalization.",
                path=f"{entry.path}.value",
            )
            continue
        if entry.target not in STOP_LIST_TARGETS:
            _add_error(
                errors,
                summary,
                code="invalid_stop_list_target",
                message=f"Invalid stop-list target: {entry.target}.",
                path=f"{entry.path}.target",
            )
            continue

        duplicate = _find_overlapping_stop_entry(entry, seen_entries)
        if duplicate is not None:
            if duplicate.target == entry.target:
                _add_warning(
                    warnings,
                    summary,
                    code="duplicate_stop_list_entry",
                    message=(
                        f"Duplicate {scope} stop-list entry in payload: "
                        f"{entry.value}"
                    ),
                    path=entry.path,
                )
            else:
                _add_error(
                    errors,
                    summary,
                    code=f"{scope}_stop_list_target_overlap",
                    message=(
                        f"{scope.title()} stop-list target overlaps another "
                        f"payload entry for value: {entry.value}"
                    ),
                    path=entry.path,
                    conflict=True,
                )
            continue
        seen_entries.append(entry)

        existing = _find_overlapping_existing_stop_entry(entry, existing_by_key)
        if existing is not None:
            if scope == "profile":
                summary.would_update_profile_stop_list_entries += 1
            else:
                summary.would_update_global_stop_list_entries += 1
            if existing.target != entry.target:
                _add_error(
                    errors,
                    summary,
                    code=f"{scope}_stop_list_existing_target_overlap",
                    message=(
                        f"{scope.title()} stop-list entry overlaps an existing "
                        f"entry: {entry.value} ({existing.target})"
                    ),
                    path=entry.path,
                    conflict=True,
                )
            elif mode == "strict":
                _add_error(
                    errors,
                    summary,
                    code=f"{scope}_stop_list_entry_exists",
                    message=(
                        f"{scope.title()} stop-list entry already exists: "
                        f"{entry.value}"
                    ),
                    path=entry.path,
                    conflict=True,
                )
        else:
            if scope == "profile":
                summary.would_create_profile_stop_list_entries += 1
            else:
                summary.would_create_global_stop_list_entries += 1


def _find_overlapping_stop_entry(
    entry: NormalizedStopListInput, candidates: list[NormalizedStopListInput]
) -> NormalizedStopListInput | None:
    for candidate in candidates:
        if (
            candidate.normalized_value == entry.normalized_value
            and _stop_targets_overlap(candidate.target, entry.target)
        ):
            return candidate
    return None


def _find_overlapping_existing_stop_entry(
    entry: NormalizedStopListInput,
    candidates: dict[
        tuple[str, str], GovernanceStopListEntry | GovernanceGlobalStopListEntry
    ],
) -> GovernanceStopListEntry | GovernanceGlobalStopListEntry | None:
    for candidate in candidates.values():
        if (
            candidate.normalized_value == entry.normalized_value
            and _stop_targets_overlap(candidate.target, entry.target)
        ):
            return candidate
    return None


def _stop_targets_overlap(first: str, second: str) -> bool:
    return first == second or first == "both" or second == "both"


def _load_existing_state(
    session: Session, profile: TerminologyProfile | None
) -> ExistingState:
    terms_by_value: dict[str, CanonicalTerm] = {}
    aliases_by_value: dict[str, TermAlias] = {}
    profile_stop_by_key: dict[tuple[str, str], GovernanceStopListEntry] = {}
    active_profile_stop_values: dict[str, set[str]] = {
        "alias": set(),
        "canonical": set(),
        "both": set(),
    }

    if profile is not None:
        terms = list(
            session.scalars(
                select(CanonicalTerm).where(CanonicalTerm.profile_id == profile.id)
            )
        )
        terms_by_value = {term.normalized_value: term for term in terms}
        aliases = list(
            session.scalars(select(TermAlias).where(TermAlias.profile_id == profile.id))
        )
        aliases_by_value = {alias.normalized_alias: alias for alias in aliases}
        profile_stop_entries = list(
            session.scalars(
                select(GovernanceStopListEntry).where(
                    GovernanceStopListEntry.profile_id == profile.id
                )
            )
        )
        profile_stop_by_key = {
            (entry.target, entry.normalized_value): entry
            for entry in profile_stop_entries
        }
        active_profile_stop_values = _active_values_by_target(profile_stop_entries)

    global_stop_entries = list(session.scalars(select(GovernanceGlobalStopListEntry)))
    global_stop_by_key = {
        (entry.target, entry.normalized_value): entry for entry in global_stop_entries
    }
    active_global_stop_values = _active_values_by_target(global_stop_entries)
    return ExistingState(
        profile=profile,
        terms_by_value=terms_by_value,
        aliases_by_value=aliases_by_value,
        profile_stop_by_key=profile_stop_by_key,
        global_stop_by_key=global_stop_by_key,
        active_profile_stop_values=active_profile_stop_values,
        active_global_stop_values=active_global_stop_values,
    )


def _active_values_by_target(entries) -> dict[str, set[str]]:
    values: dict[str, set[str]] = {"alias": set(), "canonical": set(), "both": set()}
    for entry in entries:
        if entry.is_active:
            values.setdefault(entry.target, set()).add(entry.normalized_value)
    return values


def _stop_values_by_target(
    entries: list[NormalizedStopListInput],
) -> dict[str, set[str]]:
    values: dict[str, set[str]] = {"alias": set(), "canonical": set(), "both": set()}
    for entry in entries:
        if entry.is_active:
            values.setdefault(entry.target, set()).add(entry.normalized_value)
    return values


def _is_blocked(
    normalized_value: str,
    target: str,
    state: ExistingState,
    payload_profile_stops: dict[str, set[str]],
    payload_global_stops: dict[str, set[str]],
) -> bool:
    target_values = _target_values(target)
    for values_by_target in (
        state.active_profile_stop_values,
        state.active_global_stop_values,
        payload_profile_stops,
        payload_global_stops,
    ):
        if any(
            normalized_value in values_by_target.get(value, set())
            for value in target_values
        ):
            return True
    return False


def _target_values(target: str) -> tuple[str, ...]:
    if target == "alias":
        return ("alias", "both")
    if target == "canonical":
        return ("canonical", "both")
    return STOP_LIST_TARGETS


def _find_profile(session: Session, profile_name: str) -> TerminologyProfile | None:
    return session.scalar(
        select(TerminologyProfile).where(
            TerminologyProfile.normalized_name == normalize_profile_name(profile_name)
        )
    )


def _get_profile_or_404(session: Session, profile_name: str) -> TerminologyProfile:
    profile = _find_profile(session, profile_name)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Profile not found: {profile_name}",
        )
    return profile


def _export_stop_entry(entry: GovernanceStopListEntry) -> ConsoleStopListInput:
    return ConsoleStopListInput(
        value=entry.value,
        target=entry.target,
        reason=entry.reason,
        is_active=entry.is_active,
    )


def _export_global_stop_entry(
    entry: GovernanceGlobalStopListEntry,
) -> ConsoleStopListInput:
    return ConsoleStopListInput(
        value=entry.value,
        target=entry.target,
        reason=entry.reason,
        is_active=entry.is_active,
    )


def _add_error(
    errors: list[ConsoleDictionaryIssue],
    summary: ConsoleDictionarySummary,
    *,
    code: str,
    message: str,
    path: str | None,
    conflict: bool = False,
    blocked: bool = False,
) -> None:
    errors.append(
        ConsoleDictionaryIssue(
            code=code,
            message=message,
            path=path,
            severity="error",
        )
    )
    if conflict:
        summary.conflicts += 1
    if blocked:
        summary.blocked_by_stop_list += 1


def _add_prompt_injection_warnings(
    warnings: list[ConsoleDictionaryIssue],
    summary: ConsoleDictionarySummary,
    findings,
) -> None:
    if not findings:
        return
    summary.prompt_like_instruction_findings = len(findings)
    risk_summary = build_prompt_injection_risk_summary(findings)
    for finding in findings:
        warnings.append(
            ConsoleDictionaryIssue(
                code=finding.risk_code,
                message=(
                    f"Prompt-like instruction risk in untrusted dictionary input: "
                    f"{finding.message}"
                ),
                path=finding.path,
                severity="warning",
            )
        )
    if risk_summary.get("status") == "review_required":
        warnings.append(
            ConsoleDictionaryIssue(
                code="prompt_injection_review_required",
                message=(
                    "Dictionary input contains prompt-like or tool-like text. "
                    "Review findings before promotion to runtime snapshots."
                ),
                path=None,
                severity="warning",
            )
        )


def _add_warning(
    warnings: list[ConsoleDictionaryIssue],
    summary: ConsoleDictionarySummary,
    *,
    code: str,
    message: str,
    path: str | None,
) -> None:
    warnings.append(
        ConsoleDictionaryIssue(
            code=code,
            message=message,
            path=path,
            severity="warning",
        )
    )
    if code.startswith("duplicate"):
        summary.duplicates += 1


def _set_issue_totals(
    summary: ConsoleDictionarySummary,
    errors: list[ConsoleDictionaryIssue],
    warnings: list[ConsoleDictionaryIssue],
) -> None:
    summary.errors = len(errors)
    summary.warnings = len(warnings)
