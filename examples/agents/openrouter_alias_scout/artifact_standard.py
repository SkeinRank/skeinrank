"""Standard report/artifact layout for the OpenRouter alias scout.

The module provides a small, dependency-free artifact contract that scheduled
runs, integration smokes, and external orchestrators can rely on:

    reports/<run_id>/
      manifest.json
      reports/<artifact-name>.json

The module intentionally only writes JSON files. It does not call OpenRouter,
Elasticsearch, or the SkeinRank API, and it never mutates runtime state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Sequence

JsonDict = dict[str, Any]


@dataclass(frozen=True)
class ArtifactStandardConfig:
    """Config for normalized agent report/artifact folders."""

    root_dir: Path
    reports_subdir: str = "reports"
    manifest_filename: str = "manifest.json"
    summary_filename: str = "run_summary.json"
    layout_version: str = "skeinrank.agent_artifacts_layout.v1"
    write_manifest: bool = True
    include_checksums: bool = True

    @classmethod
    def from_mapping(
        cls, raw: Mapping[str, Any] | None, *, base_dir: Path | None = None
    ) -> "ArtifactStandardConfig":
        data = dict(raw or {})
        raw_root = Path(str(data.get("root_dir", "reports")))
        if base_dir is not None and not raw_root.is_absolute():
            raw_root = base_dir / raw_root
        return cls(
            root_dir=raw_root,
            reports_subdir=str(data.get("reports_subdir", "reports")),
            manifest_filename=str(data.get("manifest_filename", "manifest.json")),
            summary_filename=str(data.get("summary_filename", "run_summary.json")),
            layout_version=str(
                data.get("layout_version", "skeinrank.agent_artifacts_layout.v1")
            ),
            write_manifest=bool(data.get("write_manifest", True)),
            include_checksums=bool(data.get("include_checksums", True)),
        )

    def with_overrides(
        self, *, root_dir: Path | None = None
    ) -> "ArtifactStandardConfig":
        return ArtifactStandardConfig(
            root_dir=root_dir or self.root_dir,
            reports_subdir=self.reports_subdir,
            manifest_filename=self.manifest_filename,
            summary_filename=self.summary_filename,
            layout_version=self.layout_version,
            write_manifest=self.write_manifest,
            include_checksums=self.include_checksums,
        )

    def to_plan(self) -> JsonDict:
        """Return a network-free plan describing the artifact contract."""

        return {
            "schema_version": "skeinrank.agent_artifacts_standard_plan.v1",
            "runner": "openrouter_alias_scout",
            "layout_version": self.layout_version,
            "root_dir": str(self.root_dir),
            "run_layout": f"{self.root_dir}/<run_id>/",
            "manifest_path": f"<run_id>/{self.manifest_filename}",
            "reports_path": f"<run_id>/{self.reports_subdir}/<artifact>.json",
            "summary_path": f"<run_id>/{self.summary_filename}",
            "write_manifest": self.write_manifest,
            "include_checksums": self.include_checksums,
            "safe_defaults": {
                "network_calls": False,
                "runtime_mutation_enabled": False,
                "snapshot_publish_enabled": False,
            },
            "canonical_artifacts": [
                "demo_report",
                "tracking_report",
                "llm_review_report",
                "proposal_submission_report",
                "proposal_inbox_report",
                "approved_apply_plan",
                "snapshot_evaluation_report",
                "evaluation_report",
                "cycle_report",
            ],
        }


def make_artifact_run_dir(config: ArtifactStandardConfig, run_id: str) -> Path:
    """Return the normalized folder for a single run."""

    return config.root_dir / sanitize_artifact_name(run_id)


def sanitize_artifact_name(value: str) -> str:
    """Normalize a report or run name for filesystem-safe artifact paths."""

    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in value.strip())
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "artifact"


def artifact_report_path(
    *, config: ArtifactStandardConfig, run_id: str, name: str
) -> Path:
    """Return the normalized JSON report path for an artifact name."""

    filename = sanitize_artifact_name(name)
    if not filename.endswith(".json"):
        filename = f"{filename}.json"
    return make_artifact_run_dir(config, run_id) / config.reports_subdir / filename


def write_standard_artifact(
    *,
    config: ArtifactStandardConfig,
    run_id: str,
    name: str,
    payload: Mapping[str, Any],
) -> JsonDict:
    """Write one report artifact and return manifest metadata for it."""

    path = artifact_report_path(config=config, run_id=run_id, name=name)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    path.write_text(raw, encoding="utf-8")
    run_dir = make_artifact_run_dir(config, run_id)
    return build_artifact_metadata(
        config=config,
        run_id=run_id,
        name=name,
        path=path,
        payload=payload,
        raw=raw,
        run_dir=run_dir,
    )


def build_artifact_metadata(
    *,
    config: ArtifactStandardConfig,
    run_id: str,
    name: str,
    path: Path,
    payload: Mapping[str, Any],
    raw: str | None = None,
    run_dir: Path | None = None,
) -> JsonDict:
    """Build stable artifact metadata for a report file."""

    if run_dir is None:
        run_dir = make_artifact_run_dir(config, run_id)
    try:
        relative_path = str(path.relative_to(run_dir))
    except ValueError:
        relative_path = str(path)
    metadata: JsonDict = {
        "name": name,
        "path": str(path),
        "relative_path": relative_path,
        "schema_version": payload.get("schema_version"),
    }
    if path.exists():
        metadata["size_bytes"] = path.stat().st_size
    if config.include_checksums:
        if raw is None and path.exists():
            raw = path.read_text(encoding="utf-8")
        if raw is not None:
            metadata["sha256"] = sha256(raw.encode("utf-8")).hexdigest()
    return metadata


def build_artifact_manifest(
    *,
    config: ArtifactStandardConfig,
    run_id: str,
    artifacts: Sequence[Mapping[str, Any]],
    cycle_report: Mapping[str, Any] | None = None,
    status: str | None = None,
) -> JsonDict:
    """Build a normalized manifest for all reports produced by one run."""

    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    artifact_list = [dict(item) for item in artifacts]
    schemas = {
        str(item.get("name")): item.get("schema_version")
        for item in artifact_list
        if item.get("name")
    }
    inferred_status = status or "unknown"
    if cycle_report is not None:
        inferred_status = str(cycle_report.get("status") or inferred_status)
    return {
        "schema_version": "skeinrank.agent_artifact_manifest.v1",
        "runner": "openrouter_alias_scout",
        "layout_version": config.layout_version,
        "run_id": run_id,
        "created_at": now,
        "status": inferred_status,
        "root_dir": str(config.root_dir),
        "run_dir": str(make_artifact_run_dir(config, run_id)),
        "reports_dir": str(
            make_artifact_run_dir(config, run_id) / config.reports_subdir
        ),
        "manifest_filename": config.manifest_filename,
        "summary_filename": config.summary_filename,
        "artifact_count": len(artifact_list),
        "artifacts": artifact_list,
        "stage_schemas": schemas,
        "cycle_summary": _compact_cycle_summary(cycle_report),
        "safety": {
            "network_calls_declared_by_manifest": False,
            "runtime_mutation_enabled": False,
            "snapshot_publish_enabled": False,
        },
    }


def write_artifact_manifest(
    *,
    config: ArtifactStandardConfig,
    run_id: str,
    artifacts: Sequence[Mapping[str, Any]],
    cycle_report: Mapping[str, Any] | None = None,
    status: str | None = None,
) -> JsonDict:
    """Write manifest.json and run_summary.json for a normalized run folder."""

    run_dir = make_artifact_run_dir(config, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_artifact_manifest(
        config=config,
        run_id=run_id,
        artifacts=artifacts,
        cycle_report=cycle_report,
        status=status,
    )
    manifest_path = run_dir / config.manifest_filename
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    summary = {
        "schema_version": "skeinrank.agent_run_summary.v1",
        "run_id": run_id,
        "status": manifest["status"],
        "artifact_count": manifest["artifact_count"],
        "manifest_path": str(manifest_path),
        "stage_schemas": manifest["stage_schemas"],
    }
    (run_dir / config.summary_filename).write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def discover_artifact_files(
    config: ArtifactStandardConfig, run_id: str
) -> list[JsonDict]:
    """Discover already-written JSON artifacts for manifest repair/backfill."""

    reports_dir = make_artifact_run_dir(config, run_id) / config.reports_subdir
    if not reports_dir.exists():
        return []
    items: list[JsonDict] = []
    for path in sorted(reports_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        items.append(
            build_artifact_metadata(
                config=config,
                run_id=run_id,
                name=path.stem,
                path=path,
                payload=payload,
            )
        )
    return items


def _compact_cycle_summary(report: Mapping[str, Any] | None) -> JsonDict:
    if not report:
        return {"available": False}
    summary: JsonDict = {
        "available": True,
        "schema_version": report.get("schema_version"),
        "status": report.get("status"),
        "recommended_exit_code": report.get("recommended_exit_code"),
    }
    if "summary" in report:
        summary["summary"] = report["summary"]
    if "quality_gate" in report:
        summary["quality_gate"] = report["quality_gate"]
    return summary
