"""Zero-friction public facade for local SkeinRank canonicalization.

The facade is intentionally deterministic and dependency-light. It does not call
OpenRouter, the Governance API, Elasticsearch, Celery, or optional ML adapters.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .dictionary_spec import DICTIONARY_SCHEMA_VERSION
from .sdk import (
    CanonicalizedText,
    Dictionary,
    ExtractionResult,
    canonicalize_text,
    extract_terms,
    load_dictionary,
)

DictionarySource = str | Path | Mapping[str, Any] | Dictionary | None
SimpleDictionaryValue = str | Sequence[str] | Mapping[str, Any]
SimpleDictionary = Mapping[str, SimpleDictionaryValue]

_DEMO_DICTIONARY_PAYLOAD: dict[str, Any] = {
    "schema_version": DICTIONARY_SCHEMA_VERSION,
    "profile_name": "platform_ops_demo",
    "profile_description": (
        "Built-in platform operations terminology for zero-friction "
        "SkeinRank SDK examples. The dictionary is intentionally compact, "
        "but it covers infrastructure, incidents, CI/CD, search, RAG, and "
        "ambiguous company-language surfaces."
    ),
    "terms": [
        {
            "canonical_value": "kubernetes",
            "slot": "TECHNOLOGY",
            "description": "Container orchestration platform.",
            "tags": ["cloud-native", "infrastructure", "orchestration"],
            "aliases": ["k8s", "kube", "kuber", "kube cluster"],
        },
        {
            "canonical_value": "postgresql",
            "slot": "DATABASE",
            "description": "PostgreSQL relational database.",
            "tags": ["database", "storage"],
            "aliases": ["pg", "postgres", "psql", "postgres db"],
        },
        {
            "canonical_value": "redis",
            "slot": "CACHE",
            "description": "Redis cache or key-value store.",
            "tags": ["cache", "storage"],
            "aliases": ["redis cache", "cache"],
        },
        {
            "canonical_value": "elasticsearch",
            "slot": "SEARCH_BACKEND",
            "description": "Elasticsearch search backend.",
            "tags": ["index", "search"],
            "aliases": ["es", "elastic", "elastic search"],
        },
        {
            "canonical_value": "opensearch",
            "slot": "SEARCH_BACKEND",
            "description": "OpenSearch search backend.",
            "tags": ["index", "search"],
            "aliases": ["os search", "open search"],
        },
        {
            "canonical_value": "vector database",
            "slot": "SEARCH_BACKEND",
            "description": "Vector or embedding store used by RAG workflows.",
            "tags": ["embeddings", "rag", "search"],
            "aliases": ["vector db", "vdb", "embedding store"],
        },
        {
            "canonical_value": "rag pipeline",
            "slot": "AI_WORKFLOW",
            "description": "Retrieval-augmented generation workflow.",
            "tags": ["ai", "rag", "retrieval"],
            "aliases": ["rag", "retrieval augmented generation"],
        },
        {
            "canonical_value": "llm agent",
            "slot": "AI_WORKFLOW",
            "description": "Tool-using or agentic LLM workflow.",
            "tags": ["agent", "ai", "tools"],
            "aliases": ["ai agent", "agentic workflow", "tool-using agent"],
        },
        {
            "canonical_value": "api server",
            "slot": "COMPONENT",
            "description": "Backend API service component.",
            "tags": ["backend", "service"],
            "aliases": ["api-server", "apiserver", "api svc"],
        },
        {
            "canonical_value": "background worker",
            "slot": "COMPONENT",
            "description": "Asynchronous worker or job processor.",
            "tags": ["backend", "jobs"],
            "aliases": ["worker", "job worker", "async worker"],
        },
        {
            "canonical_value": "message queue",
            "slot": "COMPONENT",
            "description": "Queue used for asynchronous processing.",
            "tags": ["backend", "messaging"],
            "aliases": ["rabbitmq", "rmq", "queue"],
        },
        {
            "canonical_value": "authentication",
            "slot": "SECURITY_CONCEPT",
            "description": "Identity verification.",
            "tags": ["identity", "security"],
            "aliases": ["authn", "login auth"],
        },
        {
            "canonical_value": "authorization",
            "slot": "SECURITY_CONCEPT",
            "description": "Permission and access checks.",
            "tags": ["identity", "security"],
            "aliases": ["authz", "permission check"],
        },
        {
            "canonical_value": "identity service",
            "slot": "SERVICE",
            "description": "Authentication or identity provider service.",
            "tags": ["identity", "service"],
            "aliases": ["auth service", "idp", "identity provider"],
        },
        {
            "canonical_value": "billing service",
            "slot": "SERVICE",
            "description": "Billing or payments service.",
            "tags": ["payments", "service"],
            "aliases": ["billing api", "payments service", "billing svc"],
        },
        {
            "canonical_value": "github actions",
            "slot": "CI_SYSTEM",
            "description": "GitHub Actions CI/CD system.",
            "tags": ["automation", "ci"],
            "aliases": ["gh actions", "gha"],
        },
        {
            "canonical_value": "continuous integration",
            "slot": "CI_CONCEPT",
            "description": "Automated build and test workflow.",
            "tags": ["automation", "ci"],
            "aliases": ["ci", "build pipeline"],
        },
        {
            "canonical_value": "deployment",
            "slot": "CHANGE_TYPE",
            "description": "Production rollout or release deployment.",
            "tags": ["operations", "release"],
            "aliases": ["deploy", "rollout", "release rollout"],
        },
        {
            "canonical_value": "rollback",
            "slot": "CHANGE_ACTION",
            "description": "Revert a deployment or runtime change.",
            "tags": ["operations", "release"],
            "aliases": ["revert", "roll back"],
        },
        {
            "canonical_value": "database migration",
            "slot": "CHANGE_TYPE",
            "description": "Schema or data migration for a database.",
            "tags": ["database", "release"],
            "aliases": ["db migration", "schema migration", "migration"],
        },
        {
            "canonical_value": "critical incident",
            "slot": "SEVERITY",
            "description": "Highest-severity production incident.",
            "tags": ["incident", "priority"],
            "aliases": ["sev1", "sev-1", "p0", "major incident"],
        },
        {
            "canonical_value": "high priority incident",
            "slot": "SEVERITY",
            "description": "High-priority but non-critical incident.",
            "tags": ["incident", "priority"],
            "aliases": ["sev2", "sev-2", "p1"],
        },
        {
            "canonical_value": "timeout",
            "slot": "SYMPTOM",
            "description": "Request or job timed out.",
            "tags": ["incident", "latency"],
            "aliases": ["timed out", "time out"],
        },
        {
            "canonical_value": "latency",
            "slot": "SYMPTOM",
            "description": "Slow response or performance degradation.",
            "tags": ["incident", "performance"],
            "aliases": ["slow", "slowness", "latency spike"],
        },
        {
            "canonical_value": "outage",
            "slot": "SYMPTOM",
            "description": "Service unavailable or down.",
            "tags": ["incident", "availability"],
            "aliases": ["down", "service down", "incident outage"],
        },
        {
            "canonical_value": "runbook",
            "slot": "DOCUMENT_TYPE",
            "description": "Operational remediation guide.",
            "tags": ["docs", "operations"],
            "aliases": ["playbook", "ops guide"],
        },
        {
            "canonical_value": "postmortem",
            "slot": "DOCUMENT_TYPE",
            "description": "Incident review document.",
            "tags": ["docs", "incident"],
            "aliases": ["post-mortem", "incident review"],
        },
        {
            "canonical_value": "service level objective",
            "slot": "RELIABILITY_CONCEPT",
            "description": "Reliability target for a service.",
            "tags": ["reliability", "slo"],
            "aliases": ["slo", "service objective"],
        },
        {
            "canonical_value": "on-call rotation",
            "slot": "RELIABILITY_CONCEPT",
            "description": "Scheduled incident-response ownership.",
            "tags": ["incident", "operations"],
            "aliases": ["oncall", "on-call"],
        },
        {
            "canonical_value": "feature flag",
            "slot": "RELEASE_CONCEPT",
            "description": "Feature toggle used during rollout.",
            "tags": ["release", "runtime"],
            "aliases": ["ff", "feature toggle"],
        },
        {
            "canonical_value": "search index",
            "slot": "SEARCH_CONCEPT",
            "description": "Search collection or backend index.",
            "tags": ["index", "search"],
            "aliases": ["search alias", "index alias"],
        },
        {
            "canonical_value": "read replica",
            "slot": "DATABASE_CONCEPT",
            "description": "Read-only database replica.",
            "tags": ["database", "replication"],
            "aliases": ["replica", "db replica", "reader"],
        },
        {
            "canonical_value": "index shard",
            "slot": "SEARCH_CONCEPT",
            "description": "Search-index shard or partition.",
            "tags": ["index", "search"],
            "aliases": ["shard", "sharding"],
        },
        {
            "canonical_value": "runtime snapshot",
            "slot": "SKEINRANK_CONCEPT",
            "description": "Immutable terminology artifact served at runtime.",
            "tags": ["governance", "runtime"],
            "aliases": ["snapshot", "pinned snapshot"],
        },
        {
            "canonical_value": "ai inbox",
            "slot": "SKEINRANK_CONCEPT",
            "description": "Review queue for evidence-backed terminology proposals.",
            "tags": ["governance", "review"],
            "aliases": ["proposal inbox", "review inbox"],
        },
        {
            "canonical_value": "governance api",
            "slot": "SKEINRANK_COMPONENT",
            "description": "SkeinRank control-plane API.",
            "tags": ["api", "governance"],
            "aliases": ["control plane api", "governance api"],
        },
        {
            "canonical_value": "page layout",
            "slot": "DOCUMENT_CONCEPT",
            "description": "Page layout or frontend template context for ambiguous pg examples.",
            "tags": ["docs", "frontend"],
            "aliases": ["pg layout", "page template"],
        },
        {
            "canonical_value": "product group",
            "slot": "ORG_UNIT",
            "description": "Product group context for ambiguous pg examples.",
            "tags": ["org", "product"],
            "aliases": ["prod group", "pg dashboard"],
        },
    ],
    "profile_stop_list": [
        {
            "value": "app",
            "target": "alias",
            "reason": "too generic for the built-in demo matcher",
        },
        {
            "value": "service",
            "target": "alias",
            "reason": "too generic for the built-in demo matcher",
        },
        {
            "value": "platform",
            "target": "alias",
            "reason": "too generic for the built-in demo matcher",
        },
    ],
}


class SkeinRank:
    """Small deterministic facade for local canonicalization.

    Parameters
    ----------
    dictionary:
        Omit this argument to use the built-in demo dictionary. Pass a simple
        ``{canonical: [aliases...]}`` mapping for quick experiments, a full
        SkeinRank dictionary payload, a file path, or an existing ``Dictionary``.
    profile_name:
        Profile name used when a simple Python mapping is converted into a
        SkeinRank dictionary.
    default_slot:
        Slot assigned to simple mapping entries that do not specify one.
    """

    def __init__(
        self,
        dictionary: DictionarySource = None,
        *,
        profile_name: str = "inline_terms",
        default_slot: str = "TERM",
    ) -> None:
        self.dictionary = _coerce_dictionary(
            dictionary,
            profile_name=profile_name,
            default_slot=default_slot,
        )

    @classmethod
    def demo(cls) -> "SkeinRank":
        """Return a facade backed by the built-in platform-ops demo dictionary."""

        return cls(demo_dictionary())

    @classmethod
    def from_file(cls, path: str | Path) -> "SkeinRank":
        """Load a SkeinRank dictionary JSON/YAML file."""

        return cls(load_dictionary(path))

    def canonicalize(
        self,
        text: str,
        *,
        explain: bool = False,
        max_matches: int | None = None,
        context_chars: int = 48,
    ) -> str | CanonicalizedText:
        """Canonicalize text with this facade's dictionary.

        Returns a plain string by default. Pass ``explain=True`` to get the
        full ``CanonicalizedText`` object with replacement metadata.
        """

        result = canonicalize_text(
            text,
            dictionary=self.dictionary,
            max_matches=max_matches,
            context_chars=context_chars,
        )
        return result if explain else result.text

    def extract(
        self,
        text: str,
        *,
        explain: bool = False,
        max_matches: int | None = None,
        context_chars: int = 48,
    ) -> list[str] | ExtractionResult:
        """Extract canonical values from text.

        Returns ``list[str]`` by default. Pass ``explain=True`` to get the full
        ``ExtractionResult`` with offsets and highlighted evidence fragments.
        """

        result = extract_terms(
            text,
            dictionary=self.dictionary,
            max_matches=max_matches,
            context_chars=context_chars,
        )
        return result if explain else result.canonical_values


def canonicalize(
    text: str,
    *,
    dictionary: DictionarySource = None,
    explain: bool = False,
    max_matches: int | None = None,
    context_chars: int = 48,
) -> str | CanonicalizedText:
    """Canonicalize text with a demo or caller-supplied dictionary.

    This is the lowest-friction entrypoint:

    ``skeinrank.canonicalize("k8s pg timeout")``
    """

    return SkeinRank(dictionary).canonicalize(
        text,
        explain=explain,
        max_matches=max_matches,
        context_chars=context_chars,
    )


def extract(
    text: str,
    *,
    dictionary: DictionarySource = None,
    explain: bool = False,
    max_matches: int | None = None,
    context_chars: int = 48,
) -> list[str] | ExtractionResult:
    """Extract canonical values with a demo or caller-supplied dictionary."""

    return SkeinRank(dictionary).extract(
        text,
        explain=explain,
        max_matches=max_matches,
        context_chars=context_chars,
    )


def demo_dictionary() -> Dictionary:
    """Return a fresh built-in demo dictionary for platform-ops examples."""

    return load_dictionary(_DEMO_DICTIONARY_PAYLOAD)


def demo_dictionary_payload() -> dict[str, Any]:
    """Return a deep copy of the built-in demo dictionary payload."""

    return copy.deepcopy(_DEMO_DICTIONARY_PAYLOAD)


def _coerce_dictionary(
    source: DictionarySource,
    *,
    profile_name: str,
    default_slot: str,
) -> Dictionary:
    if source is None:
        return demo_dictionary()
    if isinstance(source, Dictionary):
        return source
    if isinstance(source, (str, Path)):
        return load_dictionary(source)
    if isinstance(source, Mapping):
        if _looks_like_dictionary_payload(source):
            return load_dictionary(source)
        return load_dictionary(
            _simple_mapping_to_dictionary_payload(
                source,
                profile_name=profile_name,
                default_slot=default_slot,
            )
        )
    raise TypeError(
        "dictionary must be omitted, a path, a Dictionary, a full dictionary "
        "payload, or a simple {canonical: aliases} mapping"
    )


def _looks_like_dictionary_payload(source: Mapping[str, Any]) -> bool:
    return any(
        key in source
        for key in (
            "schema_version",
            "profile_name",
            "profile_id",
            "terms",
            "canonical_terms",
        )
    )


def _simple_mapping_to_dictionary_payload(
    source: SimpleDictionary,
    *,
    profile_name: str,
    default_slot: str,
) -> dict[str, Any]:
    terms: list[dict[str, Any]] = []
    for canonical, raw_value in source.items():
        term = _simple_mapping_term(
            str(canonical),
            raw_value,
            default_slot=default_slot,
        )
        terms.append(term)
    return {
        "schema_version": DICTIONARY_SCHEMA_VERSION,
        "profile_name": profile_name,
        "terms": terms,
    }


def _simple_mapping_term(
    canonical: str,
    raw_value: SimpleDictionaryValue,
    *,
    default_slot: str,
) -> dict[str, Any]:
    if isinstance(raw_value, Mapping):
        aliases = raw_value.get("aliases", [])
        if isinstance(aliases, str):
            aliases = [aliases]
        return {
            "canonical_value": canonical,
            "slot": str(
                raw_value.get("slot") or raw_value.get("primary_slot") or default_slot
            ),
            "description": raw_value.get("description"),
            "tags": _string_list(raw_value.get("tags", [])),
            "aliases": _string_list(aliases),
        }
    if isinstance(raw_value, str):
        aliases = [raw_value]
    else:
        aliases = list(raw_value)
    return {
        "canonical_value": canonical,
        "slot": default_slot,
        "aliases": aliases,
    }


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence):
        return [str(item) for item in value]
    return [str(value)]
