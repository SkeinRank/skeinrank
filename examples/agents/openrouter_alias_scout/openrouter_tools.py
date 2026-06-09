"""OpenRouter/OpenAI-compatible tool schemas for the alias scout example.

Tool calling stays a contract-only layer: the schemas describe the existing
SkeinRank `/v1/tools/*` facade, but this module does not call OpenRouter and does
not execute model-requested tools. Runners can wire these schemas to candidate
discovery and evidence sampling while keeping mutation boundaries explicit.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

JsonDict = dict[str, Any]

TOOL_LIST_BINDINGS = "skeinrank_list_bindings"
TOOL_EXPLAIN_QUERY = "skeinrank_explain_query"
TOOL_VALIDATE_ALIAS = "skeinrank_validate_alias"
TOOL_SUBMIT_ALIAS_PROPOSAL = "skeinrank_submit_alias_proposal"

_TOOL_ORDER = (
    TOOL_LIST_BINDINGS,
    TOOL_EXPLAIN_QUERY,
    TOOL_VALIDATE_ALIAS,
    TOOL_SUBMIT_ALIAS_PROPOSAL,
)


def _object_schema(
    *,
    properties: Mapping[str, Any],
    required: Sequence[str] = (),
    additional_properties: bool = False,
) -> JsonDict:
    schema: JsonDict = {
        "type": "object",
        "properties": dict(properties),
        "additionalProperties": additional_properties,
    }
    if required:
        schema["required"] = list(required)
    return schema


def _function_tool(
    *, name: str, description: str, parameters: Mapping[str, Any]
) -> JsonDict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": dict(parameters),
        },
    }


OPENROUTER_TOOL_SCHEMAS: list[JsonDict] = [
    _function_tool(
        name=TOOL_LIST_BINDINGS,
        description=(
            "List SkeinRank runtime binding contexts available to the alias "
            "scout. Use this before validating or submitting binding-scoped "
            "alias proposals."
        ),
        parameters=_object_schema(
            properties={
                "profile_name": {
                    "type": "string",
                    "description": "Optional profile name filter.",
                },
                "enabled_only": {
                    "type": "boolean",
                    "description": "Return only enabled bindings.",
                    "default": True,
                },
            }
        ),
    ),
    _function_tool(
        name=TOOL_EXPLAIN_QUERY,
        description=(
            "Explain how SkeinRank canonicalizes a query for a binding or "
            "profile. This is read-only and useful before proposing aliases."
        ),
        parameters=_object_schema(
            properties={
                "profile_name": {
                    "type": "string",
                    "description": "Profile name for preview/dev mode.",
                },
                "binding_id": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Runtime binding context for production mode.",
                },
                "query": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Raw user query or failed search query.",
                },
                "size": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 10,
                },
                "include_evidence": {
                    "type": "boolean",
                    "default": True,
                },
            },
            required=("query",),
        ),
    ),
    _function_tool(
        name=TOOL_VALIDATE_ALIAS,
        description=(
            "Validate an alias proposal without saving it. Prefer this before "
            "submitting a proposal when the candidate may be noisy or ambiguous."
        ),
        parameters=_object_schema(
            properties={
                "profile_name": {"type": "string"},
                "binding_id": {"type": "integer", "minimum": 1},
                "canonical_value": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Canonical term, for example 'postgresql'.",
                },
                "alias_value": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Observed surface form, for example 'pg'.",
                },
                "slot": {
                    "type": "string",
                    "minLength": 1,
                    "description": "SkeinRank slot for the canonical term.",
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "default": 1.0,
                },
                "proposal_source_name": {"type": "string"},
                "idempotency_key": {"type": "string"},
                "source_payload": {
                    "type": "object",
                    "description": "Compact evidence/statistics payload from the agent.",
                },
            },
            required=("canonical_value", "alias_value", "slot"),
            additional_properties=False,
        ),
    ),
    _function_tool(
        name=TOOL_SUBMIT_ALIAS_PROPOSAL,
        description=(
            "Submit an alias proposal for review. This creates a pending "
            "proposal only; it does not publish a snapshot or mutate runtime "
            "terminology directly."
        ),
        parameters=_object_schema(
            properties={
                "profile_name": {"type": "string"},
                "binding_id": {"type": "integer", "minimum": 1},
                "canonical_value": {
                    "type": "string",
                    "minLength": 1,
                },
                "alias_value": {
                    "type": "string",
                    "minLength": 1,
                },
                "slot": {"type": "string", "minLength": 1},
                "confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "default": 1.0,
                },
                "context": {
                    "type": "string",
                    "description": "Short human-readable reason/evidence summary.",
                },
                "proposal_source_name": {"type": "string"},
                "idempotency_key": {"type": "string"},
                "source_payload": {
                    "type": "object",
                    "description": "Compact evidence/statistics payload from the agent.",
                },
            },
            required=("canonical_value", "alias_value", "slot"),
            additional_properties=False,
        ),
    ),
]


def get_openrouter_tool_schemas() -> list[JsonDict]:
    """Return a defensive copy of OpenRouter-compatible tool schemas."""

    return json.loads(json.dumps(OPENROUTER_TOOL_SCHEMAS))


def get_tool_schema(name: str) -> JsonDict:
    """Return one tool schema by function name."""

    for schema in get_openrouter_tool_schemas():
        if schema["function"]["name"] == name:
            return schema
    raise KeyError(f"Unknown OpenRouter tool schema: {name}")


def get_tool_names() -> tuple[str, ...]:
    """Return tool names in the order the alias scout should expose them."""

    return _TOOL_ORDER


def parse_tool_call_arguments(arguments: str | Mapping[str, Any] | None) -> JsonDict:
    """Parse OpenRouter/OpenAI tool-call arguments into a JSON object.

    Providers typically return function arguments as a JSON string, while tests and
    local runners often pass a mapping directly. This helper deliberately accepts
    only JSON objects so downstream client calls do not receive a scalar/list by
    accident.
    """

    if arguments is None:
        return {}
    if isinstance(arguments, Mapping):
        return dict(arguments)
    if not isinstance(arguments, str):
        raise TypeError("Tool-call arguments must be a JSON string or mapping.")
    stripped = arguments.strip()
    if not stripped:
        return {}
    parsed = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise ValueError("Tool-call arguments must decode to a JSON object.")
    return parsed
