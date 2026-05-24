"""Budget and cache helpers for OpenRouter alias-scout runs.

Patch 40M keeps live model execution bounded and repeatable. The reference
agent may call OpenRouter, but every run should have explicit call/cost/token
limits and may reuse cached model responses for identical candidate packs.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

JsonDict = dict[str, Any]


@dataclass(frozen=True)
class AgentBudgetCacheConfig:
    """Budget and JSON cache settings for one alias-scout run."""

    max_llm_calls_per_run: int = 3
    max_total_tokens_per_run: int = 6000
    max_prompt_tokens_per_run: int = 5000
    max_cost_usd_per_run: float = 0.01
    cache_enabled: bool = False
    cache_path: Path | None = None
    cache_namespace: str = "openrouter-alias-scout-v1"
    force_refresh: bool = False
    write_cache: bool = True

    @classmethod
    def from_mapping(
        cls, raw: Mapping[str, Any] | None, *, base_dir: Path | None = None
    ) -> "AgentBudgetCacheConfig":
        """Create config from optional JSON config values."""

        if not raw:
            return cls()
        raw_cache_path = raw.get("cache_path")
        cache_path: Path | None = None
        if raw_cache_path:
            cache_path = Path(str(raw_cache_path))
            if not cache_path.is_absolute() and base_dir is not None:
                cache_path = base_dir / cache_path
        return cls(
            max_llm_calls_per_run=int(
                raw.get("max_llm_calls_per_run", cls.max_llm_calls_per_run)
            ),
            max_total_tokens_per_run=int(
                raw.get("max_total_tokens_per_run", cls.max_total_tokens_per_run)
            ),
            max_prompt_tokens_per_run=int(
                raw.get("max_prompt_tokens_per_run", cls.max_prompt_tokens_per_run)
            ),
            max_cost_usd_per_run=float(
                raw.get("max_cost_usd_per_run", cls.max_cost_usd_per_run)
            ),
            cache_enabled=bool(raw.get("cache_enabled", cls.cache_enabled)),
            cache_path=cache_path,
            cache_namespace=str(raw.get("cache_namespace", cls.cache_namespace)),
            force_refresh=bool(raw.get("force_refresh", cls.force_refresh)),
            write_cache=bool(raw.get("write_cache", cls.write_cache)),
        )

    def with_overrides(
        self,
        *,
        max_llm_calls_per_run: int | None = None,
        max_cost_usd_per_run: float | None = None,
        cache_enabled: bool | None = None,
        force_refresh: bool | None = None,
    ) -> "AgentBudgetCacheConfig":
        """Return a copy with common CLI overrides applied."""

        return AgentBudgetCacheConfig(
            max_llm_calls_per_run=(
                self.max_llm_calls_per_run
                if max_llm_calls_per_run is None
                else max_llm_calls_per_run
            ),
            max_total_tokens_per_run=self.max_total_tokens_per_run,
            max_prompt_tokens_per_run=self.max_prompt_tokens_per_run,
            max_cost_usd_per_run=(
                self.max_cost_usd_per_run
                if max_cost_usd_per_run is None
                else max_cost_usd_per_run
            ),
            cache_enabled=self.cache_enabled
            if cache_enabled is None
            else cache_enabled,
            cache_path=self.cache_path,
            cache_namespace=self.cache_namespace,
            force_refresh=self.force_refresh
            if force_refresh is None
            else force_refresh,
            write_cache=self.write_cache,
        )

    def to_report(self) -> JsonDict:
        """Return JSON-safe config metadata for reports."""

        return {
            "max_llm_calls_per_run": self.max_llm_calls_per_run,
            "max_total_tokens_per_run": self.max_total_tokens_per_run,
            "max_prompt_tokens_per_run": self.max_prompt_tokens_per_run,
            "max_cost_usd_per_run": self.max_cost_usd_per_run,
            "cache_enabled": self.cache_enabled,
            "cache_path": str(self.cache_path) if self.cache_path else None,
            "cache_namespace": self.cache_namespace,
            "force_refresh": self.force_refresh,
            "write_cache": self.write_cache,
        }


class JsonLlmReviewCache:
    """Small JSON-file cache for OpenRouter review responses."""

    def __init__(self, config: AgentBudgetCacheConfig) -> None:
        self.config = config
        self._entries: dict[str, JsonDict] = {}
        self._dirty = False
        if self.enabled:
            self._entries = self._load_entries()

    @property
    def enabled(self) -> bool:
        """Whether cache reads/writes are enabled and a path is configured."""

        return bool(self.config.cache_enabled and self.config.cache_path)

    @property
    def entry_count(self) -> int:
        """Number of loaded cache entries."""

        return len(self._entries)

    def get(self, key: str) -> JsonDict | None:
        """Return a cached response entry if present and refresh is not forced."""

        if not self.enabled or self.config.force_refresh:
            return None
        entry = self._entries.get(key)
        return dict(entry) if isinstance(entry, Mapping) else None

    def set(self, key: str, entry: Mapping[str, Any]) -> None:
        """Store a response entry in memory for later save."""

        if not self.enabled or not self.config.write_cache:
            return
        self._entries[key] = dict(entry)
        self._dirty = True

    def save(self) -> None:
        """Persist dirty cache entries to JSON."""

        if not self.enabled or not self._dirty:
            return
        path = self.config.cache_path
        if path is None:  # pragma: no cover - guarded by enabled.
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "skeinrank.openrouter_alias_scout_cache.v1",
            "namespace": self.config.cache_namespace,
            "entries": self._entries,
        }
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        self._dirty = False

    def clear(self) -> int:
        """Clear the cache file and return the number of removed entries."""

        removed = len(self._entries)
        self._entries = {}
        self._dirty = False
        if self.config.cache_path and self.config.cache_path.exists():
            self.config.cache_path.unlink()
        return removed

    def _load_entries(self) -> dict[str, JsonDict]:
        path = self.config.cache_path
        if path is None or not path.exists():
            return {}
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping):
            return {}
        if raw.get("namespace") != self.config.cache_namespace:
            return {}
        entries = raw.get("entries")
        if not isinstance(entries, Mapping):
            return {}
        return {
            str(key): dict(value)
            for key, value in entries.items()
            if isinstance(value, Mapping)
        }


class LlmRunBudgetTracker:
    """Track live OpenRouter calls, token usage, and cost for one run."""

    def __init__(self, config: AgentBudgetCacheConfig) -> None:
        self.config = config
        self.live_calls_started = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.cache_writes = 0
        self.skipped_due_to_budget = 0
        self.prompt_tokens_used = 0
        self.completion_tokens_used = 0
        self.total_tokens_used = 0
        self.cost_usd_used = 0.0

    def can_start_live_call(self) -> bool:
        """Return whether another live LLM call is allowed."""

        if self.live_calls_started >= self.config.max_llm_calls_per_run:
            return False
        if self.total_tokens_used >= self.config.max_total_tokens_per_run:
            return False
        if self.prompt_tokens_used >= self.config.max_prompt_tokens_per_run:
            return False
        return self.cost_usd_used < self.config.max_cost_usd_per_run

    def record_live_call_started(self) -> None:
        """Record that a live OpenRouter call is about to start."""

        self.live_calls_started += 1

    def record_cache_hit(self) -> None:
        """Record one cache hit."""

        self.cache_hits += 1

    def record_cache_miss(self) -> None:
        """Record one cache miss."""

        self.cache_misses += 1

    def record_cache_write(self) -> None:
        """Record one cache write."""

        self.cache_writes += 1

    def record_budget_skip(self) -> None:
        """Record that a candidate was skipped due to budget limits."""

        self.skipped_due_to_budget += 1

    def record_usage(self, response: Mapping[str, Any]) -> None:
        """Accumulate token/cost usage from an OpenRouter response."""

        usage = response.get("usage")
        if not isinstance(usage, Mapping):
            return
        prompt_tokens = _int_value(usage.get("prompt_tokens"))
        completion_tokens = _int_value(usage.get("completion_tokens"))
        total_tokens = _int_value(usage.get("total_tokens"))
        if total_tokens == 0:
            total_tokens = prompt_tokens + completion_tokens
        self.prompt_tokens_used += prompt_tokens
        self.completion_tokens_used += completion_tokens
        self.total_tokens_used += total_tokens
        self.cost_usd_used += extract_openrouter_cost_usd(usage)

    def to_report(self) -> JsonDict:
        """Return JSON-safe budget/cache counters."""

        return {
            "budget": self.config.to_report(),
            "live_calls_started": self.live_calls_started,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_writes": self.cache_writes,
            "skipped_due_to_budget": self.skipped_due_to_budget,
            "usage": {
                "prompt_tokens": self.prompt_tokens_used,
                "completion_tokens": self.completion_tokens_used,
                "total_tokens": self.total_tokens_used,
                "estimated_cost_usd": round(self.cost_usd_used, 10),
            },
        }


def build_llm_review_cache_key(
    *,
    candidate_pack: Mapping[str, Any],
    openrouter_model: str,
    system_prompt: str,
    user_prompt: str,
    response_format_json: bool,
    tools: Sequence[Mapping[str, Any]] | None,
    cache_namespace: str,
) -> str:
    """Build a stable cache key for a model review request."""

    payload = {
        "cache_namespace": cache_namespace,
        "candidate_pack": _json_safe(candidate_pack),
        "openrouter_model": openrouter_model,
        "response_format_json": response_format_json,
        "system_prompt": system_prompt,
        "tools": _json_safe(list(tools or [])),
        "user_prompt": user_prompt,
    }
    cache_source = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    digest = sha256(cache_source).hexdigest()
    return f"{cache_namespace}:{digest[:24]}"


def build_budget_cache_plan(config: AgentBudgetCacheConfig) -> JsonDict:
    """Build an offline budget/cache plan for CLI inspection."""

    cache = JsonLlmReviewCache(config)
    return {
        "schema_version": "skeinrank.agent_budget_cache_plan.v1",
        "runner": "openrouter_alias_scout",
        "openrouter_calls": False,
        "budget_cache": config.to_report(),
        "cache_status": {
            "enabled": cache.enabled,
            "entries_loaded": cache.entry_count,
            "path_exists": bool(config.cache_path and config.cache_path.exists()),
        },
        "safety": {
            "limits_checked_before_live_calls": True,
            "cached_responses_do_not_mutate_skeinrank": True,
            "proposal_submission_enabled": False,
        },
    }


def clear_llm_review_cache(config: AgentBudgetCacheConfig) -> JsonDict:
    """Clear the configured cache file and return a small report."""

    cache = JsonLlmReviewCache(config)
    removed = cache.clear()
    return {
        "schema_version": "skeinrank.agent_cache_clear_report.v1",
        "runner": "openrouter_alias_scout",
        "cache_enabled": cache.enabled,
        "cache_path": str(config.cache_path) if config.cache_path else None,
        "entries_removed": removed,
    }


def build_budget_skip_review_item(item: Mapping[str, Any]) -> JsonDict:
    """Build a reviewed-item placeholder for candidates skipped by budget."""

    return {
        "candidate_alias": item.get("candidate_alias"),
        "idempotency_key": item.get("idempotency_key"),
        "judgment": {
            "action": "skipped_budget",
            "confidence": 0.0,
            "reason": "LLM review skipped because the run budget was exhausted.",
            "risk_flags": ["budget_exhausted"],
        },
        "proposal_ready_for_validation": False,
        "proposal_payload": None,
        "openrouter_response_id": None,
        "openrouter_usage": None,
        "cache": {"hit": False, "skipped_due_to_budget": True},
    }


def make_cache_entry(
    *,
    response: Mapping[str, Any],
    candidate_alias: str,
    openrouter_model: str,
) -> JsonDict:
    """Build a JSON-safe cache entry for one OpenRouter response."""

    return {
        "response": _json_safe(response),
        "candidate_alias": candidate_alias,
        "openrouter_model": openrouter_model,
    }


def extract_openrouter_cost_usd(usage: Mapping[str, Any]) -> float:
    """Extract OpenRouter cost from usage payloads when present."""

    cost = usage.get("cost")
    if isinstance(cost, int | float):
        return float(cost)
    cost_details = usage.get("cost_details")
    if isinstance(cost_details, Mapping):
        inference_cost = cost_details.get("upstream_inference_cost")
        if isinstance(inference_cost, int | float):
            return float(inference_cost)
    return 0.0


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    return value


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0
