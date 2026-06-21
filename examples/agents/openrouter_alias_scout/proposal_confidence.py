"""Confidence and abstention helpers for alias-scout judgments.

The helpers keep model review conservative. They aggregate one or more strict
LLM judgments and allow proposal preparation only when the model converges on a
compatible high-confidence decision. Low agreement is converted into
``needs_evidence`` instead of a risky proposal.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

try:  # pragma: no cover - import style depends on how the example is executed.
    from .structured_output import AliasReviewJudgment
except ImportError:  # pragma: no cover
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from structured_output import AliasReviewJudgment

JsonDict = dict[str, Any]


@dataclass(frozen=True)
class ProposalConfidenceConfig:
    """Consensus and abstention settings for model-reviewed proposals."""

    judgment_samples_per_candidate: int = 1
    min_consensus_to_prepare_proposal: float = 1.0
    abstain_on_disagreement: bool = True
    require_consistent_proposal_payload: bool = True

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> "ProposalConfidenceConfig":
        """Create config from optional JSON config values."""

        if not raw:
            return cls()
        samples = int(
            raw.get(
                "judgment_samples_per_candidate", cls.judgment_samples_per_candidate
            )
        )
        return cls(
            judgment_samples_per_candidate=max(1, samples),
            min_consensus_to_prepare_proposal=float(
                raw.get(
                    "min_consensus_to_prepare_proposal",
                    cls.min_consensus_to_prepare_proposal,
                )
            ),
            abstain_on_disagreement=bool(
                raw.get("abstain_on_disagreement", cls.abstain_on_disagreement)
            ),
            require_consistent_proposal_payload=bool(
                raw.get(
                    "require_consistent_proposal_payload",
                    cls.require_consistent_proposal_payload,
                )
            ),
        )

    def to_report(self) -> JsonDict:
        """Return a redaction-safe config summary."""

        return {
            "schema_version": "skeinrank.proposal_confidence_config.v1",
            "judgment_samples_per_candidate": self.judgment_samples_per_candidate,
            "min_consensus_to_prepare_proposal": (
                self.min_consensus_to_prepare_proposal
            ),
            "abstain_on_disagreement": self.abstain_on_disagreement,
            "require_consistent_proposal_payload": (
                self.require_consistent_proposal_payload
            ),
        }


@dataclass(frozen=True)
class ProposalConfidenceDecision:
    """Aggregated proposal confidence decision for one reviewed candidate."""

    action: str
    consensus_score: float
    mean_confidence: float
    max_confidence: float
    samples: int
    proposed_payload_consensus: float = 0.0
    selected_sample_index: int | None = None
    abstained: bool = False
    abstention_reason: str | None = None
    risk_flags: tuple[str, ...] = field(default_factory=tuple)
    action_counts: Mapping[str, int] = field(default_factory=dict)

    def to_dict(self) -> JsonDict:
        """Return a stable JSON-serializable decision payload."""

        payload: JsonDict = {
            "schema_version": "skeinrank.proposal_confidence_decision.v1",
            "action": self.action,
            "consensus_score": self.consensus_score,
            "mean_confidence": self.mean_confidence,
            "max_confidence": self.max_confidence,
            "samples": self.samples,
            "proposed_payload_consensus": self.proposed_payload_consensus,
            "selected_sample_index": self.selected_sample_index,
            "abstained": self.abstained,
            "risk_flags": list(self.risk_flags),
            "action_counts": dict(self.action_counts),
        }
        if self.abstention_reason:
            payload["abstention_reason"] = self.abstention_reason
        return payload


def aggregate_judgment_confidence(
    judgments: Sequence[AliasReviewJudgment],
    *,
    config: ProposalConfidenceConfig | None = None,
) -> ProposalConfidenceDecision:
    """Aggregate strict model judgments into a conservative decision."""

    cfg = config or ProposalConfidenceConfig()
    if not judgments:
        return ProposalConfidenceDecision(
            action="needs_evidence",
            consensus_score=0.0,
            mean_confidence=0.0,
            max_confidence=0.0,
            samples=0,
            abstained=True,
            abstention_reason="no_valid_judgments",
            risk_flags=("no_valid_judgments",),
            action_counts={},
        )

    samples = len(judgments)
    action_counts = Counter(judgment.action for judgment in judgments)
    top_action, top_count = action_counts.most_common(1)[0]
    consensus_score = round(top_count / samples, 4)
    confidence_values = [float(judgment.confidence) for judgment in judgments]
    mean_confidence = round(sum(confidence_values) / samples, 4)
    max_confidence = round(max(confidence_values), 4)
    selected_index = _selected_sample_index(judgments, top_action)
    payload_consensus = 0.0
    risk_flags: list[str] = []
    abstention_reason: str | None = None

    if consensus_score < cfg.min_consensus_to_prepare_proposal:
        risk_flags.append("low_action_consensus")
        abstention_reason = "low_action_consensus"
    if top_action == "propose":
        payload_consensus = _proposal_payload_consensus(judgments)
        if (
            cfg.require_consistent_proposal_payload
            and payload_consensus < cfg.min_consensus_to_prepare_proposal
        ):
            risk_flags.append("proposal_payload_disagreement")
            abstention_reason = abstention_reason or "proposal_payload_disagreement"

    if abstention_reason and cfg.abstain_on_disagreement:
        return ProposalConfidenceDecision(
            action="needs_evidence",
            consensus_score=consensus_score,
            mean_confidence=mean_confidence,
            max_confidence=max_confidence,
            samples=samples,
            proposed_payload_consensus=round(payload_consensus, 4),
            selected_sample_index=selected_index,
            abstained=True,
            abstention_reason=abstention_reason,
            risk_flags=tuple(risk_flags),
            action_counts=dict(action_counts),
        )

    return ProposalConfidenceDecision(
        action=top_action,
        consensus_score=consensus_score,
        mean_confidence=mean_confidence,
        max_confidence=max_confidence,
        samples=samples,
        proposed_payload_consensus=round(payload_consensus, 4),
        selected_sample_index=selected_index,
        abstained=False,
        risk_flags=tuple(risk_flags),
        action_counts=dict(action_counts),
    )


def _selected_sample_index(
    judgments: Sequence[AliasReviewJudgment], action: str
) -> int | None:
    best_index: int | None = None
    best_confidence = -1.0
    for index, judgment in enumerate(judgments):
        if judgment.action != action:
            continue
        if judgment.confidence > best_confidence:
            best_index = index
            best_confidence = judgment.confidence
    return best_index


def _proposal_payload_consensus(judgments: Sequence[AliasReviewJudgment]) -> float:
    keys = [
        (
            _norm(judgment.alias_value),
            _norm(judgment.canonical_value),
            _norm(judgment.slot),
        )
        for judgment in judgments
        if judgment.action == "propose"
    ]
    if not keys:
        return 0.0
    counts = Counter(keys)
    return round(counts.most_common(1)[0][1] / len(judgments), 4)


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()
