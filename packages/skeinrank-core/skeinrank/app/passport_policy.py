"""Passport policy helpers.

This module keeps the "hot path" in :mod:`skeinrank.app.engine` clean.

Policy goals:
- Summary passport is always-on by default (cheap, stable for logging).
- Debug passport is opt-in (explicit) or can be enabled by sampling/triggers.
- Off disables passport entirely for maximum throughput.

Env vars:
- SKEINRANK_DEBUG_SAMPLE=0.01 (upgrade a fraction of summary requests to debug)
- SKEINRANK_DEBUG_ON_WARNINGS=1 (upgrade to debug when warnings are present)
- SKEINRANK_DEBUG_LATENCY_MS=250 (upgrade to debug when total_ms >= threshold)
  (also accepts SKEINRANK_DEBUG_LATENCY_P95_MS as an alias)

Upgrade taxonomy (passport_upgraded_by):
- explicit: user requested debug/off
- sample: chosen by probabilistic sampling
- latency: triggered by latency threshold
- warnings: non-critical warnings (e.g., truncation)
- fallback: mitigation / degraded mode (for example, device fallback)

Optional: in debug mode, ``reason_details`` can include parameters explaining
why an upgrade happened (sampling probability, latency threshold, etc.).
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass, field

_LEVELS = {"summary", "debug", "off"}

# Stable ordering for multi-reason upgrades (e.g., fallback+warnings).
_UPGRADE_FLAGS_ORDER = ("fallback", "warnings", "latency", "sample")

# Warnings that indicate a degraded mode / mitigation.
_FALLBACK_WARNING_PREFIXES = (
    "device_fallback:",
    "backend_fallback:",
    "precision_fallback:",
)


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_float(name: str, default: float | None = None) -> float | None:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    try:
        return float(v)
    except Exception:
        return default


def _shorten(s: str, *, max_chars: int = 256) -> str:
    if s is None:
        return ""
    s = str(s)
    return s if len(s) <= max_chars else (s[: max_chars - 3] + "...")


def _split_warnings(warnings: list[str]) -> tuple[list[str], list[str]]:
    fallback: list[str] = []
    normal: list[str] = []
    for w in warnings or []:
        ws = str(w)
        if any(ws.startswith(p) for p in _FALLBACK_WARNING_PREFIXES):
            fallback.append(ws)
        else:
            normal.append(ws)
    return fallback, normal


@dataclass(frozen=True)
class PassportDecision:
    requested: str
    effective: str
    # Why the passport is debug for this request.
    # - ["explicit"] when user requested debug
    # - ["fallback"|"warnings"|"latency"|"sample"] when upgraded from summary
    # - [] when summary and not upgraded
    passport_upgraded_by: list[str] = field(default_factory=list)
    # Extra parameters explaining the upgrade decision. Only populated for debug.
    reason_details: dict[str, object] | None = None


def resolve_requested_passport_level(*, passport: str | None, debug: bool) -> str:
    """Resolve user-facing args to a requested passport level."""
    if debug:
        return "debug"
    if passport is None:
        return "summary"
    p = str(passport).strip().lower()
    if p not in _LEVELS:
        # Be strict: unknown value should fail early.
        raise ValueError(
            f"Unknown passport level: {passport!r}. Expected one of: summary|debug|off"
        )
    return p


def decide_effective_passport_level(
    *,
    requested: str,
    warnings: list[str],
    total_ms: float,
) -> PassportDecision:
    """Decide whether to upgrade summary -> debug based on sampling/triggers.

    Notes:
      - requested="debug" is always honored and tagged as ["explicit"].
      - requested="off" is always honored (passport is null).
      - requested="summary" can be upgraded to debug for observability.
    """

    if requested == "debug":
        return PassportDecision(
            requested="debug",
            effective="debug",
            passport_upgraded_by=["explicit"],
            reason_details=None,
        )
    if requested == "off":
        # passport will be null; keep explicit for symmetry.
        return PassportDecision(
            requested="off",
            effective="off",
            passport_upgraded_by=["explicit"],
            reason_details=None,
        )

    # requested == summary
    flags: set[str] = set()
    details: dict[str, object] = {}

    # Trigger: warnings
    if _env_bool("SKEINRANK_DEBUG_ON_WARNINGS", default=False) and len(warnings) > 0:
        fallback_w, normal_w = _split_warnings(warnings)
        if len(fallback_w) > 0:
            flags.add("fallback")
            details["fallback_warnings"] = [_shorten(w) for w in fallback_w]
        if len(normal_w) > 0:
            flags.add("warnings")
            details["warnings_count"] = int(len(normal_w))
        # If warnings exist but all are fallback, we still want the upgrade.
        if len(fallback_w) == 0 and len(normal_w) == 0:
            flags.add("warnings")
            details["warnings_count"] = 0

    # Trigger: latency threshold.
    latency_ms = _env_float("SKEINRANK_DEBUG_LATENCY_MS", default=None)
    if latency_ms is None:
        latency_ms = _env_float("SKEINRANK_DEBUG_LATENCY_P95_MS", default=None)
    if latency_ms is not None:
        latency_ms = max(1.0, float(latency_ms))
    if latency_ms is not None and total_ms >= float(latency_ms):
        flags.add("latency")
        details["threshold_ms"] = float(latency_ms)
        details["total_ms"] = float(total_ms)

    # Trigger: sampling.
    p = _env_float("SKEINRANK_DEBUG_SAMPLE", default=0.0)
    try:
        p = float(p) if p is not None else 0.0
    except Exception:
        p = 0.0
    p = max(0.0, min(1.0, p))
    if p > 0.0 and random.random() < p:
        flags.add("sample")
        details["p"] = float(p)

    if len(flags) > 0:
        ordered = [k for k in _UPGRADE_FLAGS_ORDER if k in flags]
        return PassportDecision(
            requested="summary",
            effective="debug",
            passport_upgraded_by=ordered,
            reason_details=details if len(details) > 0 else {},
        )

    return PassportDecision(
        requested="summary",
        effective="summary",
        passport_upgraded_by=[],
        reason_details=None,
    )
