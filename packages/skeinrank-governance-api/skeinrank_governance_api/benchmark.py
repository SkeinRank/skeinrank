"""Deterministic benchmark harness for headless agent workflow E2E checks.

The 48A benchmark is intentionally offline: it does not call OpenRouter and it
uses a dry-run Elasticsearch binding only as a runtime context. The goal is to
exercise the governed agent workflow end-to-end with repeatable sample data:

    seed dictionary -> record agent visits -> deterministic candidate reviews
    -> proposal attempts -> governed suggestions -> approve/apply -> snapshot
    -> runtime query checks -> JSON report
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from skeinrank_governance import create_all, create_session_factory
from skeinrank_governance.cli import (
    GovernanceCliError,
    add_alias,
    add_term,
    create_profile,
    get_profile,
    set_term_tags,
)
from skeinrank_governance.models import (
    AgentRun,
    CanonicalTerm,
    ElasticsearchBinding,
    GovernanceStopListEntry,
    GovernanceSuggestion,
    TermAlias,
    TerminologyProfile,
    normalize_profile_name,
    normalize_value,
    utc_now,
)
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .agent_candidate_observations import record_candidate_observation
from .agent_document_visits import record_document_visit
from .agent_llm_reviews import record_llm_review, record_proposal_attempt
from .agent_run_registry import create_agent_run, update_agent_run
from .config import GovernanceApiConfig
from .dependencies import create_engine_for_config
from .proposal_quality import validation_status
from .proposal_validation import build_proposal_validation_summary
from .runtime_snapshots import (
    alias_entries_from_snapshot,
    publish_binding_runtime_snapshot,
)

BENCHMARK_FORMAT_VERSION = "skeinrank.benchmark_report.v1"
DEFAULT_BENCHMARK_NAME = "platform_ops_v1"
DEFAULT_PROFILE_NAME = "platform_ops_benchmark"
DEFAULT_RUN_ID = "platform_ops_v1-eval"
DEFAULT_PRIOR_RUN_ID = "platform_ops_v1-prior"


@dataclass(frozen=True)
class BenchmarkPaths:
    """Resolved benchmark fixture paths."""

    root: Path
    corpus: Path
    seed_dictionary: Path
    expected_aliases: Path
    golden_queries: Path
    default_report: Path


def default_benchmark_dir() -> Path:
    """Return the default repository benchmark fixture directory."""

    return (
        Path(__file__).resolve().parents[3]
        / "examples"
        / "benchmarks"
        / "platform_ops_v1"
    )


def resolve_benchmark_paths(path: str | Path | None = None) -> BenchmarkPaths:
    """Resolve and validate benchmark fixture paths."""

    root = Path(path or default_benchmark_dir()).expanduser().resolve()
    paths = BenchmarkPaths(
        root=root,
        corpus=root / "corpus.jsonl",
        seed_dictionary=root / "seed_dictionary.json",
        expected_aliases=root / "expected_aliases.json",
        golden_queries=root / "golden_queries.jsonl",
        default_report=root / "reports" / "platform_ops_v1-report.json",
    )
    missing = [
        str(candidate)
        for candidate in (
            paths.corpus,
            paths.seed_dictionary,
            paths.expected_aliases,
            paths.golden_queries,
        )
        if not candidate.exists()
    ]
    if missing:
        raise BenchmarkError("Missing benchmark fixture files: " + ", ".join(missing))
    return paths


class BenchmarkError(RuntimeError):
    """Raised for user-facing benchmark errors."""


def reset_benchmark_state(
    session: Session,
    *,
    profile_name: str = DEFAULT_PROFILE_NAME,
) -> dict[str, Any]:
    """Delete benchmark-owned state for one profile."""

    normalized_profile = normalize_profile_name(profile_name)
    profile = session.scalar(
        select(TerminologyProfile).where(
            TerminologyProfile.normalized_name == normalized_profile
        )
    )
    deleted = False
    if profile is not None:
        session.delete(profile)
        deleted = True
    session.commit()
    return {
        "format_version": "skeinrank.benchmark.reset.v1",
        "status": "reset",
        "profile_name": profile_name,
        "profile_deleted": deleted,
    }


def seed_benchmark_state(
    session: Session,
    *,
    paths: BenchmarkPaths | None = None,
    reset_first: bool = False,
) -> dict[str, Any]:
    """Load the deterministic benchmark dictionary into the governance DB."""

    paths = paths or resolve_benchmark_paths()
    seed_payload = _read_json(paths.seed_dictionary)
    profile_payload = _require_mapping(seed_payload.get("profile"), "profile")
    binding_payload = _require_mapping(seed_payload.get("binding"), "binding")
    profile_name = str(profile_payload.get("name") or DEFAULT_PROFILE_NAME)

    if reset_first:
        reset_benchmark_state(session, profile_name=profile_name)

    profile = _get_or_create_profile(
        session,
        name=profile_name,
        description=str(profile_payload.get("description") or "") or None,
    )
    terms_created = 0
    aliases_created = 0
    tags_set = 0
    for term_payload in _require_list(seed_payload.get("terms"), "terms"):
        term_payload = _require_mapping(term_payload, "terms[]")
        term = _get_or_create_term(
            session,
            profile_name=profile.name,
            canonical_value=str(term_payload["canonical_value"]),
            slot=str(term_payload["slot"]),
            tags=[str(value) for value in term_payload.get("tags") or []],
        )
        if term.id is None:
            session.flush()
        if getattr(term, "_benchmark_created", False):
            terms_created += 1
        tags = [str(value) for value in term_payload.get("tags") or []]
        set_term_tags(session, term, tags)
        tags_set += len(tags)
        for alias_value in term_payload.get("aliases") or []:
            if _get_alias(session, profile, str(alias_value)) is None:
                add_alias(
                    session,
                    profile.name,
                    term.canonical_value,
                    str(alias_value),
                    actor="benchmark",
                )
                aliases_created += 1

    stop_entries_created = _seed_stop_list(
        session,
        profile=profile,
        entries=_require_list(seed_payload.get("stop_list", []), "stop_list"),
    )
    binding = _get_or_create_binding(session, profile=profile, payload=binding_payload)
    session.commit()

    return {
        "format_version": "skeinrank.benchmark.seed.v1",
        "status": "seeded",
        "benchmark_name": seed_payload.get("benchmark_name", DEFAULT_BENCHMARK_NAME),
        "profile_name": profile.name,
        "binding_id": binding.id,
        "terms_total": _count_profile_terms(session, profile),
        "aliases_total": _count_profile_aliases(session, profile),
        "terms_created": terms_created,
        "aliases_created": aliases_created,
        "tags_set": tags_set,
        "stop_entries_created": stop_entries_created,
    }


def run_benchmark_evaluation(
    session: Session,
    *,
    paths: BenchmarkPaths | None = None,
    run_id: str = DEFAULT_RUN_ID,
    prior_run_id: str = DEFAULT_PRIOR_RUN_ID,
    reset_runs: bool = True,
    apply_passed_proposals: bool = True,
) -> dict[str, Any]:
    """Run the deterministic headless agent workflow benchmark and return a report."""

    paths = paths or resolve_benchmark_paths()
    seed_payload = _read_json(paths.seed_dictionary)
    expected_payload = _read_json(paths.expected_aliases)
    corpus = _read_jsonl(paths.corpus)
    golden_queries = _read_jsonl(paths.golden_queries)
    profile_name = str(
        (_require_mapping(seed_payload.get("profile"), "profile"))["name"]
    )

    profile = _get_profile_or_error(session, profile_name)
    binding = _get_binding_or_error(session, profile)
    if reset_runs:
        _delete_agent_run_if_exists(session, run_id)
        _delete_agent_run_if_exists(session, prior_run_id)
        session.commit()

    prior_run = create_agent_run(
        session,
        run_id=prior_run_id,
        agent_name="deterministic_benchmark_agent",
        agent_version="48A",
        status="running",
        trigger_type="test",
        profile_name=profile.name,
        binding_id=binding.id,
        openrouter_model="offline/deterministic",
        prompt_version="benchmark-v1",
        workflow_engine="headless_benchmark_fixture",
        config_hash="platform_ops_v1",
        requested_by="benchmark",
    )
    session.flush()
    _record_prior_visits(session, prior_run_id=prior_run.run_id, corpus=corpus)
    update_agent_run(prior_run, status="succeeded", summary_json={"stage": "prior"})
    session.flush()

    agent_run = create_agent_run(
        session,
        run_id=run_id,
        agent_name="deterministic_benchmark_agent",
        agent_version="48A",
        status="running",
        trigger_type="test",
        profile_name=profile.name,
        binding_id=binding.id,
        openrouter_model="offline/deterministic",
        prompt_version="benchmark-v1",
        workflow_engine="headless_benchmark_fixture",
        config_hash="platform_ops_v1",
        requested_by="benchmark",
    )
    session.flush()

    observations = []
    reviews = []
    proposal_attempts = []
    suggestions = []
    visit_status_counts: Counter[str] = Counter()
    validation_status_counts: Counter[str] = Counter()
    source_visit_statuses: dict[str, str] = {}
    idempotent_noops = 0

    for document in corpus:
        visit = record_document_visit(
            session,
            run_id=agent_run.run_id,
            source_id=str(document["source_id"]),
            source_type=str(document.get("source_type") or "document"),
            index_name=binding.index_name,
            content=_document_text(document),
            metadata_json={
                "title": document.get("title"),
                "benchmark": DEFAULT_BENCHMARK_NAME,
            },
        )
        session.flush()
        visit_status_counts[visit.visit_status] += 1
        source_visit_statuses[visit.source_id] = visit.visit_status
        if not visit.should_scan:
            continue

        for candidate in _require_list(document.get("candidates", []), "candidates"):
            candidate = _require_mapping(candidate, "candidates[]")
            evidence_text = str(candidate.get("evidence") or document.get("body") or "")
            observation = record_candidate_observation(
                session,
                run_id=agent_run.run_id,
                document_visit_id=visit.id,
                candidate_alias=str(candidate["alias"]),
                possible_canonical=str(candidate.get("canonical") or ""),
                slot=str(candidate.get("slot") or "TECHNOLOGY"),
                observation_status="reviewed",
                discovery_score=float(candidate.get("confidence") or 0.0),
                weighted_count=1.0,
                document_frequency=1,
                discovery_reasons=[
                    "fixture_candidate",
                    str(candidate.get("expected_action") or ""),
                ],
                candidate_pack={"expected_action": candidate.get("expected_action")},
                metadata_json={"source_id": document.get("source_id")},
                evidence_windows=[
                    {
                        "source_id": document.get("source_id"),
                        "source_type": document.get("source_type") or "document",
                        "field": "body",
                        "text": evidence_text,
                        "metadata": {"title": document.get("title")},
                    }
                ],
            )
            session.flush()
            observations.append(observation)
            expected_action = str(candidate.get("expected_action") or "propose")
            review_status = "proposed" if expected_action != "blocked" else "rejected"
            review = record_llm_review(
                session,
                run_id=agent_run.run_id,
                candidate_observation_id=observation.id,
                candidate_alias=observation.candidate_alias,
                possible_canonical=observation.possible_canonical,
                slot=observation.slot,
                review_status=review_status,
                action="submit_proposal"
                if review_status == "proposed"
                else "reject_candidate",
                confidence=observation.discovery_score,
                model="offline/deterministic",
                prompt_version="benchmark-v1",
                usage={"llm_calls": 0, "tokens": 0},
                judgment={"expected_action": expected_action, "fixture": True},
                raw_response={"source": "benchmark_fixture"},
            )
            session.flush()
            reviews.append(review)

            validation_summary = build_proposal_validation_summary(
                session,
                profile,
                suggestion_type="alias",
                canonical_value=observation.possible_canonical or "",
                alias_value=observation.candidate_alias,
                slot=observation.slot or "TECHNOLOGY",
                confidence=observation.discovery_score,
                proposal_source_type="agent",
                proposal_source_name="deterministic_benchmark_agent",
                idempotency_key=_proposal_idempotency_key(run_id, observation),
                source_payload={
                    "benchmark_name": DEFAULT_BENCHMARK_NAME,
                    "source_id": document.get("source_id"),
                    "expected_action": expected_action,
                },
            )
            status = validation_status(validation_summary)
            validation_status_counts[status] += 1
            active_alias = _get_alias(session, profile, observation.candidate_alias)
            if (
                active_alias is not None
                and active_alias.term.normalized_value
                == normalize_value(observation.possible_canonical or "")
            ):
                idempotent_noops += 1
                attempt_status = "idempotent_existing_alias"
                suggestion = None
            elif status == "blocked" or expected_action == "blocked":
                attempt_status = "validation_blocked"
                suggestion = None
            else:
                suggestion = _create_benchmark_suggestion(
                    session,
                    profile=profile,
                    binding=binding,
                    observation=observation,
                    validation_summary=validation_summary,
                    source_id=str(document.get("source_id") or ""),
                    idempotency_key=_proposal_idempotency_key(run_id, observation),
                )
                suggestions.append(suggestion)
                attempt_status = "created"
            session.flush()
            attempt = record_proposal_attempt(
                session,
                run_id=agent_run.run_id,
                candidate_observation_id=observation.id,
                llm_review_id=review.id,
                governance_suggestion_id=suggestion.id
                if suggestion is not None
                else None,
                alias_value=observation.candidate_alias,
                canonical_value=observation.possible_canonical,
                slot=observation.slot,
                attempt_status=attempt_status,
                validation_status=status,
                validation_category=status,
                confidence=observation.discovery_score,
                idempotency_key=_proposal_idempotency_key(run_id, observation),
                submitted=suggestion is not None,
                proposal_source_type="agent",
                proposal_source_name="deterministic_benchmark_agent",
                validation_response=validation_summary,
                submission_response={
                    "created": suggestion is not None,
                    "suggestion_id": suggestion.id if suggestion is not None else None,
                },
                source_payload={"source_id": document.get("source_id")},
            )
            proposal_attempts.append(attempt)
            session.flush()

    approved_suggestion_ids: list[int] = []
    if apply_passed_proposals:
        approved_suggestion_ids = _approve_and_apply_suggestions(session, suggestions)
    snapshot_payload = publish_binding_runtime_snapshot(
        session,
        binding,
        snapshot_version=f"{DEFAULT_BENCHMARK_NAME}@{run_id}",
    )
    runtime_checks = _evaluate_runtime_queries(
        snapshot_payload=snapshot_payload,
        golden_queries=golden_queries,
    )
    report = _build_report(
        expected_payload=expected_payload,
        corpus=corpus,
        profile=profile,
        binding=binding,
        run_id=run_id,
        prior_run_id=prior_run_id,
        visit_status_counts=visit_status_counts,
        source_visit_statuses=source_visit_statuses,
        observations=observations,
        reviews=reviews,
        proposal_attempts=proposal_attempts,
        suggestions=suggestions,
        approved_suggestion_ids=approved_suggestion_ids,
        validation_status_counts=validation_status_counts,
        idempotent_noops=idempotent_noops,
        snapshot_payload=snapshot_payload,
        runtime_checks=runtime_checks,
    )
    update_agent_run(
        agent_run,
        status="succeeded" if report["status"] == "passed" else "needs_review",
        summary_json={
            "benchmark_name": DEFAULT_BENCHMARK_NAME,
            "status": report["status"],
            "scores": report["scores"],
            "counts": report["counts"],
        },
        report_uri=str(paths.default_report),
    )
    session.commit()
    return report


def write_report(report: dict[str, Any], path: str | Path) -> Path:
    """Write a benchmark report as pretty JSON."""

    report_path = Path(path).expanduser().resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report_path


def _record_prior_visits(
    session: Session,
    *,
    prior_run_id: str,
    corpus: list[dict[str, Any]],
) -> None:
    for document in corpus:
        if not document.get("previously_seen"):
            continue
        previous_body = document.get("previous_body")
        prior_document = dict(document)
        if previous_body is not None:
            prior_document["body"] = previous_body
        record_document_visit(
            session,
            run_id=prior_run_id,
            source_id=str(document["source_id"]),
            source_type=str(document.get("source_type") or "document"),
            content=_document_text(prior_document),
            metadata_json={"title": document.get("title"), "prior": True},
        )


def _create_benchmark_suggestion(
    session: Session,
    *,
    profile: TerminologyProfile,
    binding: ElasticsearchBinding,
    observation: Any,
    validation_summary: dict[str, Any],
    source_id: str,
    idempotency_key: str,
) -> GovernanceSuggestion:
    existing = session.scalar(
        select(GovernanceSuggestion).where(
            GovernanceSuggestion.profile_id == profile.id,
            GovernanceSuggestion.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        return existing
    suggestion = GovernanceSuggestion(
        profile=profile,
        suggestion_type="alias",
        canonical_value=observation.possible_canonical or "",
        alias_value=observation.candidate_alias,
        slot=observation.slot or "TECHNOLOGY",
        description="Created by the deterministic headless benchmark harness.",
        confidence=observation.discovery_score,
        source="discovery",
        context=f"benchmark source_id={source_id}",
        binding_id=binding.id,
        proposal_source_type="agent",
        proposal_source_name="deterministic_benchmark_agent",
        idempotency_key=idempotency_key,
        source_payload_json={
            "benchmark_name": DEFAULT_BENCHMARK_NAME,
            "source_id": source_id,
            "candidate_observation_id": observation.id,
        },
        validation_summary_json=validation_summary,
        status="pending",
        created_by="benchmark",
        evidence_snapshot={
            "source_id": source_id,
            "candidate_observation_id": observation.id,
        },
    )
    session.add(suggestion)
    return suggestion


def _approve_and_apply_suggestions(
    session: Session,
    suggestions: list[GovernanceSuggestion],
) -> list[int]:
    approved: list[int] = []
    for suggestion in suggestions:
        status = validation_status(suggestion.validation_summary_json)
        if status == "blocked":
            continue
        alias = _get_alias(session, suggestion.profile, suggestion.alias_value or "")
        if alias is None:
            try:
                alias = add_alias(
                    session,
                    suggestion.profile.name,
                    suggestion.canonical_value,
                    suggestion.alias_value or "",
                    confidence=suggestion.confidence,
                    actor="benchmark",
                )
            except GovernanceCliError:
                continue
        suggestion.status = "approved"
        suggestion.reviewed_by = "benchmark"
        suggestion.review_comment = "Auto-approved by deterministic benchmark fixture."
        suggestion.reviewed_at = utc_now()
        suggestion.alias_id = alias.id
        suggestion.term_id = alias.term_id
        approved.append(suggestion.id)
    return approved


def _build_report(
    *,
    expected_payload: dict[str, Any],
    corpus: list[dict[str, Any]],
    profile: TerminologyProfile,
    binding: ElasticsearchBinding,
    run_id: str,
    prior_run_id: str,
    visit_status_counts: Counter[str],
    source_visit_statuses: dict[str, str],
    observations: list[Any],
    reviews: list[Any],
    proposal_attempts: list[Any],
    suggestions: list[GovernanceSuggestion],
    approved_suggestion_ids: list[int],
    validation_status_counts: Counter[str],
    idempotent_noops: int,
    snapshot_payload: dict[str, Any],
    runtime_checks: list[dict[str, Any]],
) -> dict[str, Any]:
    expected_new = {
        normalize_value(item["alias"]): normalize_value(item["canonical"])
        for item in _require_list(
            expected_payload.get("expected_new_aliases"), "expected_new_aliases"
        )
    }
    runtime_aliases = {
        entry.normalized_alias: entry.normalized_canonical
        for entry in alias_entries_from_snapshot(snapshot_payload)
    }
    found_expected = {
        alias: canonical
        for alias, canonical in expected_new.items()
        if runtime_aliases.get(alias) == canonical
    }
    missing_expected = sorted(set(expected_new) - set(found_expected))
    blocked_expected = {
        normalize_value(value)
        for value in _require_list(
            expected_payload.get("expected_blocked_aliases"), "expected_blocked_aliases"
        )
    }
    blocked_observed = {
        attempt.normalized_alias
        for attempt in proposal_attempts
        if attempt.attempt_status == "validation_blocked"
    }
    missing_blocked = sorted(blocked_expected - blocked_observed)
    expected_skipped = set(expected_payload.get("expected_skipped_sources") or [])
    skipped_sources = {
        source_id
        for source_id in expected_skipped
        if source_visit_statuses.get(source_id) == "unchanged_seen"
    }
    expected_changed = set(
        expected_payload.get("expected_content_changed_sources") or []
    )
    changed_sources = {
        source_id
        for source_id in expected_changed
        if source_visit_statuses.get(source_id) == "content_changed"
    }
    changed_ok = len(changed_sources) == len(expected_changed)
    runtime_accuracy = _ratio(
        sum(1 for item in runtime_checks if item["status"] == "passed"),
        len(runtime_checks),
    )
    expected_alias_recall = _ratio(len(found_expected), len(expected_new))
    unexpected_created = sorted(
        {
            suggestion.normalized_alias
            for suggestion in suggestions
            if suggestion.normalized_alias not in expected_new
        }
    )
    checks = [
        _check_item(
            "expected_aliases_found",
            not missing_expected,
            "Expected benchmark aliases are present in the runtime snapshot.",
            {"missing": missing_expected, "found": sorted(found_expected)},
        ),
        _check_item(
            "blocked_aliases_not_submitted",
            not missing_blocked,
            "Stop-list/noise candidates are blocked before submission.",
            {
                "missing_blocked": missing_blocked,
                "blocked_observed": sorted(blocked_observed),
            },
        ),
        _check_item(
            "unchanged_documents_skipped",
            len(skipped_sources) == len(expected_skipped),
            "Previously seen unchanged documents are skipped.",
            {"expected": sorted(expected_skipped), "observed": sorted(skipped_sources)},
        ),
        _check_item(
            "changed_documents_revisited",
            changed_ok,
            "Changed documents are revisited by the agent workflow.",
            {
                "expected": sorted(expected_changed),
                "observed": sorted(changed_sources),
                "source_visit_statuses": source_visit_statuses,
            },
        ),
        _check_item(
            "runtime_queries_match",
            runtime_accuracy == 1.0,
            "Golden runtime queries match expected canonical values.",
            {"runtime_checks": runtime_checks},
        ),
        _check_item(
            "no_unexpected_proposals",
            not unexpected_created,
            "Benchmark did not create unexpected proposal aliases.",
            {"unexpected_created": unexpected_created},
        ),
    ]
    report_status = (
        "passed" if all(item["status"] == "passed" for item in checks) else "failed"
    )
    return {
        "format_version": BENCHMARK_FORMAT_VERSION,
        "benchmark_name": DEFAULT_BENCHMARK_NAME,
        "status": report_status,
        "generated_at": utc_now().isoformat(),
        "profile_name": profile.name,
        "binding_id": binding.id,
        "run_id": run_id,
        "prior_run_id": prior_run_id,
        "counts": {
            "documents_total": len(corpus),
            "visit_statuses": dict(sorted(visit_status_counts.items())),
            "candidate_observations": len(observations),
            "evidence_windows": sum(
                item.evidence_windows_found for item in observations
            ),
            "llm_reviews": len(reviews),
            "proposal_attempts": len(proposal_attempts),
            "suggestions_created": len(suggestions),
            "suggestions_approved": len(approved_suggestion_ids),
            "validation_statuses": dict(sorted(validation_status_counts.items())),
            "idempotent_noops": idempotent_noops,
            "runtime_aliases_total": len(runtime_aliases),
        },
        "scores": {
            "expected_alias_recall": expected_alias_recall,
            "runtime_canonicalization_accuracy": runtime_accuracy,
            "unexpected_proposals": len(unexpected_created),
            "unchanged_skip_rate": _ratio(
                visit_status_counts.get("unchanged_seen", 0),
                max(1, len(expected_skipped)),
            ),
        },
        "checks": checks,
        "runtime_checks": runtime_checks,
        "approved_suggestion_ids": approved_suggestion_ids,
        "snapshot": {
            "version": snapshot_payload.get("version"),
            "checksum": snapshot_payload.get("checksum"),
            "alias_entries_total": len(runtime_aliases),
        },
    }


def _evaluate_runtime_queries(
    *,
    snapshot_payload: dict[str, Any],
    golden_queries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    alias_entries = alias_entries_from_snapshot(snapshot_payload)
    results: list[dict[str, Any]] = []
    for query in golden_queries:
        text = normalize_value(str(query.get("query") or ""))
        matched = sorted(
            {
                entry.normalized_canonical
                for entry in alias_entries
                if _contains_token(text, entry.normalized_alias)
            }
        )
        expected = sorted(
            normalize_value(value) for value in query.get("expected_canonicals") or []
        )
        missing = sorted(set(expected) - set(matched))
        results.append(
            {
                "query": query.get("query"),
                "expected_canonicals": expected,
                "matched_canonicals": matched,
                "missing_canonicals": missing,
                "status": "passed" if not missing else "failed",
                "description": query.get("description"),
            }
        )
    return results


def _contains_token(text: str, token: str) -> bool:
    padded = f" {text} "
    return f" {token} " in padded


def _check_item(
    name: str,
    passed: bool,
    message: str,
    details: dict[str, Any],
) -> dict[str, Any]:
    return {
        "name": name,
        "status": "passed" if passed else "failed",
        "message": message,
        "details": details,
    }


def _proposal_idempotency_key(run_id: str, observation: Any) -> str:
    return "benchmark:{run_id}:{alias}:{canonical}".format(
        run_id=run_id,
        alias=observation.normalized_alias,
        canonical=observation.normalized_canonical or "none",
    )


def _document_text(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": document.get("title") or "",
        "body": document.get("body") or "",
    }


def _get_or_create_profile(
    session: Session,
    *,
    name: str,
    description: str | None,
) -> TerminologyProfile:
    profile = session.scalar(
        select(TerminologyProfile).where(
            TerminologyProfile.normalized_name == normalize_profile_name(name)
        )
    )
    if profile is not None:
        profile.description = description
        return profile
    return create_profile(session, name, description=description, actor="benchmark")


def _get_or_create_term(
    session: Session,
    *,
    profile_name: str,
    canonical_value: str,
    slot: str,
    tags: list[str],
) -> CanonicalTerm:
    profile = get_profile(session, profile_name)
    term = session.scalar(
        select(CanonicalTerm).where(
            CanonicalTerm.profile_id == profile.id,
            CanonicalTerm.normalized_value == normalize_value(canonical_value),
        )
    )
    if term is not None:
        term.slot = slot
        term._benchmark_created = False  # type: ignore[attr-defined]
        return term
    term = add_term(
        session,
        profile_name,
        canonical_value,
        slot=slot,
        tags=tags,
        actor="benchmark",
    )
    term._benchmark_created = True  # type: ignore[attr-defined]
    return term


def _seed_stop_list(
    session: Session,
    *,
    profile: TerminologyProfile,
    entries: list[Any],
) -> int:
    created = 0
    for raw_entry in entries:
        entry = _require_mapping(raw_entry, "stop_list[]")
        value = str(entry["value"])
        target = str(entry.get("target") or "both").strip().lower()
        existing = session.scalar(
            select(GovernanceStopListEntry).where(
                GovernanceStopListEntry.profile_id == profile.id,
                GovernanceStopListEntry.target == target,
                GovernanceStopListEntry.normalized_value == normalize_value(value),
            )
        )
        if existing is not None:
            existing.reason = str(entry.get("reason") or "") or None
            existing.is_active = True
            continue
        session.add(
            GovernanceStopListEntry(
                profile=profile,
                value=value,
                target=target,
                reason=str(entry.get("reason") or "") or None,
                is_active=True,
            )
        )
        created += 1
    return created


def _get_or_create_binding(
    session: Session,
    *,
    profile: TerminologyProfile,
    payload: dict[str, Any],
) -> ElasticsearchBinding:
    name = str(payload["name"])
    binding = session.scalar(
        select(ElasticsearchBinding).where(
            ElasticsearchBinding.normalized_name == normalize_profile_name(name)
        )
    )
    if binding is None:
        binding = ElasticsearchBinding(profile=profile, name=name)
        session.add(binding)
    binding.profile = profile
    binding.description = str(payload.get("description") or "") or None
    binding.provider = "elasticsearch"
    binding.index_name = str(payload["index_name"])
    binding.text_fields = [
        str(field) for field in payload.get("text_fields") or ["body"]
    ]
    binding.target_field = str(payload.get("target_field") or "skeinrank_terms")
    binding.filter_field = str(payload.get("filter_field") or "") or None
    binding.filter_value = str(payload.get("filter_value") or "") or None
    binding.mode = str(payload.get("mode") or "dry_run")
    binding.write_strategy = str(payload.get("write_strategy") or "reindex_alias_swap")
    binding.is_enabled = True
    session.flush()
    return binding


def _delete_agent_run_if_exists(session: Session, run_id: str) -> None:
    run = session.scalar(select(AgentRun).where(AgentRun.run_id == run_id))
    if run is not None:
        session.delete(run)
        session.flush()


def _get_profile_or_error(session: Session, profile_name: str) -> TerminologyProfile:
    profile = session.scalar(
        select(TerminologyProfile).where(
            TerminologyProfile.normalized_name == normalize_profile_name(profile_name)
        )
    )
    if profile is None:
        raise BenchmarkError(
            f"Benchmark profile {profile_name!r} is missing. Run seed first."
        )
    return profile


def _get_binding_or_error(
    session: Session,
    profile: TerminologyProfile,
) -> ElasticsearchBinding:
    binding = session.scalar(
        select(ElasticsearchBinding)
        .where(ElasticsearchBinding.profile_id == profile.id)
        .order_by(ElasticsearchBinding.id)
    )
    if binding is None:
        raise BenchmarkError(
            f"Benchmark binding for profile {profile.name!r} is missing. Run seed first."
        )
    return binding


def _get_alias(
    session: Session,
    profile: TerminologyProfile,
    alias_value: str,
) -> TermAlias | None:
    return session.scalar(
        select(TermAlias).where(
            TermAlias.profile_id == profile.id,
            TermAlias.normalized_alias == normalize_value(alias_value),
        )
    )


def _count_profile_terms(session: Session, profile: TerminologyProfile) -> int:
    return len(
        list(
            session.scalars(
                select(CanonicalTerm).where(CanonicalTerm.profile_id == profile.id)
            )
        )
    )


def _count_profile_aliases(session: Session, profile: TerminologyProfile) -> int:
    return len(
        list(
            session.scalars(select(TermAlias).where(TermAlias.profile_id == profile.id))
        )
    )


def _ratio(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 1.0
    return round(float(numerator) / float(denominator), 4)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BenchmarkError(f"Invalid JSON in {path}: {exc}") from exc
    return _require_mapping(payload, str(path))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise BenchmarkError(
                f"Invalid JSONL in {path}:{line_number}: {exc}"
            ) from exc
        items.append(_require_mapping(payload, f"{path}:{line_number}"))
    return items


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BenchmarkError(f"{name} must be a JSON object")
    return value


def _require_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise BenchmarkError(f"{name} must be a JSON array")
    return value


def _engine_from_database_url(database_url: str | None) -> Engine:
    config = (
        GovernanceApiConfig(database_url=database_url)
        if database_url
        else GovernanceApiConfig.from_env()
    )
    return create_engine_for_config(config)


def _run_with_session(
    database_url: str | None,
    callback,
    *,
    create_tables: bool = True,
) -> Any:
    engine = _engine_from_database_url(database_url)
    if create_tables:
        create_all(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        return callback(session)


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the benchmark CLI argument parser."""

    parser = argparse.ArgumentParser(
        prog="skeinrank-governance-benchmark",
        description="Run deterministic SkeinRank headless benchmark workflows.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Governance database URL. Defaults to SKEINRANK_GOVERNANCE_API_DATABASE_URL/env config.",
    )
    parser.add_argument(
        "--benchmark-dir",
        default=None,
        help="Benchmark fixture directory. Defaults to examples/benchmarks/platform_ops_v1.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    reset_parser = subparsers.add_parser("reset", help="Delete benchmark-owned state.")
    reset_parser.add_argument("--profile-name", default=DEFAULT_PROFILE_NAME)

    seed_parser = subparsers.add_parser(
        "seed", help="Seed benchmark dictionary and binding."
    )
    seed_parser.add_argument(
        "--reset", action="store_true", help="Reset benchmark profile before seeding."
    )

    eval_parser = subparsers.add_parser(
        "eval", help="Run deterministic agent workflow evaluation."
    )
    eval_parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    eval_parser.add_argument("--prior-run-id", default=DEFAULT_PRIOR_RUN_ID)
    eval_parser.add_argument("--out", default=None, help="Optional report output path.")
    eval_parser.add_argument(
        "--no-apply",
        action="store_true",
        help="Record proposals but do not approve/apply them before runtime checks.",
    )
    eval_parser.add_argument(
        "--keep-runs",
        action="store_true",
        help="Do not delete previous benchmark agent runs with the same ids.",
    )

    report_parser = subparsers.add_parser(
        "report", help="Print the latest benchmark report file."
    )
    report_parser.add_argument("--file", default=None)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    """CLI entrypoint for deterministic benchmark operations."""

    parser = build_arg_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        paths = resolve_benchmark_paths(args.benchmark_dir)
        if args.command == "reset":
            payload = _run_with_session(
                args.database_url,
                lambda session: reset_benchmark_state(
                    session, profile_name=args.profile_name
                ),
            )
            _print_json(payload)
            return 0
        if args.command == "seed":
            payload = _run_with_session(
                args.database_url,
                lambda session: seed_benchmark_state(
                    session, paths=paths, reset_first=args.reset
                ),
            )
            _print_json(payload)
            return 0
        if args.command == "eval":
            report = _run_with_session(
                args.database_url,
                lambda session: run_benchmark_evaluation(
                    session,
                    paths=paths,
                    run_id=args.run_id,
                    prior_run_id=args.prior_run_id,
                    reset_runs=not args.keep_runs,
                    apply_passed_proposals=not args.no_apply,
                ),
            )
            out = (
                Path(args.out).expanduser().resolve()
                if args.out
                else paths.default_report
            )
            write_report(report, out)
            _print_json(
                {
                    "status": report["status"],
                    "report": str(out),
                    "scores": report["scores"],
                    "counts": report["counts"],
                }
            )
            return 0 if report["status"] == "passed" else 1
        if args.command == "report":
            report_path = (
                Path(args.file).expanduser().resolve()
                if args.file
                else paths.default_report
            )
            if not report_path.exists():
                raise BenchmarkError(f"Benchmark report not found: {report_path}")
            print(report_path.read_text(encoding="utf-8"), end="")
            return 0
        parser.error(f"Unsupported command: {args.command}")
        return 2
    except BenchmarkError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
