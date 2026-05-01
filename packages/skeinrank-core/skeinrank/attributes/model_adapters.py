from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .normalize import normalize_value
from .types import AttributeProfile, AttributeSlot


@dataclass(frozen=True)
class ModelCandidate:
    slot: AttributeSlot
    value: str
    source: str
    matched_text: str
    confidence: float = 0.8
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def normalized_value(self) -> str:
        return normalize_value(self.value)


class GLiNERLikeAdapter(Protocol):
    def extract(
        self, text: str, *, profile: AttributeProfile
    ) -> list[ModelCandidate]: ...


class E5LikeAdapter(Protocol):
    def extract(
        self, text: str, *, profile: AttributeProfile
    ) -> list[ModelCandidate]: ...


class KeyBERTLikeAdapter(Protocol):
    def extract(
        self, text: str, *, profile: AttributeProfile
    ) -> list[ModelCandidate]: ...


@dataclass
class AttributeModelAdapters:
    gliner: GLiNERLikeAdapter | None = None
    e5: E5LikeAdapter | None = None
    keybert: KeyBERTLikeAdapter | None = None


class StaticGLiNERAdapter:
    def __init__(self, candidates: list[ModelCandidate]):
        self._candidates = list(candidates)

    def extract(self, text: str, *, profile: AttributeProfile) -> list[ModelCandidate]:
        return list(self._candidates)


class StaticE5Adapter:
    def __init__(self, candidates: list[ModelCandidate]):
        self._candidates = list(candidates)

    def extract(self, text: str, *, profile: AttributeProfile) -> list[ModelCandidate]:
        return list(self._candidates)


class StaticKeyBERTAdapter:
    def __init__(self, candidates: list[ModelCandidate]):
        self._candidates = list(candidates)

    def extract(self, text: str, *, profile: AttributeProfile) -> list[ModelCandidate]:
        return list(self._candidates)


class FailingAdapter:
    def __init__(self, message: str = "adapter_failure"):
        self._message = message

    def extract(self, text: str, *, profile: AttributeProfile) -> list[ModelCandidate]:
        raise RuntimeError(self._message)
