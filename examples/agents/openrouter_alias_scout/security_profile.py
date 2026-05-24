"""Security profile helpers for the OpenRouter alias scout.

Patch 40L keeps the reference agent safe by default. The agent may call
OpenRouter for review, but proposal submission and runtime mutation stay
blocked unless a later patch enables them through explicit policy, scoped
credentials, and validation.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

JsonDict = dict[str, Any]

DEFAULT_BLOCKED_ACTIONS = (
    "direct_dictionary_write",
    "snapshot_publish",
    "direct_git_push",
    "runtime_mutation",
)
DEFAULT_ALLOWED_TOOL_PATHS = (
    "GET /v1/tools/bindings",
    "POST /v1/tools/explain-query",
    "POST /v1/tools/validate-alias",
    "POST /v1/tools/suggest-alias",
)


@dataclass(frozen=True)
class SecurityProfileConfig:
    """Security settings for the reference agent runner."""

    service_account_name: str = "openrouter-alias-scout"
    required_role: str = "contributor"
    allowed_roles: tuple[str, ...] = ("contributor",)
    allow_proposal_submission: bool = False
    allow_runtime_mutation: bool = False
    require_skeinrank_api_token_for_submission: bool = True
    blocked_actions: tuple[str, ...] = field(
        default_factory=lambda: DEFAULT_BLOCKED_ACTIONS
    )
    allowed_skeinrank_tool_paths: tuple[str, ...] = field(
        default_factory=lambda: DEFAULT_ALLOWED_TOOL_PATHS
    )
    redact_env_values: bool = True

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "SecurityProfileConfig":
        """Create config from optional JSON config values."""

        if not raw:
            return cls()
        allowed_roles = tuple(
            str(value) for value in raw.get("allowed_roles", cls.allowed_roles)
        )
        blocked_actions = tuple(
            str(value) for value in raw.get("blocked_actions", DEFAULT_BLOCKED_ACTIONS)
        )
        allowed_paths = tuple(
            str(value)
            for value in raw.get(
                "allowed_skeinrank_tool_paths", DEFAULT_ALLOWED_TOOL_PATHS
            )
        )
        return cls(
            service_account_name=str(
                raw.get("service_account_name", cls.service_account_name)
            ),
            required_role=str(raw.get("required_role", cls.required_role)),
            allowed_roles=allowed_roles or cls.allowed_roles,
            allow_proposal_submission=bool(
                raw.get("allow_proposal_submission", cls.allow_proposal_submission)
            ),
            allow_runtime_mutation=bool(
                raw.get("allow_runtime_mutation", cls.allow_runtime_mutation)
            ),
            require_skeinrank_api_token_for_submission=bool(
                raw.get(
                    "require_skeinrank_api_token_for_submission",
                    cls.require_skeinrank_api_token_for_submission,
                )
            ),
            blocked_actions=blocked_actions or DEFAULT_BLOCKED_ACTIONS,
            allowed_skeinrank_tool_paths=allowed_paths or DEFAULT_ALLOWED_TOOL_PATHS,
            redact_env_values=bool(raw.get("redact_env_values", cls.redact_env_values)),
        )


def env_var_status(env_var: str | None) -> JsonDict:
    """Return redacted status for a secret-bearing environment variable."""

    if not env_var:
        return {"env_var": None, "configured": False, "redacted": True}
    value = os.getenv(env_var)
    return {
        "env_var": env_var,
        "configured": bool(value),
        "redacted": True,
        "value_preview": _secret_preview(value) if value else None,
    }


def build_security_profile_report(
    *,
    security_config: SecurityProfileConfig | None = None,
    skeinrank_api_url: str,
    skeinrank_role: str,
    api_token_env: str | None,
    openrouter_api_key_env: str,
    proposal_source_name: str,
    dry_run: bool,
    llm_submit_proposals: bool,
) -> JsonDict:
    """Build a sanitized agent security report without calling any network API."""

    cfg = security_config or SecurityProfileConfig()
    role_allowed = skeinrank_role in cfg.allowed_roles
    role_matches_required = skeinrank_role == cfg.required_role
    api_token = env_var_status(api_token_env)
    openrouter_key = env_var_status(openrouter_api_key_env)
    submission_ready = _proposal_submission_ready(
        cfg=cfg,
        llm_submit_proposals=llm_submit_proposals,
        role_allowed=role_allowed,
        api_token_configured=bool(api_token["configured"]),
    )
    report: JsonDict = {
        "schema_version": "skeinrank.agent_security_profile.v1",
        "runner": "openrouter_alias_scout",
        "proposal_source_name": proposal_source_name,
        "service_account_name": cfg.service_account_name,
        "skeinrank_api_url": skeinrank_api_url,
        "skeinrank_role": skeinrank_role,
        "dry_run": dry_run,
        "auth": {
            "skeinrank_api_token": api_token,
            "openrouter_api_key": openrouter_key,
        },
        "roles": {
            "required_role": cfg.required_role,
            "allowed_roles": list(cfg.allowed_roles),
            "role_matches_required": role_matches_required,
            "role_allowed": role_allowed,
        },
        "proposal_submission": submission_ready,
        "runtime_mutation": {
            "allowed": cfg.allow_runtime_mutation,
            "agent_may_mutate_runtime": False,
            "reason": "Runtime mutation and snapshot publishing are blocked for the reference agent.",
        },
        "allowed_skeinrank_tool_paths": list(cfg.allowed_skeinrank_tool_paths),
        "blocked_actions": list(cfg.blocked_actions),
        "recommendations": _security_recommendations(
            cfg=cfg,
            llm_submit_proposals=llm_submit_proposals,
            role_allowed=role_allowed,
            api_token_configured=bool(api_token["configured"]),
        ),
    }
    report["findings"] = validate_security_profile_report(report)
    report["status"] = "ok" if not _has_error_findings(report["findings"]) else "error"
    return report


def validate_security_profile_report(report: Mapping[str, Any]) -> list[JsonDict]:
    """Return actionable security findings for a generated report."""

    findings: list[JsonDict] = []
    proposal_submission = report.get("proposal_submission", {})
    roles = report.get("roles", {})
    runtime_mutation = report.get("runtime_mutation", {})

    if not roles.get("role_allowed", False):
        findings.append(
            {
                "level": "error",
                "code": "agent_role_not_allowed",
                "message": "The configured SkeinRank role is not allowed for this agent profile.",
            }
        )
    if proposal_submission.get(
        "configured_in_llm_review"
    ) and not proposal_submission.get("security_policy_allows_submission"):
        findings.append(
            {
                "level": "error",
                "code": "proposal_submission_blocked_by_policy",
                "message": "llm_review.submit_proposals is true, but the security profile does not allow submission.",
            }
        )
    if proposal_submission.get(
        "configured_in_llm_review"
    ) and not proposal_submission.get("api_token_configured"):
        findings.append(
            {
                "level": "error",
                "code": "proposal_submission_requires_api_token",
                "message": "Proposal submission requires a scoped SKEINRANK_AGENT_API_TOKEN.",
            }
        )
    if runtime_mutation.get("allowed"):
        findings.append(
            {
                "level": "error",
                "code": "runtime_mutation_not_supported",
                "message": "The reference agent must not publish snapshots or mutate runtime state.",
            }
        )
    if not proposal_submission.get("configured_in_llm_review"):
        findings.append(
            {
                "level": "info",
                "code": "proposal_submission_disabled",
                "message": "Proposal submission is disabled; the agent can only prepare payloads.",
            }
        )
    return findings


def assert_security_allows_llm_review(
    *,
    security_config: SecurityProfileConfig,
    skeinrank_role: str,
    api_token_env: str | None,
    llm_submit_proposals: bool,
) -> None:
    """Fail fast for dangerous live review settings before model calls happen."""

    role_allowed = skeinrank_role in security_config.allowed_roles
    token_configured = bool(os.getenv(api_token_env)) if api_token_env else False
    if not role_allowed:
        raise RuntimeError(
            "Agent security profile rejected the configured SkeinRank role: "
            f"{skeinrank_role!r}."
        )
    if security_config.allow_runtime_mutation:
        raise RuntimeError(
            "Agent security profile cannot allow runtime mutation for this reference runner."
        )
    if llm_submit_proposals and not security_config.allow_proposal_submission:
        raise RuntimeError(
            "Proposal submission is blocked by the agent security profile. "
            "Keep llm_review.submit_proposals=false until Patch 40L+ submission "
            "policy and scoped tokens are configured."
        )
    if (
        llm_submit_proposals
        and security_config.require_skeinrank_api_token_for_submission
        and not token_configured
    ):
        raise RuntimeError(
            "Proposal submission requires a scoped SKEINRANK_AGENT_API_TOKEN."
        )


def _proposal_submission_ready(
    *,
    cfg: SecurityProfileConfig,
    llm_submit_proposals: bool,
    role_allowed: bool,
    api_token_configured: bool,
) -> JsonDict:
    ready = (
        llm_submit_proposals
        and cfg.allow_proposal_submission
        and role_allowed
        and (api_token_configured or not cfg.require_skeinrank_api_token_for_submission)
    )
    return {
        "configured_in_llm_review": llm_submit_proposals,
        "security_policy_allows_submission": cfg.allow_proposal_submission,
        "requires_skeinrank_api_token": cfg.require_skeinrank_api_token_for_submission,
        "api_token_configured": api_token_configured,
        "ready": ready,
        "will_submit_proposals": False,
        "reason": (
            "The reference runner does not submit proposals in Patch 40L; it only "
            "prepares payloads for validation/submission in later patches."
        ),
    }


def _security_recommendations(
    *,
    cfg: SecurityProfileConfig,
    llm_submit_proposals: bool,
    role_allowed: bool,
    api_token_configured: bool,
) -> list[str]:
    recommendations = [
        "Use a contributor/service-account token instead of an admin token.",
        "Keep OPENROUTER_API_KEY and SKEINRANK_AGENT_API_TOKEN out of Git.",
        "Keep snapshot publishing outside the agent runner.",
    ]
    if not role_allowed:
        recommendations.append(
            f"Set SKEINRANK_AGENT_ROLE to one of: {', '.join(cfg.allowed_roles)}."
        )
    if llm_submit_proposals and not cfg.allow_proposal_submission:
        recommendations.append(
            "Set security_profile.allow_proposal_submission only after proposal submission policy is implemented."
        )
    if llm_submit_proposals and not api_token_configured:
        recommendations.append(
            "Export SKEINRANK_AGENT_API_TOKEN before live proposal submission."
        )
    return recommendations


def _has_error_findings(findings: Sequence[Mapping[str, Any]]) -> bool:
    return any(finding.get("level") == "error" for finding in findings)


def _secret_preview(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"
