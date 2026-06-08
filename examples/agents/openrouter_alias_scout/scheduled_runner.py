"""Scheduled/worker-mode helpers for the OpenRouter alias scout example.

Orchestration stays dependency-light so the runner can be invoked from cron,
Airflow, Prefect, GitHub Actions, or Kubernetes CronJobs. The helpers in this
module only build plans, artifact manifests, and summarized cycle reports;
network calls stay explicit in the caller.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

try:  # pragma: no cover - import style depends on execution mode.
    from .artifact_standard import (
        ArtifactStandardConfig,
        write_artifact_manifest,
        write_standard_artifact,
    )
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from artifact_standard import (
        ArtifactStandardConfig,
        write_artifact_manifest,
        write_standard_artifact,
    )

JsonDict = dict[str, Any]


@dataclass(frozen=True)
class ScheduledRunnerConfig:
    """Config for a production-friendly single-run agent cycle."""

    artifacts_dir: Path
    artifact_standard: ArtifactStandardConfig | None = None
    cycle_name: str = "openrouter-alias-scout-cycle"
    default_mode: str = "offline"
    write_artifacts: bool = True
    append_tracking_ledger: bool = False
    live_llm_review_enabled: bool = False
    validate_proposals_enabled: bool = False
    submit_proposals_enabled: bool = False
    build_inbox_enabled: bool = True
    build_apply_plan_enabled: bool = True
    run_snapshot_evaluation_enabled: bool = True
    fail_on_needs_review: bool = False
    fail_on_errors: bool = True
    success_exit_code: int = 0
    needs_review_exit_code: int = 10
    error_exit_code: int = 2

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any] | None, *, base_dir: Path | None = None
    ) -> "ScheduledRunnerConfig":
        data = dict(value or {})
        raw_artifacts_dir = Path(str(data.get("artifacts_dir", "reports/scheduled")))
        if not raw_artifacts_dir.is_absolute() and base_dir is not None:
            raw_artifacts_dir = base_dir / raw_artifacts_dir
        artifact_standard = ArtifactStandardConfig.from_mapping(
            data.get("artifact_standard"), base_dir=base_dir
        ).with_overrides(root_dir=raw_artifacts_dir)
        return cls(
            artifacts_dir=raw_artifacts_dir,
            artifact_standard=artifact_standard,
            cycle_name=str(data.get("cycle_name", "openrouter-alias-scout-cycle")),
            default_mode=str(data.get("default_mode", "offline")),
            write_artifacts=bool(data.get("write_artifacts", True)),
            append_tracking_ledger=bool(data.get("append_tracking_ledger", False)),
            live_llm_review_enabled=bool(data.get("live_llm_review_enabled", False)),
            validate_proposals_enabled=bool(
                data.get("validate_proposals_enabled", False)
            ),
            submit_proposals_enabled=bool(data.get("submit_proposals_enabled", False)),
            build_inbox_enabled=bool(data.get("build_inbox_enabled", True)),
            build_apply_plan_enabled=bool(data.get("build_apply_plan_enabled", True)),
            run_snapshot_evaluation_enabled=bool(
                data.get("run_snapshot_evaluation_enabled", True)
            ),
            fail_on_needs_review=bool(data.get("fail_on_needs_review", False)),
            fail_on_errors=bool(data.get("fail_on_errors", True)),
            success_exit_code=int(data.get("success_exit_code", 0)),
            needs_review_exit_code=int(data.get("needs_review_exit_code", 10)),
            error_exit_code=int(data.get("error_exit_code", 2)),
        )

    def with_overrides(
        self,
        *,
        artifacts_dir: Path | None = None,
        live_llm_review_enabled: bool | None = None,
        validate_proposals_enabled: bool | None = None,
        submit_proposals_enabled: bool | None = None,
        append_tracking_ledger: bool | None = None,
        fail_on_needs_review: bool | None = None,
    ) -> "ScheduledRunnerConfig":
        next_artifacts_dir = artifacts_dir or self.artifacts_dir
        next_standard = (
            self.artifact_standard.with_overrides(root_dir=next_artifacts_dir)
            if self.artifact_standard is not None
            else ArtifactStandardConfig(root_dir=next_artifacts_dir)
        )
        return ScheduledRunnerConfig(
            artifacts_dir=next_artifacts_dir,
            artifact_standard=next_standard,
            cycle_name=self.cycle_name,
            default_mode=self.default_mode,
            write_artifacts=self.write_artifacts,
            append_tracking_ledger=(
                self.append_tracking_ledger
                if append_tracking_ledger is None
                else append_tracking_ledger
            ),
            live_llm_review_enabled=(
                self.live_llm_review_enabled
                if live_llm_review_enabled is None
                else live_llm_review_enabled
            ),
            validate_proposals_enabled=(
                self.validate_proposals_enabled
                if validate_proposals_enabled is None
                else validate_proposals_enabled
            ),
            submit_proposals_enabled=(
                self.submit_proposals_enabled
                if submit_proposals_enabled is None
                else submit_proposals_enabled
            ),
            build_inbox_enabled=self.build_inbox_enabled,
            build_apply_plan_enabled=self.build_apply_plan_enabled,
            run_snapshot_evaluation_enabled=self.run_snapshot_evaluation_enabled,
            fail_on_needs_review=(
                self.fail_on_needs_review
                if fail_on_needs_review is None
                else fail_on_needs_review
            ),
            fail_on_errors=self.fail_on_errors,
            success_exit_code=self.success_exit_code,
            needs_review_exit_code=self.needs_review_exit_code,
            error_exit_code=self.error_exit_code,
        )

    def to_plan(self) -> JsonDict:
        """Return a network-free plan for cron/Airflow style invocations."""

        return {
            "schema_version": "skeinrank.agent_scheduled_runner_plan.v1",
            "runner": "openrouter_alias_scout",
            "cycle_name": self.cycle_name,
            "default_mode": self.default_mode,
            "artifacts_dir": str(self.artifacts_dir),
            "write_artifacts": self.write_artifacts,
            "append_tracking_ledger": self.append_tracking_ledger,
            "live_llm_review_enabled": self.live_llm_review_enabled,
            "validate_proposals_enabled": self.validate_proposals_enabled,
            "submit_proposals_enabled": self.submit_proposals_enabled,
            "build_inbox_enabled": self.build_inbox_enabled,
            "build_apply_plan_enabled": self.build_apply_plan_enabled,
            "run_snapshot_evaluation_enabled": self.run_snapshot_evaluation_enabled,
            "fail_on_needs_review": self.fail_on_needs_review,
            "exit_codes": {
                "success": self.success_exit_code,
                "needs_review": self.needs_review_exit_code,
                "error": self.error_exit_code,
            },
            "artifact_standard": (
                self.artifact_standard
                or ArtifactStandardConfig(root_dir=self.artifacts_dir)
            ).to_plan(),
            "safe_defaults": {
                "openrouter_calls_by_default": False,
                "proposal_submission_by_default": False,
                "runtime_mutation_enabled": False,
                "snapshot_publish_enabled": False,
            },
            "orchestrators": [
                "cron",
                "Airflow BashOperator",
                "Prefect shell task",
                "GitHub Actions",
                "Kubernetes CronJob",
                "Docker Compose one-shot service",
            ],
        }


def make_scheduled_run_id(*, cycle_name: str, seed: str | None = None) -> str:
    """Build a stable-enough run id for one scheduled cycle."""

    if seed is None:
        seed = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    digest = sha256(f"{cycle_name}:{seed}".encode("utf-8")).hexdigest()[:8]
    safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in cycle_name)
    return f"{safe_name}-{seed}-{digest}"


def write_cycle_artifact(
    *, artifacts_dir: Path, run_id: str, name: str, payload: Mapping[str, Any]
) -> Path:
    """Write one JSON artifact using the standard layout and return its path."""

    metadata = write_standard_artifact(
        config=ArtifactStandardConfig(root_dir=artifacts_dir),
        run_id=run_id,
        name=name,
        payload=payload,
    )
    return Path(str(metadata["path"]))


def write_cycle_manifest(
    *,
    artifacts_dir: Path,
    run_id: str,
    artifacts: list[Mapping[str, Any]],
    cycle_report: Mapping[str, Any] | None = None,
) -> JsonDict:
    """Write the artifact manifest for one scheduled cycle."""

    return write_artifact_manifest(
        config=ArtifactStandardConfig(root_dir=artifacts_dir),
        run_id=run_id,
        artifacts=artifacts,
        cycle_report=cycle_report,
    )


def summarize_report(report: Mapping[str, Any] | None) -> JsonDict:
    """Extract a compact summary from an existing agent report."""

    if not report:
        return {"available": False}
    summary: JsonDict = {
        "available": True,
        "schema_version": report.get("schema_version"),
    }
    for key in (
        "candidate_summary",
        "source_quality",
        "llm_review_summary",
        "budget_cache_summary",
        "summary",
        "quality_gate",
        "evidence_quality",
        "llm_quality",
        "proposal_quality",
    ):
        if key in report:
            summary[key] = report[key]
    return summary


def build_scheduled_cycle_report(
    *,
    config: ScheduledRunnerConfig,
    run_id: str,
    artifacts: list[Mapping[str, Any]],
    steps: list[Mapping[str, Any]],
    reports: Mapping[str, Mapping[str, Any] | None],
) -> JsonDict:
    """Build the final scheduled/worker-mode cycle report."""

    errors = [step for step in steps if step.get("status") == "error"]
    needs_review = any(
        step.get("status") == "needs_review" or step.get("needs_review") is True
        for step in steps
    )
    if errors:
        status = "error"
        exit_code = (
            config.error_exit_code
            if config.fail_on_errors
            else config.success_exit_code
        )
    elif needs_review:
        status = "needs_review"
        exit_code = (
            config.needs_review_exit_code
            if config.fail_on_needs_review
            else config.success_exit_code
        )
    else:
        status = "completed"
        exit_code = config.success_exit_code

    return {
        "schema_version": "skeinrank.agent_scheduled_cycle_report.v1",
        "runner": "openrouter_alias_scout",
        "run_id": run_id,
        "cycle_name": config.cycle_name,
        "status": status,
        "recommended_exit_code": exit_code,
        "artifacts_dir": str(config.artifacts_dir),
        "artifacts": list(artifacts),
        "steps": list(steps),
        "reports": {name: summarize_report(report) for name, report in reports.items()},
        "safety": {
            "runtime_mutation_enabled": False,
            "snapshot_publish_enabled": False,
            "submit_proposals_enabled": config.submit_proposals_enabled,
            "live_llm_review_enabled": config.live_llm_review_enabled,
        },
    }
