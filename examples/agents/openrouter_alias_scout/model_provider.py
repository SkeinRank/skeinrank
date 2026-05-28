"""Model-provider abstraction for the alias scout example.

Patch 57A introduces a provider-facing seam without changing the existing
OpenRouter runtime behavior. The abstraction is intentionally small: providers
only need to implement the OpenAI-compatible ``create_chat_completion`` method
that the current alias scout workflow already uses. This keeps OpenRouter as the
first production adapter while allowing tests and future patches to use mock,
OpenAI-compatible, or local endpoint adapters without rewriting the workflow.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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
    require_api_key: bool | None = None

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
        provider_type_env = os.getenv("SKEINRANK_MODEL_PROVIDER_TYPE")
        provider_type = str(
            provider_type_env
            or data.get("provider_type", data.get("type", "openrouter"))
        )
        normalized_provider_type = provider_type.lower().strip().replace("-", "_")
        if provider_type_env and normalized_provider_type in {
            "local",
            "local_endpoint",
        }:
            provider_name = "local-endpoint"
        else:
            provider_name = str(
                data.get("provider_name", data.get("name", provider_type))
            )
        if normalized_provider_type == "local":
            normalized_provider_type = "local_endpoint"
        local_default_base_url = "http://127.0.0.1:8000/v1"
        local_default_model = "local-model"
        local_default_api_key_env = "SKEINRANK_LOCAL_MODEL_API_KEY"
        base_url_default = (
            local_default_base_url
            if normalized_provider_type == "local_endpoint"
            else default_base_url
        )
        model_default = (
            local_default_model
            if normalized_provider_type == "local_endpoint"
            else default_model
        )
        api_key_env_default = (
            local_default_api_key_env
            if normalized_provider_type == "local_endpoint"
            else default_api_key_env
        )
        require_api_key_raw = None if provider_type_env else data.get("require_api_key")
        require_api_key: bool | None
        if require_api_key_raw is None:
            require_api_key = None
        else:
            require_api_key = bool(require_api_key_raw)
        if normalized_provider_type == "local_endpoint":
            model_value = (
                os.getenv("SKEINRANK_MODEL_PROVIDER_MODEL")
                or os.getenv("SKEINRANK_LOCAL_MODEL")
                or data.get("model", model_default)
            )
            base_url_value = (
                os.getenv("SKEINRANK_MODEL_PROVIDER_BASE_URL")
                or os.getenv("SKEINRANK_LOCAL_MODEL_BASE_URL")
                or data.get("base_url", base_url_default)
            )
        else:
            model_value = os.getenv("SKEINRANK_MODEL_PROVIDER_MODEL") or data.get(
                "model", model_default
            )
            base_url_value = os.getenv("SKEINRANK_MODEL_PROVIDER_BASE_URL") or data.get(
                "base_url", base_url_default
            )
        return cls(
            provider_type=normalized_provider_type,
            provider_name=provider_name,
            model=str(model_value),
            api_key_env=str(
                api_key_env_default
                if provider_type_env
                else data.get("api_key_env", api_key_env_default)
            ),
            base_url=str(base_url_value),
            app_title=str(data.get("app_title", default_app_title)),
            http_referer=data.get("http_referer", default_http_referer),
            timeout_seconds=float(data.get("timeout_seconds", cls.timeout_seconds)),
            require_api_key=require_api_key,
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
            "requires_api_key": self.requires_api_key,
        }

    @property
    def requires_api_key(self) -> bool:
        """Return whether this provider needs an API key before live calls."""

        if self.require_api_key is not None:
            return self.require_api_key
        return self.provider_type.lower().strip() != "local_endpoint"


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


@dataclass(frozen=True)
class LocalEndpointChatProvider:
    """Local OpenAI-compatible `/chat/completions` endpoint adapter.

    This adapter is intentionally named `local_endpoint` in operator-facing
    config because the practical use case is a self-hosted vLLM/LM Studio/Ollama
    compatible gateway. It does not require an API key by default, but it can
    pass a Bearer token when `api_key_env` is configured.
    """

    base_url: str = "http://127.0.0.1:8000/v1"
    model: str = "local-model"
    provider_name: str = "local-endpoint"
    provider_type: str = "local_endpoint"
    api_key: str | None = None
    timeout_seconds: float = 30.0
    transport: Callable[[str, str, Mapping[str, Any] | None], Any] | None = None

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
        """Create one local endpoint chat completion and return decoded JSON."""

        payload: JsonDict = {
            "model": model or self.model,
            "messages": [dict(message) for message in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = [dict(tool) for tool in tools]
            payload["tool_choice"] = "auto"
        if response_format:
            payload["response_format"] = dict(response_format)
        return self._request("POST", "/chat/completions", payload)

    def _request(
        self, method: str, path: str, payload: Mapping[str, Any] | None = None
    ) -> JsonDict:
        if self.transport is not None:
            result = self.transport(method.upper(), path, payload)
            if not isinstance(result, Mapping):
                raise ModelProviderError(
                    "Local endpoint transport must return a mapping."
                )
            return dict(result)

        url = f"{self.base_url.rstrip('/')}{path}"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Title": self.provider_name,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        data = json.dumps(dict(payload or {})).encode("utf-8")
        request = Request(url, data=data, headers=headers, method=method.upper())
        try:
            with urlopen(  # noqa: S310
                request, timeout=self.timeout_seconds
            ) as response:
                body = response.read().decode("utf-8")
                if not body.strip():
                    return {}
                parsed = json.loads(body)
                if not isinstance(parsed, dict):
                    raise ModelProviderError(
                        "Local endpoint response must be a JSON object."
                    )
                return parsed
        except HTTPError as exc:
            body = exc.read().decode("utf-8")
            try:
                detail: Any = json.loads(body)
            except json.JSONDecodeError:
                detail = body or exc.reason
            raise ModelProviderError(
                f"Local endpoint returned {exc.code}: {detail}"
            ) from exc
        except URLError as exc:
            raise ModelProviderError(
                f"Could not reach local model endpoint: {exc}"
            ) from exc


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
            "cost_estimation_from_usage": config.provider_type != "local_endpoint",
            "local_endpoint_supported": True,
        },
        "supported_provider_types": ["openrouter", "local_endpoint", "mock"],
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

    provider_type = config.provider_type.lower().strip().replace("-", "_")
    if provider_type == "local":
        provider_type = "local_endpoint"
    if provider_type == "mock":
        return MockChatProvider(model=config.model, provider_name=config.provider_name)
    if provider_type == "local_endpoint":
        api_key = os.getenv(config.api_key_env) if config.api_key_env else None
        if config.requires_api_key and not api_key:
            raise ModelProviderError(
                f"Local model endpoint API key is required. Set {config.api_key_env} "
                "or set require_api_key=false for unauthenticated local endpoints."
            )
        return LocalEndpointChatProvider(
            base_url=config.base_url,
            model=config.model,
            provider_name=config.provider_name or "local-endpoint",
            provider_type="local_endpoint",
            api_key=api_key,
            timeout_seconds=config.timeout_seconds,
        )
    if provider_type != "openrouter":
        raise ModelProviderError(
            f"Unsupported model provider type: {config.provider_type}. "
            "Supported provider types are: openrouter, local_endpoint, mock."
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
        provider_type="openrouter",
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
