"""Company model integration planning for the alias scout example.

Patch 57C adds an operator-facing integration plan for companies that want to
run the alias scout with their own model endpoint. The plan is intentionally
read-only: it validates configuration shape, prints safe commands, and never
contacts OpenRouter, a local endpoint, Elasticsearch, or the Governance API.
"""

from __future__ import annotations

from typing import Any

try:  # pragma: no cover - import style depends on how the example is executed.
    from .model_provider import ModelProviderConfig, build_model_provider_plan
except ImportError:  # pragma: no cover
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from model_provider import ModelProviderConfig, build_model_provider_plan

JsonDict = dict[str, Any]
COMPANY_MODEL_INTEGRATION_PLAN_VERSION = "skeinrank.company_model_integration_plan.v1"


def _provider_checks(config: ModelProviderConfig) -> list[JsonDict]:
    provider_type = config.provider_type.lower().strip().replace("-", "_")
    supported = provider_type in {"openrouter", "local_endpoint", "mock"}
    checks: list[JsonDict] = [
        {
            "name": "provider_type_supported",
            "status": "passed" if supported else "failed",
            "message": (
                "Provider type is supported."
                if supported
                else "Provider type is not supported by the alias scout."
            ),
            "details": {
                "provider_type": provider_type,
                "supported_provider_types": ["openrouter", "local_endpoint", "mock"],
            },
        },
        {
            "name": "secret_redaction",
            "status": "passed",
            "message": "Provider plans do not include raw API key values.",
            "details": {"api_key_env": config.api_key_env},
        },
        {
            "name": "json_response_format",
            "status": "passed",
            "message": "Alias scout requests JSON responses from chat-completion providers.",
            "details": {"response_format": {"type": "json_object"}},
        },
    ]
    if provider_type == "local_endpoint":
        base_url_ok = config.base_url.rstrip("/").endswith("/v1")
        checks.append(
            {
                "name": "local_endpoint_base_url",
                "status": "passed" if base_url_ok else "warning",
                "message": (
                    "Local endpoint base URL ends with /v1."
                    if base_url_ok
                    else "Most local OpenAI-compatible gateways expect a /v1 base URL."
                ),
                "details": {"base_url": config.base_url},
            }
        )
        checks.append(
            {
                "name": "local_endpoint_api_key_policy",
                "status": "passed",
                "message": (
                    "Local endpoint does not require an API key by default."
                    if not config.requires_api_key
                    else "Local endpoint requires an API key from the configured env var."
                ),
                "details": {
                    "requires_api_key": config.requires_api_key,
                    "api_key_env": config.api_key_env,
                },
            }
        )
    return checks


