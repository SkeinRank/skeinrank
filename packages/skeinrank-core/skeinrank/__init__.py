"""SkeinRank public API.

Only symbols exported from this module are considered **stable public API**.
Internal modules may change without notice.
"""

from .app.engine import RerankEngine, rerank, rerank_many, score
from .app.profiles import get_profile, list_profiles, validate_profile
from .attributes import (
    AttributeEvidence,
    AttributeModelAdapters,
    AttributePack,
    AttributePassport,
    AttributeProfile,
    AttributeSlot,
    AttributeSnapshot,
    AttributeStageStatus,
    AttributeTrace,
    ExtractedAttribute,
    FailingAdapter,
    ModelCandidate,
    StaticE5Adapter,
    StaticGLiNERAdapter,
    StaticKeyBERTAdapter,
    build_attribute_profile,
    enrich_documents,
    enrich_jsonl,
    evaluate_demo_queries,
    extract_attributes,
    get_attribute_profile,
    list_attribute_profiles,
    load_attribute_profile,
    load_jsonl,
    write_jsonl,
)
from .domain.errors import ContractError, ModelUnavailable, SkeinRankError
from .domain.types import (
    Candidate,
    RankedItem,
    RequestPassport,
    RerankRequest,
    RerankResult,
    ScoreResult,
)

__all__ = [
    "RerankEngine",
    "rerank",
    "rerank_many",
    "score",
    "list_profiles",
    "get_profile",
    "validate_profile",
    "Candidate",
    "RerankRequest",
    "RankedItem",
    "RerankResult",
    "ScoreResult",
    "RequestPassport",
    "extract_attributes",
    "get_attribute_profile",
    "list_attribute_profiles",
    "build_attribute_profile",
    "load_attribute_profile",
    "load_jsonl",
    "write_jsonl",
    "enrich_documents",
    "enrich_jsonl",
    "evaluate_demo_queries",
    "AttributeModelAdapters",
    "ModelCandidate",
    "StaticGLiNERAdapter",
    "StaticE5Adapter",
    "StaticKeyBERTAdapter",
    "FailingAdapter",
    "AttributeSlot",
    "AttributeEvidence",
    "ExtractedAttribute",
    "AttributeTrace",
    "AttributeProfile",
    "AttributeSnapshot",
    "AttributeStageStatus",
    "AttributePassport",
    "AttributePack",
    "SkeinRankError",
    "ContractError",
    "ModelUnavailable",
]

__version__ = "0.0.11"
