"""Scoped agent credential policy helpers.

The helpers in this module are intentionally read-only. They describe the
least-privilege service-account shapes that scheduled agents should use, while
runtime enforcement continues to happen through existing role and API-token
scope checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = "skeinrank.scoped_agent_credentials.v1"


@dataclass(frozen=True)
class AgentCredentialProfile:
    """One recommended service-token profile for an agent workflow."""

    name: str
    role: str
    scopes: tuple[str, ...]
    description: str
    can_submit_proposals: bool = False
    can_mutate_runtime: bool = False
    rotation_note: str = "Rotate with the service-account token rotation endpoint."

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "scopes": list(self.scopes),
            "description": self.description,
            "can_submit_proposals": self.can_submit_proposals,
            "can_mutate_runtime": self.can_mutate_runtime,
            "rotation_note": self.rotation_note,
        }


READ_ONLY_AGENT_SCOPES = (
    "agent:runs:read",
    "agent:tracking:read",
    "agent:tools:read",
    "agent:tools:validate",
    "ops:reports:read",
)

PROPOSAL_AGENT_SCOPES = (
    "agent:runs:read",
    "agent:runs:write",
    "agent:tracking:read",
    "agent:tracking:write",
    "agent:tools:read",
    "agent:tools:validate",
    "agent:tools:suggest",
    "agent:tools:explain",
    "ops:reports:read",
)

TRACKING_WRITER_SCOPES = (
    "agent:runs:read",
    "agent:runs:write",
    "agent:tracking:read",
    "agent:tracking:write",
    "ops:reports:read",
)

RECOMMENDED_AGENT_CREDENTIALS = (
    AgentCredentialProfile(
        name="agent-readonly-validator",
        role="contributor",
        scopes=READ_ONLY_AGENT_SCOPES,
        description=(
            "Read-only agent credential for validation, run/report reads, and "
            "candidate checks. It cannot submit proposals."
        ),
    ),
    AgentCredentialProfile(
        name="agent-proposal-writer",
        role="contributor",
        scopes=PROPOSAL_AGENT_SCOPES,
        description=(
            "Proposal-writing agent credential. It can validate candidates and "
            "submit pending suggestions, but it cannot approve, apply, or publish."
        ),
        can_submit_proposals=True,
    ),
    AgentCredentialProfile(
        name="agent-tracking-writer",
        role="contributor",
        scopes=TRACKING_WRITER_SCOPES,
        description=(
            "Tracking-only credential for long-running workers that register runs "
            "and persist document/candidate/LLM review metadata."
        ),
    ),
)


def build_scoped_agent_credentials_policy(
    *, current_user: str | None = None
) -> dict[str, Any]:
    """Return a stable, serializable least-privilege credential policy."""

    return {
        "schema_version": SCHEMA_VERSION,
        "current_user": current_user,
        "recommended_credentials": [
            credential.as_dict() for credential in RECOMMENDED_AGENT_CREDENTIALS
        ],
        "rotation": {
            "endpoint": (
                "POST /v1/auth/service-accounts/{account_name}/tokens/{token_id}/rotate"
            ),
            "plaintext_token_returned_once": True,
            "old_token_revoked_by_default": True,
            "no_raw_token_logging": True,
            "recommended_steps": [
                "create or choose a scoped contributor service account",
                "rotate the service-account token",
                "store the new token in the deployment secret store",
                "restart the agent worker with the new token",
                "verify the old token no longer authenticates",
            ],
        },
        "safety": {
            "auto_apply_allowed": False,
            "runtime_mutation_allowed": False,
            "snapshot_publish_allowed": False,
            "admin_service_tokens_recommended_for_agents": False,
        },
    }
