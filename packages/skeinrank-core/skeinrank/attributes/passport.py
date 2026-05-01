from __future__ import annotations

from .types import (
    AttributePassport,
    AttributeSnapshot,
    AttributeStageStatus,
    AttributeTrace,
)


def build_passport(
    *,
    profile_id: str,
    normalized_text: str,
    proposed: list[AttributeTrace],
    accepted: list[AttributeTrace],
    filtered_out: list[AttributeTrace],
    warnings: list[str] | None = None,
    stage_status: list[AttributeStageStatus] | None = None,
    snapshot: AttributeSnapshot | None = None,
    alias_matcher_backend: str | None = None,
) -> AttributePassport:
    return AttributePassport(
        profile_id=profile_id,
        snapshot=snapshot,
        alias_matcher_backend=alias_matcher_backend,
        normalized_text=normalized_text,
        proposed=proposed,
        accepted=accepted,
        filtered_out=filtered_out,
        warnings=list(warnings or []),
        stage_status=list(stage_status or []),
    )
