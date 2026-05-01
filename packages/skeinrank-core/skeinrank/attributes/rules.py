from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from .normalize import normalize_value
from .types import AttributeSlot


@dataclass(frozen=True)
class RegexRule:
    rule_id: str
    slot: AttributeSlot
    pattern: str
    canonical: str | None = None
    canonical_template: str | None = None
    confidence: float = 0.9
    flags: int = 0

    def compile(self) -> re.Pattern[str]:
        return re.compile(self.pattern, self.flags)


@dataclass(frozen=True)
class RuleMatch:
    rule_id: str
    slot: AttributeSlot
    canonical: str
    matched_text: str
    start: int
    end: int
    confidence: float


class RuleSet:
    def __init__(self, rules: Iterable[RegexRule]):
        self._rules = list(rules)
        self._compiled = [(rule, rule.compile()) for rule in self._rules]

    @classmethod
    def from_profile(cls, raw_rules: Iterable[dict[str, Any]]) -> "RuleSet":
        rules = [
            RegexRule(
                rule_id=str(item["id"]),
                slot=AttributeSlot(str(item["slot"])),
                pattern=str(item["pattern"]),
                canonical=item.get("canonical"),
                canonical_template=item.get("canonical_template"),
                confidence=float(item.get("confidence", 0.9)),
                flags=re.IGNORECASE if item.get("ignore_case", True) else 0,
            )
            for item in raw_rules
        ]
        return cls(rules)

    def find(self, normalized_text: str) -> list[RuleMatch]:
        matches: list[RuleMatch] = []
        for rule, pattern in self._compiled:
            for match in pattern.finditer(normalized_text):
                matched_text = match.group(0)
                if rule.canonical is not None:
                    canonical = normalize_value(rule.canonical)
                elif rule.canonical_template is not None:
                    canonical = normalize_value(
                        rule.canonical_template.format(match=matched_text)
                    )
                else:
                    canonical = normalize_value(matched_text)
                matches.append(
                    RuleMatch(
                        rule_id=rule.rule_id,
                        slot=rule.slot,
                        canonical=canonical,
                        matched_text=matched_text,
                        start=match.start(),
                        end=match.end(),
                        confidence=rule.confidence,
                    )
                )
        return matches


def should_filter(
    *,
    slot: AttributeSlot,
    value: str,
    global_stopwords: set[str],
    slot_stopwords: dict[str, set[str]],
) -> str | None:
    if value in global_stopwords:
        return "global_stopword"
    slot_sw = slot_stopwords.get(slot.value, set())
    if value in slot_sw:
        return f"slot_stopword:{slot.value}"
    return None
