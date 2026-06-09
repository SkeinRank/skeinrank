from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from skeinrank.adapters.builtin_lexical import BuiltinLexicalScorer
from skeinrank.app.profiles import ProfileSpec
from skeinrank.domain.errors import ModelUnavailable


@dataclass(frozen=True)
class BackendDiagnosis:
    """Structured backend availability and diagnostic details."""

    backend_id: str
    available: bool
    details: dict[str, Any]
    errors: list[str]


@runtime_checkable
class Backend(Protocol):
    id: str

    def is_available(self, *, device: str | None = None) -> bool: ...

    def diagnose(self, *, device: str | None = None) -> BackendDiagnosis: ...

    def create_scorer(self, *, profile: ProfileSpec, resolved_device: str) -> Any: ...


class BuiltinBackend:
    id = "builtin"

    def is_available(self, *, device: str | None = None) -> bool:  # noqa: ARG002
        return True

    def diagnose(self, *, device: str | None = None) -> BackendDiagnosis:  # noqa: ARG002
        return BackendDiagnosis(
            backend_id=self.id,
            available=True,
            details={"always_available": True, "dependencies": []},
            errors=[],
        )

    def create_scorer(self, *, profile: ProfileSpec, resolved_device: str) -> Any:  # noqa: ARG002
        return BuiltinLexicalScorer()


_REGISTRY: dict[str, Backend] = {
    BuiltinBackend.id: BuiltinBackend(),
}


def get_backend(backend_id: str) -> Backend:
    if backend_id not in _REGISTRY:
        raise ModelUnavailable(f"Unknown backend: {backend_id}")
    return _REGISTRY[backend_id]


def list_backends() -> list[str]:
    return sorted(_REGISTRY.keys())


def diagnose_backends(*, device: str | None = None) -> dict[str, BackendDiagnosis]:
    out: dict[str, BackendDiagnosis] = {}
    for bid, backend in _REGISTRY.items():
        try:
            out[bid] = backend.diagnose(device=device)
        except Exception as e:  # pragma: no cover
            out[bid] = BackendDiagnosis(
                backend_id=bid,
                available=False,
                details={},
                errors=[f"diagnose failed: {e}"],
            )
    return out
