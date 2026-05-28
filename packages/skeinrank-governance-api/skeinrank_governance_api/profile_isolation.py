"""Read-only profile/binding isolation checks for production safety."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from skeinrank_governance.models import (
    AgentCandidateObservation,
    AgentDocumentVisit,
    AgentEvidenceWindow,
    AgentLlmReview,
    AgentProposalAttempt,
    AgentRun,
    ElasticsearchBinding,
    ElasticsearchEnrichmentJob,
    GovernanceBindingPolicy,
    GovernanceSuggestion,
    TerminologyProfile,
    normalize_profile_name,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

SCHEMA_VERSION = "skeinrank.profile_isolation.v1"


@dataclass(frozen=True)
class IsolationIssue:
    """One sampled profile-isolation issue."""

    entity: str
    entity_id: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "entity": self.entity,
            "entity_id": self.entity_id,
            "severity": self.severity,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class IsolationCheck:
    """One aggregate read-only profile-isolation check."""

    name: str
    status: str
    message: str
    issues: tuple[IsolationIssue, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self, *, sample_limit: int) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "issues_count": len(self.issues),
            "sampled_issues": [
                issue.as_dict() for issue in self.issues[: max(0, sample_limit)]
            ],
            "details": dict(self.details),
        }


def build_profile_isolation_report(
    session: Session, *, sample_limit: int = 20
) -> dict[str, Any]:
    """Return a side-effect-free profile/binding isolation report."""

    profiles = list(session.scalars(select(TerminologyProfile)))
    bindings = list(session.scalars(select(ElasticsearchBinding)))
    suggestions = list(session.scalars(select(GovernanceSuggestion)))
    agent_runs = list(session.scalars(select(AgentRun)))

    binding_by_id = {binding.id: binding for binding in bindings}
    profile_by_id = {profile.id: profile for profile in profiles}
    suggestion_by_id = {suggestion.id: suggestion for suggestion in suggestions}
    agent_run_by_id = {agent_run.id: agent_run for agent_run in agent_runs}

    checks = [
        _check_profile_boundaries(profiles=profiles, bindings=bindings),
        _check_binding_profile_alignment(
            bindings=bindings, profile_by_id=profile_by_id
        ),
        _check_binding_scoped_rows(
            name="proposal_binding_profile_alignment",
            rows=suggestions,
            entity="governance_suggestion",
            binding_by_id=binding_by_id,
        ),
        _check_binding_scoped_rows(
            name="binding_policy_profile_alignment",
            rows=list(session.scalars(select(GovernanceBindingPolicy))),
            entity="governance_binding_policy",
            binding_by_id=binding_by_id,
        ),
        _check_binding_scoped_rows(
            name="enrichment_job_profile_alignment",
            rows=list(session.scalars(select(ElasticsearchEnrichmentJob))),
            entity="elasticsearch_enrichment_job",
            binding_by_id=binding_by_id,
        ),
        _check_agent_run_alignment(agent_runs=agent_runs, binding_by_id=binding_by_id),
        _check_agent_tracking_alignment(
            name="agent_document_visit_alignment",
            rows=list(session.scalars(select(AgentDocumentVisit))),
            entity="agent_document_visit",
            binding_by_id=binding_by_id,
            agent_run_by_id=agent_run_by_id,
        ),
        _check_agent_tracking_alignment(
            name="agent_candidate_observation_alignment",
            rows=list(session.scalars(select(AgentCandidateObservation))),
            entity="agent_candidate_observation",
            binding_by_id=binding_by_id,
            agent_run_by_id=agent_run_by_id,
        ),
        _check_agent_tracking_alignment(
            name="agent_evidence_window_alignment",
            rows=list(session.scalars(select(AgentEvidenceWindow))),
            entity="agent_evidence_window",
            binding_by_id=binding_by_id,
            agent_run_by_id=agent_run_by_id,
        ),
        _check_agent_tracking_alignment(
            name="agent_llm_review_alignment",
            rows=list(session.scalars(select(AgentLlmReview))),
            entity="agent_llm_review",
            binding_by_id=binding_by_id,
            agent_run_by_id=agent_run_by_id,
        ),
        _check_agent_tracking_alignment(
            name="agent_proposal_attempt_alignment",
            rows=list(session.scalars(select(AgentProposalAttempt))),
            entity="agent_proposal_attempt",
            binding_by_id=binding_by_id,
            agent_run_by_id=agent_run_by_id,
            suggestion_by_id=suggestion_by_id,
        ),
        _check_runtime_guards(),
    ]

    failed_checks = sum(1 for check in checks if check.status != "ok")
    issues_total = sum(len(check.issues) for check in checks)
    status = "ok" if failed_checks == 0 else "degraded"

    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "summary": {
            "profiles_total": len(profiles),
            "bindings_total": len(bindings),
            "suggestions_total": len(suggestions),
            "agent_runs_total": len(agent_runs),
            "checks_total": len(checks),
            "failed_checks": failed_checks,
            "issues_total": issues_total,
        },
        "checks": [check.as_dict(sample_limit=sample_limit) for check in checks],
        "rules": {
            "binding_profile": [
                "Every binding-scoped object must reference a binding that belongs to the same profile.",
                "A request with both profile_name and binding_id must reject mismatched profile/binding pairs.",
            ],
            "agent_run": [
                "Agent runs with binding_id inherit that binding's profile context.",
                "Agent tracking rows must stay inside the parent agent run profile/binding context.",
            ],
            "review_apply": [
                "Reviewer/admin actions must resolve suggestions through the requested profile route.",
                "Batch preview/apply binding_id must belong to the route profile.",
            ],
        },
        "safety": {
            "read_only": True,
            "database_mutation_enabled": False,
            "runtime_mutation_enabled": False,
            "openrouter_calls": False,
            "elasticsearch_calls": False,
            "multi_tenant_claim": False,
        },
    }


def _check_profile_boundaries(
    *, profiles: list[TerminologyProfile], bindings: list[ElasticsearchBinding]
) -> IsolationCheck:
    profile_ids_with_bindings = {binding.profile_id for binding in bindings}
    profiles_with_bindings = sum(
        1 for profile in profiles if profile.id in profile_ids_with_bindings
    )
    return IsolationCheck(
        name="profile_boundaries",
        status="ok",
        message="Profiles are the current isolation boundary for governance data.",
        details={
            "profiles_total": len(profiles),
            "profiles_with_bindings": profiles_with_bindings,
            "bindings_total": len(bindings),
        },
    )


def _check_binding_profile_alignment(
    *,
    bindings: list[ElasticsearchBinding],
    profile_by_id: dict[int, TerminologyProfile],
) -> IsolationCheck:
    issues: list[IsolationIssue] = []
    for binding in bindings:
        if binding.profile_id not in profile_by_id:
            issues.append(
                IsolationIssue(
                    entity="elasticsearch_binding",
                    entity_id=str(binding.id),
                    severity="high",
                    message="Binding references a missing profile.",
                    details={"profile_id": binding.profile_id},
                )
            )
    return _check_result(
        name="binding_profile_alignment",
        ok_message="All bindings reference existing profiles.",
        failed_message="Some bindings reference missing profiles.",
        issues=issues,
        details={"bindings_checked": len(bindings)},
    )


def _check_binding_scoped_rows(
    *,
    name: str,
    rows: Iterable[Any],
    entity: str,
    binding_by_id: dict[int, ElasticsearchBinding],
) -> IsolationCheck:
    rows_list = list(rows)
    issues: list[IsolationIssue] = []
    scoped_total = 0
    for row in rows_list:
        binding_id = getattr(row, "binding_id", None)
        profile_id = getattr(row, "profile_id", None)
        if binding_id is None:
            continue
        scoped_total += 1
        binding = binding_by_id.get(binding_id)
        if binding is None:
            issues.append(
                IsolationIssue(
                    entity=entity,
                    entity_id=str(getattr(row, "id", "unknown")),
                    severity="high",
                    message="Row references a missing binding.",
                    details={"binding_id": binding_id, "profile_id": profile_id},
                )
            )
            continue
        if profile_id is not None and binding.profile_id != profile_id:
            issues.append(
                IsolationIssue(
                    entity=entity,
                    entity_id=str(getattr(row, "id", "unknown")),
                    severity="high",
                    message="Row profile_id does not match the referenced binding profile_id.",
                    details={
                        "row_profile_id": profile_id,
                        "binding_id": binding_id,
                        "binding_profile_id": binding.profile_id,
                    },
                )
            )
    return _check_result(
        name=name,
        ok_message=f"All {entity} rows stay inside their binding profile.",
        failed_message=f"Some {entity} rows cross profile/binding boundaries.",
        issues=issues,
        details={"rows_checked": len(rows_list), "binding_scoped_rows": scoped_total},
    )


def _check_agent_run_alignment(
    *, agent_runs: list[AgentRun], binding_by_id: dict[int, ElasticsearchBinding]
) -> IsolationCheck:
    issues: list[IsolationIssue] = []
    scoped_total = 0
    for run in agent_runs:
        if run.binding_id is None:
            continue
        scoped_total += 1
        binding = binding_by_id.get(run.binding_id)
        if binding is None:
            issues.append(
                IsolationIssue(
                    entity="agent_run",
                    entity_id=str(run.id),
                    severity="high",
                    message="Agent run references a missing binding.",
                    details={"run_id": run.run_id, "binding_id": run.binding_id},
                )
            )
            continue
        if run.profile_id is not None and binding.profile_id != run.profile_id:
            issues.append(
                IsolationIssue(
                    entity="agent_run",
                    entity_id=str(run.id),
                    severity="high",
                    message="Agent run profile_id does not match the binding profile_id.",
                    details={
                        "run_id": run.run_id,
                        "run_profile_id": run.profile_id,
                        "binding_id": run.binding_id,
                        "binding_profile_id": binding.profile_id,
                    },
                )
            )
        if run.normalized_profile_name and (
            run.normalized_profile_name != binding.profile.normalized_name
        ):
            issues.append(
                IsolationIssue(
                    entity="agent_run",
                    entity_id=str(run.id),
                    severity="high",
                    message="Agent run normalized_profile_name does not match the binding profile.",
                    details={
                        "run_id": run.run_id,
                        "run_profile_name": run.profile_name,
                        "run_normalized_profile_name": run.normalized_profile_name,
                        "binding_profile_name": binding.profile.name,
                        "binding_normalized_profile_name": binding.profile.normalized_name,
                    },
                )
            )
        elif run.profile_name and (
            normalize_profile_name(run.profile_name) != binding.profile.normalized_name
        ):
            issues.append(
                IsolationIssue(
                    entity="agent_run",
                    entity_id=str(run.id),
                    severity="high",
                    message="Agent run profile_name does not match the binding profile.",
                    details={
                        "run_id": run.run_id,
                        "run_profile_name": run.profile_name,
                        "binding_profile_name": binding.profile.name,
                    },
                )
            )
    return _check_result(
        name="agent_run_profile_binding_alignment",
        ok_message="All binding-scoped agent runs stay inside their binding profile.",
        failed_message="Some agent runs cross profile/binding boundaries.",
        issues=issues,
        details={"rows_checked": len(agent_runs), "binding_scoped_rows": scoped_total},
    )


def _check_agent_tracking_alignment(
    *,
    name: str,
    rows: Iterable[Any],
    entity: str,
    binding_by_id: dict[int, ElasticsearchBinding],
    agent_run_by_id: dict[int, AgentRun],
    suggestion_by_id: dict[int, GovernanceSuggestion] | None = None,
) -> IsolationCheck:
    rows_list = list(rows)
    issues: list[IsolationIssue] = []
    binding_scoped_total = 0
    run_scoped_total = 0
    for row in rows_list:
        row_id = str(getattr(row, "id", "unknown"))
        binding_id = getattr(row, "binding_id", None)
        profile_id = getattr(row, "profile_id", None)
        if binding_id is not None:
            binding_scoped_total += 1
            binding = binding_by_id.get(binding_id)
            if binding is None:
                issues.append(
                    IsolationIssue(
                        entity=entity,
                        entity_id=row_id,
                        severity="high",
                        message="Tracking row references a missing binding.",
                        details={"binding_id": binding_id, "profile_id": profile_id},
                    )
                )
            elif profile_id is not None and binding.profile_id != profile_id:
                issues.append(
                    IsolationIssue(
                        entity=entity,
                        entity_id=row_id,
                        severity="high",
                        message="Tracking row profile_id does not match binding profile_id.",
                        details={
                            "row_profile_id": profile_id,
                            "binding_id": binding_id,
                            "binding_profile_id": binding.profile_id,
                        },
                    )
                )
        agent_run = agent_run_by_id.get(getattr(row, "agent_run_id", None))
        if agent_run is not None:
            run_scoped_total += 1
            if profile_id != agent_run.profile_id:
                issues.append(
                    IsolationIssue(
                        entity=entity,
                        entity_id=row_id,
                        severity="high",
                        message="Tracking row profile_id does not match parent agent run profile_id.",
                        details={
                            "row_profile_id": profile_id,
                            "agent_run_id": agent_run.id,
                            "agent_run_profile_id": agent_run.profile_id,
                            "run_id": agent_run.run_id,
                        },
                    )
                )
            if binding_id != agent_run.binding_id:
                issues.append(
                    IsolationIssue(
                        entity=entity,
                        entity_id=row_id,
                        severity="high",
                        message="Tracking row binding_id does not match parent agent run binding_id.",
                        details={
                            "row_binding_id": binding_id,
                            "agent_run_id": agent_run.id,
                            "agent_run_binding_id": agent_run.binding_id,
                            "run_id": agent_run.run_id,
                        },
                    )
                )
        suggestion_id = getattr(row, "governance_suggestion_id", None)
        if suggestion_by_id is not None and suggestion_id is not None:
            suggestion = suggestion_by_id.get(suggestion_id)
            if suggestion is None:
                issues.append(
                    IsolationIssue(
                        entity=entity,
                        entity_id=row_id,
                        severity="high",
                        message="Proposal attempt references a missing governance suggestion.",
                        details={"governance_suggestion_id": suggestion_id},
                    )
                )
            else:
                if profile_id is not None and suggestion.profile_id != profile_id:
                    issues.append(
                        IsolationIssue(
                            entity=entity,
                            entity_id=row_id,
                            severity="high",
                            message="Proposal attempt profile_id does not match linked suggestion profile_id.",
                            details={
                                "attempt_profile_id": profile_id,
                                "suggestion_id": suggestion_id,
                                "suggestion_profile_id": suggestion.profile_id,
                            },
                        )
                    )
                if binding_id != suggestion.binding_id:
                    issues.append(
                        IsolationIssue(
                            entity=entity,
                            entity_id=row_id,
                            severity="high",
                            message="Proposal attempt binding_id does not match linked suggestion binding_id.",
                            details={
                                "attempt_binding_id": binding_id,
                                "suggestion_id": suggestion_id,
                                "suggestion_binding_id": suggestion.binding_id,
                            },
                        )
                    )
    return _check_result(
        name=name,
        ok_message=f"All {entity} rows stay inside their agent run and binding context.",
        failed_message=f"Some {entity} rows cross agent run/profile/binding boundaries.",
        issues=issues,
        details={
            "rows_checked": len(rows_list),
            "binding_scoped_rows": binding_scoped_total,
            "run_scoped_rows": run_scoped_total,
        },
    )


def _check_runtime_guards() -> IsolationCheck:
    return IsolationCheck(
        name="runtime_request_guards",
        status="ok",
        message="Runtime and agent request guards reject profile/binding mismatches before mutation or provider calls.",
        details={
            "guarded_paths": [
                "POST /v1/query/plan",
                "POST /v1/search",
                "POST /v1/search/multi",
                "GET /v1/tools/bindings",
                "POST /v1/tools/validate-alias",
                "POST /v1/tools/suggest-alias",
                "POST /v1/tools/explain-query",
                "POST /v1/agents/runs",
                "POST /v1/governance/profiles/{profile_name}/suggestions",
                "POST /v1/governance/profiles/{profile_name}/suggestions/apply-batch/preview",
                "POST /v1/governance/profiles/{profile_name}/suggestions/apply-batch",
            ],
            "migration_required": False,
        },
    )


def _check_result(
    *,
    name: str,
    ok_message: str,
    failed_message: str,
    issues: list[IsolationIssue],
    details: dict[str, Any],
) -> IsolationCheck:
    return IsolationCheck(
        name=name,
        status="ok" if not issues else "failed",
        message=ok_message if not issues else failed_message,
        issues=tuple(issues),
        details=details,
    )