def build_company_model_integration_plan(
    config: ModelProviderConfig,
    *,
    skeinrank_api_url: str = "http://127.0.0.1:8010",
    profile_name: str | None = None,
    binding_id: int | None = None,
    report_path: str = (
        "examples/agents/openrouter_alias_scout/reports/live-pilot/"
        "company-model-provider-smoke-report.json"
    ),
) -> JsonDict:
    """Build a redaction-safe company model integration plan.

    The returned plan is meant for docs, support handoff, and CI assertions. It
    gives operators exact existing commands to run, but it does not execute any
    provider or API call itself.
    """

    provider_plan = build_model_provider_plan(config)
    provider_type = config.provider_type.lower().strip().replace("-", "_")
    local_env = {
        "SKEINRANK_MODEL_PROVIDER_TYPE": "local_endpoint",
        "SKEINRANK_MODEL_PROVIDER_BASE_URL": config.base_url
        if provider_type == "local_endpoint"
        else "http://127.0.0.1:8000/v1",
        "SKEINRANK_MODEL_PROVIDER_MODEL": config.model
        if provider_type == "local_endpoint"
        else "local-model",
        "SKEINRANK_LOCAL_MODEL_API_KEY": "<optional-token>",
    }
    preview_command = (
        "SKEINRANK_MODEL_PROVIDER_TYPE=local_endpoint "
        "SKEINRANK_MODEL_PROVIDER_BASE_URL=$SKEINRANK_MODEL_PROVIDER_BASE_URL "
        "SKEINRANK_MODEL_PROVIDER_MODEL=$SKEINRANK_MODEL_PROVIDER_MODEL "
        "python examples/agents/openrouter_alias_scout/run_alias_scout.py "
        "--print-model-provider-plan"
    )
    smoke_command = (
        "SKEINRANK_MODEL_PROVIDER_TYPE=local_endpoint "
        "SKEINRANK_MODEL_PROVIDER_BASE_URL=$SKEINRANK_MODEL_PROVIDER_BASE_URL "
        "SKEINRANK_MODEL_PROVIDER_MODEL=$SKEINRANK_MODEL_PROVIDER_MODEL "
        "python examples/agents/openrouter_alias_scout/run_alias_scout.py "
        "--run-openrouter-live-pilot "
        f"--write-openrouter-live-pilot-report {report_path} "
        "--max-candidates 1 --max-llm-calls 1 --max-run-cost-usd 0.01"
    )
    validated_command = (
        "SKEINRANK_MODEL_PROVIDER_TYPE=local_endpoint "
        "SKEINRANK_MODEL_PROVIDER_BASE_URL=$SKEINRANK_MODEL_PROVIDER_BASE_URL "
        "SKEINRANK_MODEL_PROVIDER_MODEL=$SKEINRANK_MODEL_PROVIDER_MODEL "
        "python examples/agents/openrouter_alias_scout/run_alias_scout.py "
        "--write-openrouter-validated-pilot-report "
        "examples/agents/openrouter_alias_scout/reports/live-pilot/"
        "company-model-provider-validated-report.json "
        f"--profile-name {profile_name or '<profile-name>'} "
        "--max-candidates 1 --max-llm-calls 1 --max-proposals 1 "
        "--max-run-cost-usd 0.01"
    )
    return {
        "schema_version": COMPANY_MODEL_INTEGRATION_PLAN_VERSION,
        "status": "planned",
        "provider_plan": provider_plan,
        "company_model": {
            "recommended_provider_type": "local_endpoint",
            "current_provider_type": config.provider_type,
            "base_url": config.base_url,
            "model": config.model,
            "api_key_env": config.api_key_env,
            "requires_api_key": config.requires_api_key,
            "api_key_value": None,
        },
        "skeinrank_context": {
            "api_url": skeinrank_api_url,
            "profile_name": profile_name,
            "binding_id": binding_id,
        },
        "checks": _provider_checks(config),
        "environment_template": local_env,
        "commands": {
            "preview_provider_plan": preview_command,
            "one_call_smoke": smoke_command,
            "validated_pilot_after_seeding": validated_command,
        },
        "integration_steps": [
            "Start the company model server with an OpenAI-compatible /chat/completions endpoint.",
            "Export SKEINRANK_MODEL_PROVIDER_TYPE=local_endpoint and set base URL/model env vars.",
            "Run --print-model-provider-plan and confirm network_calls=false and secrets_included=false.",
            "Run a one-call smoke with max_llm_calls=1 and max_run_cost_usd=0.01.",
            "Seed or select an existing SkeinRank profile/binding before validated pilot mode.",
            "Run the validated pilot and review validation_passed/warning/blocked counts.",
        ],
        "output_checks": [
            "model_provider.provider_type should equal local_endpoint for company endpoint runs.",
            "provider_calls should be true only for explicit live smoke/pilot commands.",
            "proposal_submission_enabled should stay false unless explicitly enabled.",
            "secrets should not appear in provider plans, reports, or support bundles.",
        ],
        "safety": {
            "network_calls": False,
            "openrouter_calls": False,
            "local_endpoint_calls": False,
            "skeinrank_api_calls": False,
            "requires_explicit_live_run": True,
            "runtime_mutation_enabled": False,
            "proposal_submission_default": False,
            "snapshot_publish_enabled": False,
            "secrets_included": False,
        },
        "notes": [
            "The historical live pilot flag name still contains openrouter for compatibility.",
            "When SKEINRANK_MODEL_PROVIDER_TYPE=local_endpoint is set, the live pilot uses the configured model provider.",
        ],
    }
