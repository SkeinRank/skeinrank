"""Dependency-light OpenRouter chat-completions client for alias scout runs.

Patch 40J adds the first real model execution path, but keeps it small and
safe: the client only calls OpenRouter/OpenAI-compatible chat completions and
returns decoded JSON. It does not execute SkeinRank tools and it does not submit
proposals by itself.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

JsonDict = dict[str, Any]
OpenRouterTransport = Callable[[str, str, Mapping[str, Any] | None], Any]


class OpenRouterClientError(RuntimeError):
    """Base error raised by the dependency-light OpenRouter client."""


class OpenRouterApiError(OpenRouterClientError):
    """Raised when OpenRouter returns a non-2xx response."""

    def __init__(self, status_code: int, detail: Any) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"OpenRouter API returned {status_code}: {detail}")


@dataclass(frozen=True)
class OpenRouterClient:
    """Small stdlib client for OpenRouter chat completions.

    The request shape intentionally follows the OpenAI-compatible `/chat/completions`
    API because OpenRouter documents that path as the low-dependency integration
    option. Tests pass a fake transport, so no real API key/network call is needed
    in CI.
    """

    api_key: str
    base_url: str = "https://openrouter.ai/api/v1"
    app_title: str = "SkeinRank OpenRouter Alias Scout"
    http_referer: str | None = None
    timeout_seconds: float = 30.0
    transport: OpenRouterTransport | None = None

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
        """Create one OpenRouter chat completion and return decoded JSON."""

        payload: JsonDict = {
            "model": model,
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
                raise OpenRouterClientError(
                    "OpenRouter transport must return a mapping."
                )
            return dict(result)

        url = f"{self.base_url.rstrip('/')}{path}"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Title": self.app_title,
        }
        if self.http_referer:
            headers["HTTP-Referer"] = self.http_referer

        data = json.dumps(dict(payload or {})).encode("utf-8")
        request = Request(url, data=data, headers=headers, method=method.upper())
        try:
            # The URL is operator-configured and defaults to OpenRouter.
            with urlopen(  # noqa: S310
                request, timeout=self.timeout_seconds
            ) as response:
                body = response.read().decode("utf-8")
                if not body.strip():
                    return {}
                parsed = json.loads(body)
                if not isinstance(parsed, dict):
                    raise OpenRouterClientError(
                        "OpenRouter response must be a JSON object."
                    )
                return parsed
        except HTTPError as exc:
            body = exc.read().decode("utf-8")
            try:
                detail: Any = json.loads(body)
            except json.JSONDecodeError:
                detail = body or exc.reason
            raise OpenRouterApiError(exc.code, detail) from exc
        except URLError as exc:
            raise OpenRouterClientError(
                f"Could not reach OpenRouter API: {exc}"
            ) from exc


def extract_first_message_content(response: Mapping[str, Any]) -> str:
    """Extract assistant message content from an OpenAI-compatible response."""

    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise OpenRouterClientError("OpenRouter response does not contain choices.")
    first = choices[0]
    if not isinstance(first, Mapping):
        raise OpenRouterClientError("OpenRouter choice must be an object.")
    message = first.get("message")
    if not isinstance(message, Mapping):
        raise OpenRouterClientError("OpenRouter choice does not contain a message.")
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content
    raise OpenRouterClientError("OpenRouter response message content is empty.")
