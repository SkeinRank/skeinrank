"""Model-provider abstraction for the alias scout example.

Patch 57A introduces a provider-facing seam without changing the existing
OpenRouter runtime behavior. The abstraction is intentionally small: providers
only need to implement the OpenAI-compatible ``create_chat_completion`` method
that the current alias scout workflow already uses. This keeps OpenRouter as the
first production adapter while allowing tests and future patches to use mock,
OpenAI-compatible, or local endpoint adapters without rewriting the workflow.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

try:  # pragma: no cover - import style depends on how the example is executed.
    from .openrouter_client import OpenRouterClient
except ImportError:  # pragma: no cover
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from openrouter_client import OpenRouterClient

JsonDict = dict[str, Any]
MockResponseFactory = Callable[[Mapping[str, Any]], Mapping[str, Any]]

MODEL_PROVIDER_PLAN_VERSION = "skeinrank.model_provider_plan.v1"


class ModelProviderError(RuntimeError):
    """Raised when a model-provider configuration or call is invalid."""


@runtime_checkable
class ChatCompletionProvider(Protocol):
    """Minimal provider interface used by the alias scout workflow."""

    provider_name: str
    provider_type: str
    model: str

    def create_chat_completion(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, Any]],
        temperature: float = 0.0,
        max_tokens: int = 700,
        tools: Sequence[Mapping[str, Any]] | None = None,
        response_format: Mapping[str, Any] | None = None,
    ) -> JsonDict:
        """Create one chat completion and return OpenAI-compatible JSON."""


@dataclass(frozen=True)
class ModelProviderConfig:
    """Runtime config for a chat-completion provider."""

    provider_type: str = "openrouter"
    provider_name: str = "openrouter"
    model: str = "openai/gpt-4o-mini"
    api_key_env: str = "OPENROUTER_API_KEY"
    base_url: str = "https://openrouter.ai/api/v1"
    app_title: str = "SkeinRank OpenRouter Alias Scout"
    http_referer: str | None = None
    timeout_seconds: float = 30.0

    @classmethod
    def from_mapping(
        cls,
        raw: Mapping[str, Any] | None,
        *,
        default_model: str = "openai/gpt-4o-mini",
        default_api_key_env: str = "OPENROUTER_API_KEY",
        default_base_url: str = "https://openrouter.ai/api/v1",
        default_app_title: str = "SkeinRank OpenRouter Alias Scout",
        default_http_referer: str | None = None,
    ) -> "ModelProviderConfig":
        """Create provider config from optional JSON config values."""

        data = dict(raw or {})
        provider_type = str(data.get("provider_type", data.get("type", "openrouter")))
        provider_name = str(data.get("provider_name", data.get("name", provider_type)))
        return cls(
            provider_type=provider_type,
            provider_name=provider_name,
            model=str(
                os.getenv("SKEINRANK_MODEL_PROVIDER_MODEL")
                or data.get("model", default_model)
            ),
            api_key_env=str(data.get("api_key_env", default_api_key_env)),
            base_url=str(
                os.getenv("SKEINRANK_MODEL_PROVIDER_BASE_URL")
                or data.get("base_url", default_base_url)
            ),
            app_title=str(data.get("app_title", default_app_title)),
            http_referer=data.get("http_referer", default_http_referer),
            timeout_seconds=float(data.get("timeout_seconds", cls.timeout_seconds)),
        )

    def to_dict(self, *, include_secret_values: bool = False) -> JsonDict:
        """Return a redaction-safe provider config summary."""

        return {
            "schema_version": MODEL_PROVIDER_PLAN_VERSION,
            "provider_type": self.provider_type,
            "provider_name": self.provider_name,
            "model": self.model,
            "api_key_env": self.api_key_env,
            "api_key_configured": bool(os.getenv(self.api_key_env)),
            "api_key_value": os.getenv(self.api_key_env)
            if include_secret_values
            else None,
            "base_url": self.base_url,
            "app_title": self.app_title,
            "http_referer_configured": bool(self.http_referer),
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True)
class OpenRouterChatProvider:
    """OpenRouter/OpenAI-compatible provider adapter."""

    client: OpenRouterClient
    model: str = "openai/gpt-4o-mini"
    provider_name: str = "openrouter"
    provider_type: str = "openrouter"

    def create_chat_completion(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, Any]],
        temperature: float = 0.0,
        max_tokens: int = 700,
        tools: Sequence[Mapping[str, Any]] | None = None,
        response_format: Mapping[str, Any] | None = None,
    ) -> JsonDict:
        """Delegate to the existing dependency-light OpenRouter client."""

        return self.client.create_chat_completion(
            model=model or self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            response_format=response_format,
        )


@dataclass
class MockChatProvider:
    """Deterministic provider used by tests and offline demos."""

    responses: Sequence[Mapping[str, Any]] | None = None
    response_factory: MockResponseFactory | None = None
    model: str = "mock/test-model"
    provider_name: str = "mock"
    provider_type: str = "mock"

    def __post_init__(self) -> None:
        self.calls: list[JsonDict] = []
        self._index = 0

    def create_chat_completion(
        self,
        *,
        model: str,
        messages: Sequence[Mapping[str, Any]],
        temperature: float = 0.0,
        max_tokens: int = 700,
        tools: Sequence[Mapping[str, Any]] | None = None,
        response_format: Mapping[str, Any] | None = None,
    ) -> JsonDict:
        """Return a deterministic OpenAI-compatible response."""

        payload: JsonDict = {
            "model": model or self.model,
            "messages": [dict(message) for message in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "tools": [dict(tool) for tool in tools] if tools else None,
            "response_format": dict(response_format) if response_format else None,
        }
        self.calls.append(payload)
        if self.response_factory is not None:
            response = self.response_factory(payload)
        elif self.responses:
            response = self.responses[min(self._index, len(self.responses) - 1)]
            self._index += 1
        else:
            response = {
                "id": "mock-chatcmpl-1",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": (
                                '{"action":"reject","confidence":0.1,'
                                '"reason":"mock provider default response",'
                                '"risk_flags":["mock"]}'
                            ),
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "cost": 0.0,
                },
            }
        if not isinstance(response, Mapping):
            raise ModelProviderError("Mock provider response must be a mapping.")
        return dict(response)


def build_model_provider_plan(config: ModelProviderConfig) -> JsonDict:
    """Return an offline provider plan without network calls."""

    return {
        "schema_version": MODEL_PROVIDER_PLAN_VERSION,
        "status": "planned",
        "provider": config.to_dict(),
        "capabilities": {
            "chat_completions": True,
            "json_response_format": True,
            "tool_schemas_passthrough": True,
            "cost_estimation_from_usage": True,
        },
        "safety": {
            "network_calls": False,
            "requires_explicit_live_run": True,
            "secrets_included": False,
            "runtime_mutation_enabled": False,
        },
    }


def create_model_provider(config: ModelProviderConfig) -> ChatCompletionProvider:
    """Create a provider instance from config.

    Patch 57A intentionally ships only the OpenRouter production adapter and a
    deterministic mock provider. OpenAI-compatible and local endpoint adapters
    can plug into the same interface in later patches.
    """

    provider_type = config.provider_type.lower().strip()
    if provider_type == "mock":
        return MockChatProvider(model=config.model, provider_name=config.provider_name)
    if provider_type not in {"openrouter", "openai-compatible"}:
        raise ModelProviderError(
            f"Unsupported model provider type: {config.provider_type}"
        )
    api_key = os.getenv(config.api_key_env)
    if not api_key:
        raise ModelProviderError(
            f"OpenRouter API key is required. Set {config.api_key_env} "
            "or use --print-model-provider-plan / offline preview commands."
        )
    client = OpenRouterClient(
        api_key=api_key,
        base_url=config.base_url,
        app_title=config.app_title,
        http_referer=config.http_referer,
        timeout_seconds=config.timeout_seconds,
    )
    return OpenRouterChatProvider(
        client=client,
        model=config.model,
        provider_name=config.provider_name,
        provider_type=config.provider_type,
    )


def provider_metadata(provider: ChatCompletionProvider | Any) -> JsonDict:
    """Return redaction-safe metadata for a provider-like object."""

    return {
        "schema_version": "skeinrank.model_provider_metadata.v1",
        "provider_name": str(getattr(provider, "provider_name", "openrouter")),
        "provider_type": str(getattr(provider, "provider_type", "openrouter")),
        "model": str(getattr(provider, "model", "unknown")),
        "chat_completion_interface": hasattr(provider, "create_chat_completion"),
    }
