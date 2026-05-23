"""Prompt templates for the reference OpenRouter alias scout.

The prompts are intentionally strict: the model may recommend proposals, but the
runner must still validate them through SkeinRank before anything is saved.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

JsonDict = dict[str, Any]

SYSTEM_PROMPT = """You are the SkeinRank OpenRouter Alias Scout.

Your job is to review compact failed-search evidence and decide whether an
observed surface form should become a SkeinRank alias proposal.

Safety contract:
- Never claim that a proposal was applied, approved, or published.
- Never mutate terminology directly. You may only recommend validation or a
  pending proposal through SkeinRank tools.
- Prefer binding_id when it is available; use profile_name only for preview/dev
  contexts.
- Reject noisy strings, generic words, one-off typos, secrets, IDs, UUIDs,
  credentials, emails, URLs, and user/private data.
- Reject candidates without enough evidence.
- If a surface form is ambiguous, use needs_evidence unless the binding context
  and evidence strongly disambiguate it.
- Keep source_payload compact: counts, windows, conflicts, and short evidence
  snippets only. Do not send full documents to the LLM or to proposals.
- Output only JSON that matches one of these actions: propose, reject, or
  needs_evidence.
""".strip()

ALIAS_REVIEW_OUTPUT_SCHEMA: JsonDict = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["propose", "reject", "needs_evidence"]},
        "alias_value": {"type": "string"},
        "canonical_value": {"type": "string"},
        "slot": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string"},
        "context": {"type": "string"},
        "risk_flags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["action", "reason", "confidence", "risk_flags"],
    "additionalProperties": False,
}


def build_candidate_pack(
    *,
    candidate_alias: str,
    possible_canonical: str | None = None,
    slot: str | None = None,
    binding_id: int | None = None,
    profile_name: str | None = None,
    evidence: Sequence[str] = (),
    stats: Mapping[str, Any] | None = None,
    known_conflicts: Sequence[str] = (),
) -> JsonDict:
    """Build the compact evidence pack reviewed by the LLM.

    Patch 40G only provides the shape. Later candidate discovery/evidence patches
    will build these packs from failed queries and document windows.
    """

    pack: JsonDict = {
        "candidate_alias": candidate_alias.strip(),
        "possible_canonical": possible_canonical.strip()
        if possible_canonical
        else None,
        "slot": slot.strip() if slot else None,
        "binding_id": binding_id,
        "profile_name": profile_name,
        "evidence": [item.strip() for item in evidence if item.strip()],
        "stats": dict(stats or {}),
        "known_conflicts": [item.strip() for item in known_conflicts if item.strip()],
    }
    return pack


def build_alias_review_prompt(candidate_pack: Mapping[str, Any]) -> str:
    """Return a deterministic prompt for reviewing one alias candidate."""

    return "\n".join(
        [
            "Review this SkeinRank alias candidate.",
            "Return only JSON matching the provided schema.",
            "",
            "Decision rules:",
            "1. Use action=propose only when evidence strongly maps alias to canonical.",
            "2. Use action=reject for generic/noisy/private/unsafe candidates.",
            "3. Use action=needs_evidence when ambiguity remains or evidence is weak.",
            "4. Confidence must be between 0 and 1.",
            "5. For action=propose, include alias_value, canonical_value, slot, context.",
            "",
            "Output JSON schema:",
            json.dumps(ALIAS_REVIEW_OUTPUT_SCHEMA, ensure_ascii=False, indent=2),
            "",
            "Candidate pack:",
            json.dumps(
                dict(candidate_pack), ensure_ascii=False, indent=2, sort_keys=True
            ),
        ]
    )


def build_sample_candidate_pack() -> JsonDict:
    """Return a tiny deterministic sample for CLI preview and tests."""

    return build_candidate_pack(
        candidate_alias="pg",
        possible_canonical="postgresql",
        slot="database",
        profile_name="infra_incidents",
        evidence=(
            "pg timeout after failover in production cluster",
            "postgres connection pool exhausted during incident",
            "runbook: pg restart requires approval",
        ),
        stats={"query_count": 42, "document_count": 17, "no_hit_queries": 9},
        known_conflicts=("page", "product_group"),
    )
