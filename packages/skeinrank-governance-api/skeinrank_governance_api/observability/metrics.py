"""Dependency-free Prometheus metrics helpers for the governance API."""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

DEFAULT_HTTP_DURATION_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)
DEFAULT_JOB_DURATION_BUCKETS = (
    0.1,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
    60.0,
    120.0,
    300.0,
    600.0,
)

_LABELS_NONE: tuple[tuple[str, str], ...] = ()


@dataclass
class _MetricDefinition:
    name: str
    kind: str
    help: str
    label_names: tuple[str, ...] = ()
    buckets: tuple[float, ...] = ()


@dataclass
class _HistogramState:
    buckets: dict[float, float] = field(default_factory=lambda: defaultdict(float))
    count: float = 0.0
    total: float = 0.0


class MetricsRegistry:
    """Small in-memory metrics registry that renders Prometheus text format."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._definitions: dict[str, _MetricDefinition] = {}
        self._counters: dict[str, dict[tuple[tuple[str, str], ...], float]] = (
            defaultdict(dict)
        )
        self._gauges: dict[str, dict[tuple[tuple[str, str], ...], float]] = defaultdict(
            dict
        )
        self._histograms: dict[
            str, dict[tuple[tuple[str, str], ...], _HistogramState]
        ] = defaultdict(dict)

    def reset(self) -> None:
        """Clear recorded values while keeping metric definitions."""

        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()

    def counter(
        self,
        name: str,
        help_text: str,
        *,
        labels: Iterable[str] = (),
    ) -> None:
        self._define(name=name, kind="counter", help_text=help_text, labels=labels)

    def gauge(
        self,
        name: str,
        help_text: str,
        *,
        labels: Iterable[str] = (),
    ) -> None:
        self._define(name=name, kind="gauge", help_text=help_text, labels=labels)

    def histogram(
        self,
        name: str,
        help_text: str,
        *,
        labels: Iterable[str] = (),
        buckets: Iterable[float] = DEFAULT_HTTP_DURATION_BUCKETS,
    ) -> None:
        self._define(
            name=name,
            kind="histogram",
            help_text=help_text,
            labels=labels,
            buckets=tuple(float(bucket) for bucket in buckets),
        )

    def inc(
        self,
        name: str,
        amount: float = 1.0,
        *,
        labels: Mapping[str, Any] | None = None,
    ) -> None:
        with self._lock:
            label_values = self._label_values(name, labels)
            self._counters[name][label_values] = self._counters[name].get(
                label_values, 0.0
            ) + float(amount)

    def set(
        self,
        name: str,
        value: float,
        *,
        labels: Mapping[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self._gauges[name][self._label_values(name, labels)] = float(value)

    def observe(
        self,
        name: str,
        value: float,
        *,
        labels: Mapping[str, Any] | None = None,
    ) -> None:
        observed = float(value)
        with self._lock:
            definition = self._definitions.get(name)
            if definition is None or definition.kind != "histogram":
                raise KeyError(f"Unknown histogram metric: {name}")
            label_values = self._label_values(name, labels)
            state = self._histograms[name].setdefault(label_values, _HistogramState())
            state.count += 1.0
            state.total += observed
            for bucket in definition.buckets:
                if observed <= bucket:
                    state.buckets[bucket] = state.buckets.get(bucket, 0.0) + 1.0

    def render_prometheus(self) -> str:
        """Render all known metrics as Prometheus text exposition format."""

        with self._lock:
            lines: list[str] = []
            for name in sorted(self._definitions):
                definition = self._definitions[name]
                lines.append(f"# HELP {name} {_escape_help(definition.help)}")
                lines.append(f"# TYPE {name} {definition.kind}")
                if definition.kind == "counter":
                    for labels, value in sorted(self._counters.get(name, {}).items()):
                        lines.append(_sample(name, labels, value))
                elif definition.kind == "gauge":
                    for labels, value in sorted(self._gauges.get(name, {}).items()):
                        lines.append(_sample(name, labels, value))
                elif definition.kind == "histogram":
                    for labels, state in sorted(self._histograms.get(name, {}).items()):
                        cumulative = 0.0
                        for bucket in definition.buckets:
                            cumulative = state.buckets.get(bucket, cumulative)
                            lines.append(
                                _sample(
                                    f"{name}_bucket",
                                    labels + (("le", _bucket_label(bucket)),),
                                    cumulative,
                                )
                            )
                        lines.append(
                            _sample(
                                f"{name}_bucket",
                                labels + (("le", "+Inf"),),
                                state.count,
                            )
                        )
                        lines.append(_sample(f"{name}_count", labels, state.count))
                        lines.append(_sample(f"{name}_sum", labels, state.total))
            lines.append("")
            return "\n".join(lines)

    def _define(
        self,
        *,
        name: str,
        kind: str,
        help_text: str,
        labels: Iterable[str],
        buckets: tuple[float, ...] = (),
    ) -> None:
        label_names = tuple(labels)
        with self._lock:
            existing = self._definitions.get(name)
            definition = _MetricDefinition(
                name=name,
                kind=kind,
                help=help_text,
                label_names=label_names,
                buckets=tuple(sorted(set(buckets))),
            )
            if existing is not None and existing != definition:
                raise ValueError(f"Metric {name!r} was already defined differently")
            self._definitions[name] = definition

    def _label_values(
        self, name: str, labels: Mapping[str, Any] | None
    ) -> tuple[tuple[str, str], ...]:
        definition = self._definitions.get(name)
        if definition is None:
            raise KeyError(f"Unknown metric: {name}")
        if not definition.label_names:
            return _LABELS_NONE
        provided = labels or {}
        return tuple(
            (label, str(provided.get(label, ""))) for label in definition.label_names
        )


registry = MetricsRegistry()


def register_default_metrics() -> None:
    """Register built-in metrics used by the governance API and worker."""

    registry.counter(
        "skeinrank_http_requests_total",
        "Total HTTP requests handled by the governance API.",
        labels=("method", "path", "status_code"),
    )
    registry.histogram(
        "skeinrank_http_request_duration_seconds",
        "HTTP request duration in seconds.",
        labels=("method", "path", "status_code"),
        buckets=DEFAULT_HTTP_DURATION_BUCKETS,
    )
    registry.counter(
        "skeinrank_http_exceptions_total",
        "Unhandled HTTP exceptions observed by the governance API.",
        labels=("method", "path"),
    )
    registry.counter(
        "skeinrank_health_checks_total",
        "Health check responses by endpoint and status.",
        labels=("endpoint", "status"),
    )
    registry.histogram(
        "skeinrank_health_check_duration_seconds",
        "Health check execution duration in seconds.",
        labels=("endpoint", "status"),
        buckets=DEFAULT_HTTP_DURATION_BUCKETS,
    )
    registry.gauge(
        "skeinrank_database_up",
        "Database connectivity status reported by operational health checks.",
    )
    registry.gauge(
        "skeinrank_schema_ok",
        "Governance schema health status reported by operational health checks.",
    )
    registry.gauge(
        "skeinrank_schema_current_matches_head",
        "Whether the current database revision matches the Alembic head.",
    )
    registry.gauge(
        "skeinrank_schema_missing_tables",
        "Number of SQLAlchemy metadata tables missing from the database.",
    )
    registry.gauge(
        "skeinrank_alembic_multiple_heads",
        "Whether the migration script tree exposes multiple Alembic heads.",
    )
    registry.gauge(
        "skeinrank_elasticsearch_up",
        "Elasticsearch dependency status reported by operational health checks.",
        labels=("configured",),
    )
    registry.counter(
        "skeinrank_operational_metrics_refresh_total",
        "Operational metrics refresh attempts by status.",
        labels=("status",),
    )
    registry.histogram(
        "skeinrank_operational_metrics_refresh_duration_seconds",
        "Operational metrics refresh duration in seconds.",
        labels=("status",),
        buckets=DEFAULT_HTTP_DURATION_BUCKETS,
    )
    registry.gauge(
        "skeinrank_operational_metrics_last_refresh_success",
        "Whether the last operational metrics refresh completed successfully.",
    )
    registry.gauge(
        "skeinrank_operational_metrics_last_refresh_timestamp_seconds",
        "Unix timestamp of the last operational metrics refresh attempt.",
    )
    registry.gauge(
        "skeinrank_agent_runs_current",
        "Current persisted agent run rows by status.",
        labels=("status",),
    )
    registry.gauge(
        "skeinrank_agent_document_visits_current",
        "Current persisted agent document visit rows by visit status.",
        labels=("status",),
    )
    registry.gauge(
        "skeinrank_agent_candidate_observations_current",
        "Current persisted agent candidate observation rows by status.",
        labels=("status",),
    )
    registry.gauge(
        "skeinrank_agent_llm_reviews_current",
        "Current persisted agent LLM review rows by status.",
        labels=("status",),
    )
    registry.gauge(
        "skeinrank_agent_proposal_attempts_current",
        "Current persisted agent proposal attempt rows by status.",
        labels=("status",),
    )
    registry.gauge(
        "skeinrank_agent_evidence_windows_current",
        "Current persisted agent evidence window rows.",
    )
    registry.counter(
        "skeinrank_runtime_search_requests_total",
        "Runtime search requests handled by endpoint type.",
        labels=("endpoint", "status"),
    )
    registry.histogram(
        "skeinrank_runtime_search_duration_seconds",
        "Runtime search endpoint duration in seconds.",
        labels=("endpoint", "status"),
        buckets=DEFAULT_HTTP_DURATION_BUCKETS,
    )
    registry.counter(
        "skeinrank_runtime_search_hits_total",
        "Total search hits returned by runtime search endpoints.",
        labels=("endpoint",),
    )
    registry.counter(
        "skeinrank_runtime_search_binding_requests_total",
        "Per-binding runtime search attempts and outcomes.",
        labels=("status",),
    )
    registry.counter(
        "skeinrank_enrichment_jobs_total",
        "Elasticsearch enrichment jobs by status and write strategy.",
        labels=("status", "write_strategy"),
    )
    registry.histogram(
        "skeinrank_enrichment_job_duration_seconds",
        "Elasticsearch enrichment job duration in seconds.",
        labels=("status", "write_strategy"),
        buckets=DEFAULT_JOB_DURATION_BUCKETS,
    )
    registry.counter(
        "skeinrank_enrichment_documents_seen_total",
        "Total Elasticsearch documents seen by enrichment jobs.",
        labels=("write_strategy",),
    )
    registry.counter(
        "skeinrank_enrichment_documents_enriched_total",
        "Total Elasticsearch documents enriched by enrichment jobs.",
        labels=("write_strategy",),
    )
    registry.counter(
        "skeinrank_enrichment_documents_failed_total",
        "Total Elasticsearch documents failed by enrichment jobs.",
        labels=("write_strategy",),
    )

    registry.counter(
        "skeinrank_proposals_submitted_total",
        "Proposal submissions by source, suggestion type, validation status, and outcome.",
        labels=("source_type", "suggestion_type", "validation_status", "outcome"),
    )
    registry.counter(
        "skeinrank_proposal_reviews_total",
        "Proposal review decisions by source type and decision.",
        labels=("source_type", "decision"),
    )
    registry.counter(
        "skeinrank_proposal_batch_apply_total",
        "Proposal batch apply operations by status and snapshot publish flag.",
        labels=("status", "publish_snapshot"),
    )
    registry.counter(
        "skeinrank_proposal_batch_suggestions_total",
        "Suggestions processed by proposal batch apply operations.",
        labels=("status", "publish_snapshot"),
    )
    registry.gauge(
        "skeinrank_build_info",
        "Build and service metadata for the governance API.",
        labels=("service", "version"),
    )


def record_http_request(
    *, method: str, path: str, status_code: int, duration_seconds: float
) -> None:
    labels = {"method": method, "path": path, "status_code": str(status_code)}
    registry.inc("skeinrank_http_requests_total", labels=labels)
    registry.observe(
        "skeinrank_http_request_duration_seconds", duration_seconds, labels=labels
    )


def record_http_exception(*, method: str, path: str) -> None:
    registry.inc(
        "skeinrank_http_exceptions_total", labels={"method": method, "path": path}
    )


def record_health_check(*, endpoint: str, status: str, duration_seconds: float) -> None:
    """Record one health endpoint execution."""

    labels = {"endpoint": endpoint, "status": status}
    registry.inc("skeinrank_health_checks_total", labels=labels)
    registry.observe(
        "skeinrank_health_check_duration_seconds", duration_seconds, labels=labels
    )


def set_operational_health_metrics(
    *,
    database_ok: bool,
    schema_ok: bool,
    schema_current_matches_head: bool,
    schema_missing_tables: int,
    alembic_multiple_heads: bool,
    elasticsearch_ok: bool,
    elasticsearch_configured: bool,
) -> None:
    """Set gauges that describe the current deployment health surface."""

    registry.set("skeinrank_database_up", _bool_value(database_ok))
    registry.set("skeinrank_schema_ok", _bool_value(schema_ok))
    registry.set(
        "skeinrank_schema_current_matches_head",
        _bool_value(schema_current_matches_head),
    )
    registry.set("skeinrank_schema_missing_tables", max(schema_missing_tables, 0))
    registry.set(
        "skeinrank_alembic_multiple_heads", _bool_value(alembic_multiple_heads)
    )
    registry.set(
        "skeinrank_elasticsearch_up",
        _bool_value(elasticsearch_ok),
        labels={"configured": str(bool(elasticsearch_configured)).lower()},
    )


def record_operational_metrics_refresh(*, status: str, duration_seconds: float) -> None:
    """Record one /metrics-time operational refresh attempt."""

    labels = {"status": status}
    registry.inc("skeinrank_operational_metrics_refresh_total", labels=labels)
    registry.observe(
        "skeinrank_operational_metrics_refresh_duration_seconds",
        duration_seconds,
        labels=labels,
    )
    registry.set(
        "skeinrank_operational_metrics_last_refresh_success",
        1.0 if status == "succeeded" else 0.0,
    )
    registry.set(
        "skeinrank_operational_metrics_last_refresh_timestamp_seconds", time.time()
    )


def set_agent_tracking_metric(
    *, metric_name: str, status_values: Iterable[str], counts: Mapping[str, int]
) -> None:
    """Set a status-labelled current-state agent tracking metric."""

    for status in status_values:
        registry.set(
            metric_name, float(counts.get(status, 0)), labels={"status": status}
        )


def set_agent_evidence_windows_current(count: int) -> None:
    """Set the current persisted evidence window count."""

    registry.set("skeinrank_agent_evidence_windows_current", float(max(count, 0)))


def record_runtime_search_request(
    *, endpoint: str, status: str, duration_seconds: float, hits: int = 0
) -> None:
    labels = {"endpoint": endpoint, "status": status}
    registry.inc("skeinrank_runtime_search_requests_total", labels=labels)
    registry.observe(
        "skeinrank_runtime_search_duration_seconds", duration_seconds, labels=labels
    )
    registry.inc(
        "skeinrank_runtime_search_hits_total",
        amount=hits,
        labels={"endpoint": endpoint},
    )


def record_runtime_search_binding(*, status: str) -> None:
    registry.inc(
        "skeinrank_runtime_search_binding_requests_total", labels={"status": status}
    )


def record_enrichment_job(
    *,
    status: str,
    write_strategy: str,
    duration_seconds: float | None = None,
    documents_seen: int = 0,
    documents_enriched: int = 0,
    documents_failed: int = 0,
) -> None:
    labels = {"status": status, "write_strategy": write_strategy}
    registry.inc("skeinrank_enrichment_jobs_total", labels=labels)
    if duration_seconds is not None:
        registry.observe(
            "skeinrank_enrichment_job_duration_seconds", duration_seconds, labels=labels
        )
    strategy_labels = {"write_strategy": write_strategy}
    if documents_seen:
        registry.inc(
            "skeinrank_enrichment_documents_seen_total",
            amount=documents_seen,
            labels=strategy_labels,
        )
    if documents_enriched:
        registry.inc(
            "skeinrank_enrichment_documents_enriched_total",
            amount=documents_enriched,
            labels=strategy_labels,
        )
    if documents_failed:
        registry.inc(
            "skeinrank_enrichment_documents_failed_total",
            amount=documents_failed,
            labels=strategy_labels,
        )


def record_proposal_submission(
    *,
    source_type: str,
    suggestion_type: str,
    validation_status: str,
    outcome: str,
) -> None:
    """Record proposal submission, retry, or conflict outcome."""

    registry.inc(
        "skeinrank_proposals_submitted_total",
        labels={
            "source_type": source_type,
            "suggestion_type": suggestion_type,
            "validation_status": validation_status,
            "outcome": outcome,
        },
    )


def record_proposal_review(*, source_type: str, decision: str) -> None:
    """Record an individual proposal review decision."""

    registry.inc(
        "skeinrank_proposal_reviews_total",
        labels={"source_type": source_type, "decision": decision},
    )


def record_proposal_batch_apply(
    *, status: str, publish_snapshot: bool, suggestions_count: int
) -> None:
    """Record a proposal batch apply operation and processed suggestion count."""

    labels = {"status": status, "publish_snapshot": str(bool(publish_snapshot)).lower()}
    registry.inc("skeinrank_proposal_batch_apply_total", labels=labels)
    if suggestions_count:
        registry.inc(
            "skeinrank_proposal_batch_suggestions_total",
            amount=suggestions_count,
            labels=labels,
        )


def set_build_info(*, service: str, version: str) -> None:
    registry.set(
        "skeinrank_build_info", 1.0, labels={"service": service, "version": version}
    )


def render_prometheus_metrics() -> str:
    return registry.render_prometheus()


def current_time() -> float:
    return time.perf_counter()


def elapsed_seconds(started_at: float) -> float:
    return max(time.perf_counter() - started_at, 0.0)


def _bool_value(value: bool) -> float:
    return 1.0 if value else 0.0


def _sample(name: str, labels: tuple[tuple[str, str], ...], value: float) -> str:
    label_suffix = ""
    if labels:
        rendered = ",".join(
            f'{key}="{_escape_label_value(value)}"' for key, value in labels
        )
        label_suffix = f"{{{rendered}}}"
    return f"{name}{label_suffix} {_number(value)}"


def _escape_label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _escape_help(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n")


def _bucket_label(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)


def _number(value: float) -> str:
    if math.isfinite(value) and value.is_integer():
        return str(int(value))
    return repr(float(value))


register_default_metrics()
