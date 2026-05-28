"""Operational role-boundary helpers for agent/reviewer/admin workflows.

The governance data model intentionally keeps the existing stable roles:
``admin``, ``moderator``, and ``contributor``.  This module maps those roles to
operator-facing boundaries used by production agent workflows:

* contributor -> agent boundary: propose/validate/read only
* moderator -> reviewer boundary: review/approve/reject, no apply/publish
* admin -> admin boundary: apply/publish/admin operations

The helpers are side-effect free and are used by docs/tests/API responses to keep
RBAC decisions explicit without adding migrations or new user-role values.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .auth import AuthContext

ROLE_BOUNDARIES_SCHEMA_VERSION = "skeinrank.role_boundaries.v1"


@dataclass(frozen=True)
class RoleBoundary:
    """Operator-facing role boundary mapped to existing governance roles."""

    boundary: str
    governance_roles: tuple[str, ...]
    may_read: bool
    may_validate: bool
    may_propose: bool
    may_approve_reject: bool
    may_batch_apply: bool
    may_publish_snapshot: bool
    may_manage_users_tokens: bool
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "boundary": self.boundary,
            "governance_roles": list(self.governance_roles),
            "may_read": self.may_read,
            "may_validate": self.may_validate,
            "may_propose": self.may_propose,
            "may_approve_reject": self.may_approve_reject,
            "may_batch_apply": self.may_batch_apply,
            "may_publish_snapshot": self.may_publish_snapshot,
            "may_manage_users_tokens": self.may_manage_users_tokens,
            "description": self.description,
        }


ROLE_BOUNDARIES: tuple[RoleBoundary, ...] = (
    RoleBoundary(
        boundary="agent",
        governance_roles=("contributor",),
        may_read=True,
        may_validate=True,
        may_propose=True,
        may_approve_reject=False,
        may_batch_apply=False,
        may_publish_snapshot=False,
        may_manage_users_tokens=False,
        description=(
            "Agents and contributor tokens can read context, validate candidates, "
            "and submit pending proposals for human review."
        ),
    ),
    RoleBoundary(
        boundary="reviewer",
        governance_roles=("moderator",),
        may_read=True,
        may_validate=True,
        may_propose=True,
        may_approve_reject=True,
        may_batch_apply=False,
        may_publish_snapshot=False,
        may_manage_users_tokens=False,
        description=(
            "Reviewers can approve/reject proposals after evidence review, but "
            "cannot batch-apply or publish runtime snapshots."
        ),
    ),
    RoleBoundary(
        boundary="admin",
        governance_roles=("admin",),
        may_read=True,
        may_validate=True,
        may_propose=True,
        may_approve_reject=True,
        may_batch_apply=True,
        may_publish_snapshot=True,
        may_manage_users_tokens=True,
        description=(
            "Admins can apply reviewed proposal batches, publish runtime snapshots, "
            "and manage users/service tokens."
        ),
    ),
)

_ROLE_TO_BOUNDARY = {
    role: boundary.boundary
    for boundary in ROLE_BOUNDARIES
    for role in boundary.governance_roles
}
_BOUNDARY_TO_MODEL = {boundary.boundary: boundary for boundary in ROLE_BOUNDARIES}


def operational_boundary_for_role(role: str) -> str:
    """Return the operator-facing boundary for a stable governance role."""

    return _ROLE_TO_BOUNDARY.get(role, "unknown")


def role_boundary_for_auth_context(user: AuthContext) -> dict[str, Any]:
    """Return the boundary summary for an authenticated user context."""

    boundary_name = operational_boundary_for_role(user.role)
    boundary = _BOUNDARY_TO_MODEL.get(boundary_name)
    payload: dict[str, Any] = {
        "schema_version": ROLE_BOUNDARIES_SCHEMA_VERSION,
        "username": user.username,
        "role": user.role,
        "auth_type": user.auth_type,
        "boundary": boundary_name,
        "scopes": sorted(user.scopes or []),
    }
    if boundary is not None:
        payload["capabilities"] = boundary.to_dict()
    else:
        payload["capabilities"] = {}
    return payload


def role_boundaries_document() -> dict[str, Any]:
    """Return the stable role-boundary document exposed by the API."""

    return {
        "schema_version": ROLE_BOUNDARIES_SCHEMA_VERSION,
        "boundaries": [boundary.to_dict() for boundary in ROLE_BOUNDARIES],
        "rules": {
            "agent": [
                "may_validate_alias_candidates",
                "may_submit_pending_proposals",
                "must_not_approve_reject_apply_or_publish",
            ],
            "reviewer": [
                "may_review_approve_or_reject_pending_proposals",
                "may_preview_batches",
                "must_not_apply_batches_or_publish_snapshots",
            ],
            "admin": [
                "may_apply_reviewed_batches",
                "may_publish_runtime_snapshots",
                "may_manage_users_and_service_tokens",
            ],
        },
        "service_token_note": (
            "API tokens still require explicit scopes. A contributor/service token "
            "with agent:tools:validate can validate only; proposal writes require "
            "agent:tools:suggest; apply/publish routes require an admin role."
        ),
    }


def role_boundary_allows(boundary_payload: Mapping[str, Any], capability: str) -> bool:
    """Return a boolean capability from a boundary payload."""

    capabilities = boundary_payload.get("capabilities")
    if not isinstance(capabilities, Mapping):
        return False
    return bool(capabilities.get(capability))
