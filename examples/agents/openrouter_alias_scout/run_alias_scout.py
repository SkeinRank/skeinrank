"""Reference OpenRouter alias scout runner skeleton.

Patch 40F intentionally keeps this runner LLM-free. It proves the agent-side
configuration, input loading, idempotency key strategy, and SkeinRank REST client
without introducing LangGraph/CrewAI or calling OpenRouter yet.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

try:  # pragma: no cover - import style depends on how the example is executed.
    from .candidate_discovery import (
        CandidateDiscoveryConfig,
        build_candidate_discovery_report,
        build_candidate_fact_pack,
        discover_alias_candidates,
    )
    from .evidence_sampler import (
        EvidenceSamplerConfig,
        build_candidate_evidence_pack,
        build_evidence_sampling_report,
        load_jsonl_records,
        sample_evidence_windows,
    )
    from .openrouter_tools import get_openrouter_tool_schemas
    from .prompts import (
        SYSTEM_PROMPT,
        build_alias_review_prompt,
        build_sample_candidate_pack,
    )
    from .skeinrank_client import SkeinRankAgentClient
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from candidate_discovery import (
        CandidateDiscoveryConfig,
        build_candidate_discovery_report,
        build_candidate_fact_pack,
        discover_alias_candidates,
    )
    from evidence_sampler import (
        EvidenceSamplerConfig,
        build_candidate_evidence_pack,
        build_evidence_sampling_report,
        load_jsonl_records,
        sample_evidence_windows,
    )
    from openrouter_tools import get_openrouter_tool_schemas
    from prompts import (
        SYSTEM_PROMPT,
        build_alias_review_prompt,
        build_sample_candidate_pack,
    )
    from skeinrank_client import SkeinRankAgentClient

JsonDict = dict[str, Any]


@dataclass(frozen=True)
class AgentRunnerConfig:
    """Runtime config for the reference alias scout runner."""

    skeinrank_api_url: str
    skeinrank_role: str
    api_token_env: str | None
    openrouter_api_key_env: str
    openrouter_model: str
    default_profile_name: str | None
    default_binding_id: int | None
    proposal_source_name: str
    failed_queries_path: Path
    evidence_records_path: Path
    max_queries_per_run: int
    candidate_discovery: CandidateDiscoveryConfig
    evidence_sampler: EvidenceSamplerConfig
    dry_run: bool = True

    @classmethod
    def from_file(cls, path: Path) -> "AgentRunnerConfig":
        raw = json.loads(path.read_text(encoding="utf-8"))
        base_dir = path.parent
        failed_queries = Path(
            raw.get("failed_queries_path", "failed_queries.example.jsonl")
        )
        if not failed_queries.is_absolute():
            failed_queries = base_dir / failed_queries
        evidence_records = Path(
            raw.get("evidence_records_path", "evidence_records.example.jsonl")
        )
        if not evidence_records.is_absolute():
            evidence_records = base_dir / evidence_records
        binding_id = raw.get("default_binding_id")
        return cls(
            skeinrank_api_url=str(
                os.getenv(
                    "SKEINRANK_AGENT_API_URL",
                    raw.get("skeinrank_api_url", "http://127.0.0.1:8010"),
                )
            ),
            skeinrank_role=str(
                os.getenv(
                    "SKEINRANK_AGENT_ROLE", raw.get("skeinrank_role", "contributor")
                )
            ),
            api_token_env=raw.get("api_token_env", "SKEINRANK_AGENT_API_TOKEN"),
            openrouter_api_key_env=str(
                raw.get("openrouter_api_key_env", "OPENROUTER_API_KEY")
            ),
            openrouter_model=str(raw.get("openrouter_model", "openai/gpt-4o-mini")),
            default_profile_name=raw.get("default_profile_name"),
            default_binding_id=int(binding_id) if binding_id is not None else None,
            proposal_source_name=str(
                raw.get("proposal_source_name", "openrouter-alias-scout")
            ),
            failed_queries_path=failed_queries,
            evidence_records_path=evidence_records,
            max_queries_per_run=int(raw.get("max_queries_per_run", 50)),
            candidate_discovery=CandidateDiscoveryConfig.from_mapping(
                raw.get("candidate_discovery")
            ),
            evidence_sampler=EvidenceSamplerConfig.from_mapping(
                raw.get("evidence_sampler")
            ),
            dry_run=bool(raw.get("dry_run", True)),
        )

    def api_token(self) -> str | None:
        """Read the configured SkeinRank API token from the environment."""

        return os.getenv(self.api_token_env) if self.api_token_env else None


def load_failed_queries(path: Path, *, limit: int | None = None) -> list[JsonDict]:
    """Load failed-query examples from JSONL for future candidate discovery."""

    rows: list[JsonDict] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if isinstance(value, str):
            value = {"query": value}
        if not isinstance(value, dict) or not value.get("query"):
            raise ValueError(f"Invalid failed query row at {path}:{line_number}")
        rows.append(value)
        if limit is not None and len(rows) >= limit:
            break
    return rows


def make_candidate_idempotency_key(
    *, source_name: str, binding_id: int | None, profile_name: str | None, query: str
) -> str:
    """Build a deterministic retry key for future proposals derived from a query."""

    scope = (
        f"binding:{binding_id}"
        if binding_id is not None
        else f"profile:{profile_name or 'unknown'}"
    )
    digest = sha256(query.strip().lower().encode("utf-8")).hexdigest()[:16]
    return f"{source_name}:{scope}:query:{digest}"


def build_run_plan(
    config: AgentRunnerConfig, failed_queries: list[JsonDict]
) -> JsonDict:
    """Return a deterministic dry-run plan for the agent foundation step."""

    scoped_queries = failed_queries[: config.max_queries_per_run]
    return {
        "schema_version": "skeinrank.agent_run_plan.v1",
        "runner": "openrouter_alias_scout",
        "llm_enabled": False,
        "dry_run": config.dry_run,
        "skeinrank_api_url": config.skeinrank_api_url,
        "openrouter_model": config.openrouter_model,
        "proposal_source_name": config.proposal_source_name,
        "default_profile_name": config.default_profile_name,
        "default_binding_id": config.default_binding_id,
        "queries_loaded": len(scoped_queries),
        "candidate_discovery_enabled": True,
        "evidence_sampling_enabled": True,
        "evidence_records_path": str(config.evidence_records_path),
        "next_steps": [
            "Patch 40G added OpenRouter tool schemas and prompts.",
            "Patch 40H added candidate discovery and pruning.",
            "Patch 40I adds compact evidence sampling.",
        ],
        "sample_queries": [
            {
                "query": row["query"],
                "idempotency_key": make_candidate_idempotency_key(
                    source_name=config.proposal_source_name,
                    binding_id=config.default_binding_id,
                    profile_name=config.default_profile_name,
                    query=row["query"],
                ),
            }
            for row in scoped_queries[:5]
        ],
    }


def build_client(config: AgentRunnerConfig) -> SkeinRankAgentClient:
    """Create the REST client used by the runner."""

    return SkeinRankAgentClient(
        base_url=config.skeinrank_api_url,
        role=config.skeinrank_role,
        api_token=config.api_token(),
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the SkeinRank alias scout skeleton."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).with_name("agent_config.example.json"),
        help="Path to agent config JSON.",
    )
    parser.add_argument(
        "--list-bindings",
        action="store_true",
        help="Call SkeinRank /v1/tools/bindings and print available contexts.",
    )
    parser.add_argument(
        "--dry-run-plan",
        action="store_true",
        help="Print the local dry-run plan without calling OpenRouter.",
    )
    parser.add_argument(
        "--print-tool-schemas",
        action="store_true",
        help="Print OpenRouter/OpenAI-compatible SkeinRank tool schemas.",
    )
    parser.add_argument(
        "--print-system-prompt",
        action="store_true",
        help="Print the alias scout system prompt.",
    )
    parser.add_argument(
        "--print-sample-review-prompt",
        action="store_true",
        help="Print a sample alias-review prompt for local inspection.",
    )
    parser.add_argument(
        "--discover-candidates",
        action="store_true",
        help="Mine alias-like candidates from failed-query JSONL without LLM calls.",
    )
    parser.add_argument(
        "--print-sample-candidate-pack",
        action="store_true",
        help="Print the top discovered candidate as a compact fact pack.",
    )
    parser.add_argument(
        "--sample-evidence",
        action="store_true",
        help="Sample compact evidence windows for discovered candidates without LLM calls.",
    )
    parser.add_argument(
        "--print-sample-evidence-pack",
        action="store_true",
        help="Print the top candidate with sampled evidence windows as an LLM-ready pack.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(sys.argv[1:] if argv is None else argv))
    config = AgentRunnerConfig.from_file(args.config)

    if args.print_tool_schemas:
        print(json.dumps(get_openrouter_tool_schemas(), indent=2, sort_keys=True))
        return 0

    if args.print_system_prompt:
        print(SYSTEM_PROMPT)
        return 0

    if args.print_sample_review_prompt:
        sample_pack = build_sample_candidate_pack()
        print(build_alias_review_prompt(sample_pack))
        return 0

    if args.list_bindings:
        client = build_client(config)
        bindings = client.list_bindings(profile_name=config.default_profile_name)
        print(json.dumps(bindings, indent=2, sort_keys=True))
        return 0

    failed_queries = load_failed_queries(
        config.failed_queries_path, limit=config.max_queries_per_run
    )

    if args.discover_candidates:
        report = build_candidate_discovery_report(
            failed_queries,
            config=config.candidate_discovery,
            binding_id=config.default_binding_id,
            profile_name=config.default_profile_name,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.print_sample_candidate_pack:
        candidates = discover_alias_candidates(
            failed_queries, config=config.candidate_discovery
        )
        if not candidates:
            raise RuntimeError("No candidates discovered from failed-query input.")
        pack = build_candidate_fact_pack(
            candidates[0],
            binding_id=config.default_binding_id,
            profile_name=config.default_profile_name,
        )
        print(json.dumps(pack, indent=2, sort_keys=True))
        return 0

    if args.sample_evidence:
        candidates = discover_alias_candidates(
            failed_queries, config=config.candidate_discovery
        )
        evidence_records = load_jsonl_records(
            config.evidence_records_path, limit=config.evidence_sampler.max_records
        )
        report = build_evidence_sampling_report(
            candidates,
            evidence_records,
            config=config.evidence_sampler,
            binding_id=config.default_binding_id,
            profile_name=config.default_profile_name,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.print_sample_evidence_pack:
        candidates = discover_alias_candidates(
            failed_queries, config=config.candidate_discovery
        )
        if not candidates:
            raise RuntimeError("No candidates discovered from failed-query input.")
        evidence_records = load_jsonl_records(
            config.evidence_records_path, limit=config.evidence_sampler.max_records
        )
        windows = sample_evidence_windows(
            candidates[0].surface, evidence_records, config=config.evidence_sampler
        )
        if not windows:
            raise RuntimeError("No evidence windows found for the top candidate.")
        pack = build_candidate_evidence_pack(
            candidates[0],
            windows,
            binding_id=config.default_binding_id,
            profile_name=config.default_profile_name,
        )
        print(json.dumps(pack, indent=2, sort_keys=True))
        return 0

    plan = build_run_plan(config, failed_queries)
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
