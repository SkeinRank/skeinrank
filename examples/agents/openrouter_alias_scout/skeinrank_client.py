"""Small stdlib client for SkeinRank agent REST tools.

This module is intentionally dependency-light so the reference agent can run
from the repository without introducing an agent framework yet. LangGraph,
CrewAI, or OpenRouter tool-calling can wrap this client in later patches.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

JsonDict = dict[str, Any]
Transport = Callable[[str, str, Mapping[str, Any] | None], Any]


class SkeinRankAgentClientError(RuntimeError):
    """Base error raised by the reference SkeinRank agent client."""


class SkeinRankAgentApiError(SkeinRankAgentClientError):
    """Raised when the Governance API returns a non-2xx response."""

    def __init__(self, status_code: int, detail: Any) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"SkeinRank API returned {status_code}: {detail}")


@dataclass(frozen=True)
class SkeinRankAgentClient:
    """Thin client around the agent-friendly SkeinRank REST tools."""

    base_url: str = "http://127.0.0.1:8010"
    role: str = "contributor"
    api_token: str | None = None
    timeout_seconds: float = 10.0
    transport: Transport | None = None

    def request(
        self, method: str, path: str, payload: Mapping[str, Any] | None = None
    ) -> Any:
        """Execute a REST request and return decoded JSON when present."""

        if self.transport is not None:
            return self.transport(method.upper(), path, payload)

        url = f"{self.base_url.rstrip('/')}{path}"
        headers = {
            "Accept": "application/json",
            "X-SkeinRank-Role": self.role,
        }
        data: bytes | None = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"

        request = Request(url, data=data, headers=headers, method=method.upper())
        try:
            # The URL is operator-configured for this local example client.
            with urlopen(  # noqa: S310
                request, timeout=self.timeout_seconds
            ) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else None
        except HTTPError as exc:
            body = exc.read().decode("utf-8")
            try:
                detail: Any = json.loads(body)
            except json.JSONDecodeError:
                detail = body or exc.reason
            raise SkeinRankAgentApiError(exc.code, detail) from exc
        except URLError as exc:
            raise SkeinRankAgentClientError(
                f"Could not reach SkeinRank Governance API: {exc}"
            ) from exc

    def list_bindings(
        self, *, profile_name: str | None = None, enabled_only: bool = True
    ) -> Any:
        """List binding contexts available to agent workflows."""

        query: dict[str, str] = {"enabled_only": str(enabled_only).lower()}
        if profile_name:
            query["profile_name"] = profile_name
        return self.request("GET", f"/v1/tools/bindings?{urlencode(query)}")

    def explain_query(
        self,
        *,
        query: str,
        binding_id: int | None = None,
        profile_name: str | None = None,
        include_evidence: bool = True,
        size: int = 10,
    ) -> Any:
        """Ask SkeinRank to explain query canonicalization for a binding/profile."""

        payload: JsonDict = {
            "query": query,
            "include_evidence": include_evidence,
            "size": size,
        }
        if binding_id is not None:
            payload["binding_id"] = binding_id
        if profile_name is not None:
            payload["profile_name"] = profile_name
        return self.request("POST", "/v1/tools/explain-query", payload)

    def validate_alias(
        self,
        *,
        canonical_value: str,
        alias_value: str,
        slot: str,
        binding_id: int | None = None,
        profile_name: str | None = None,
        confidence: float = 1.0,
        proposal_source_name: str | None = None,
        idempotency_key: str | None = None,
        source_payload: Mapping[str, Any] | None = None,
    ) -> Any:
        """Validate an alias proposal without saving it."""

        payload = self._alias_payload(
            canonical_value=canonical_value,
            alias_value=alias_value,
            slot=slot,
            binding_id=binding_id,
            profile_name=profile_name,
            confidence=confidence,
            proposal_source_name=proposal_source_name,
            idempotency_key=idempotency_key,
            source_payload=source_payload,
        )
        return self.request("POST", "/v1/tools/validate-alias", payload)

    def suggest_alias(
        self,
        *,
        canonical_value: str,
        alias_value: str,
        slot: str,
        binding_id: int | None = None,
        profile_name: str | None = None,
        confidence: float = 1.0,
        context: str | None = None,
        proposal_source_name: str | None = None,
        idempotency_key: str | None = None,
        source_payload: Mapping[str, Any] | None = None,
    ) -> Any:
        """Submit an alias proposal for review without mutating runtime directly."""

        payload = self._alias_payload(
            canonical_value=canonical_value,
            alias_value=alias_value,
            slot=slot,
            binding_id=binding_id,
            profile_name=profile_name,
            confidence=confidence,
            proposal_source_name=proposal_source_name,
            idempotency_key=idempotency_key,
            source_payload=source_payload,
        )
        if context:
            payload["context"] = context
        return self.request("POST", "/v1/tools/suggest-alias", payload)

    @staticmethod
    def _alias_payload(
        *,
        canonical_value: str,
        alias_value: str,
        slot: str,
        binding_id: int | None,
        profile_name: str | None,
        confidence: float,
        proposal_source_name: str | None,
        idempotency_key: str | None,
        source_payload: Mapping[str, Any] | None,
    ) -> JsonDict:
        payload: JsonDict = {
            "canonical_value": canonical_value,
            "alias_value": alias_value,
            "slot": slot,
            "confidence": confidence,
            "proposal_source_type": "agent",
        }
        if binding_id is not None:
            payload["binding_id"] = binding_id
        if profile_name is not None:
            payload["profile_name"] = profile_name
        if proposal_source_name is not None:
            payload["proposal_source_name"] = proposal_source_name
        if idempotency_key is not None:
            payload["idempotency_key"] = idempotency_key
        if source_payload is not None:
            payload["source_payload"] = dict(source_payload)
        return payload
