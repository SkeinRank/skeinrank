"""Proposal source-quality analytics for agent/human review workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from skeinrank_governance.models import (
    GovernanceSuggestion,
    TerminologyProfile,
    normalize_profile_name,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

_UNKNOWN_SOURCE_NAME = "unknown"
_VALIDATION_STATUSES = ("passed", "warning", "blocked", "unknown")


@dataclass
class ProposalSourceQualityRow:
    """Aggregated quality signal for one proposal source."""

    proposal_source_type: str
    proposal_source_name: str
    proposals_total: int = 0
    pending: int = 0
    approved: int = 0
    rejected: int = 0
    validation_passed: int = 0
    validation_warning: int = 0
    validation_blocked: int = 0
    validation_unknown: int = 0
    confidence_total: float = 0.0

    @property
    def approval_rate(self) -> float:
        reviewed = self.approved + self.rejected
        if reviewed == 0:
            return 0.0
        return self.approved / reviewed

    @property
    def rejection_rate(self) -> float:
        reviewed = self.approved + self.rejected
        if reviewed == 0:
            return 0.0
        return self.rejected / reviewed

    @property
    def blocked_rate(self) -> float:
        if self.proposals_total == 0:
            return 0.0
        return self.validation_blocked / self.proposals_total

    @property
    def average_confidence(self) -> float:
        if self.proposals_total == 0:
            return 0.0
        return self.confidence_total / self.proposals_total


def build_proposal_source_quality(
    session: Session,
    *,
    profile_name: str | None = None,
    proposal_source_type: str | None = None,
    proposal_source_name: str | None = None,
) -> list[ProposalSourceQualityRow]:
    """Return aggregated proposal quality rows for review/agent sources."""

    query = select(GovernanceSuggestion).join(GovernanceSuggestion.profile)
    if profile_name is not None:
        query = query.where(
            TerminologyProfile.normalized_name == normalize_profile_name(profile_name)
        )
    if proposal_source_type is not None:
        query = query.where(
            GovernanceSuggestion.proposal_source_type == proposal_source_type
        )
    if proposal_source_name is not None:
        query = query.where(
            GovernanceSuggestion.proposal_source_name == proposal_source_name
        )

    rows: dict[tuple[str, str], ProposalSourceQualityRow] = {}
    for suggestion in session.scalars(query):
        source_name = suggestion.proposal_source_name or _UNKNOWN_SOURCE_NAME
        key = (suggestion.proposal_source_type, source_name)
        row = rows.setdefault(
            key,
            ProposalSourceQualityRow(
                proposal_source_type=suggestion.proposal_source_type,
                proposal_source_name=source_name,
            ),
        )
        row.proposals_total += 1
        row.confidence_total += float(suggestion.confidence or 0.0)
        if suggestion.status == "pending":
            row.pending += 1
        elif suggestion.status == "approved":
            row.approved += 1
        elif suggestion.status == "rejected":
            row.rejected += 1

        validation_status = _validation_status(suggestion.validation_summary_json)
        if validation_status == "passed":
            row.validation_passed += 1
        elif validation_status == "warning":
            row.validation_warning += 1
        elif validation_status == "blocked":
            row.validation_blocked += 1
        else:
            row.validation_unknown += 1

    return sorted(
        rows.values(),
        key=lambda item: (
            item.proposal_source_type,
            item.proposal_source_name,
        ),
    )


def validation_status(summary: dict[str, Any] | None) -> str:
    """Return a normalized proposal validation status for metrics labels."""

    return _validation_status(summary)


def _validation_status(summary: dict[str, Any] | None) -> str:
    if not isinstance(summary, dict):
        return "unknown"
    status = str(summary.get("status") or "unknown").strip().lower()
    if status not in _VALIDATION_STATUSES:
        return "unknown"
    return status
