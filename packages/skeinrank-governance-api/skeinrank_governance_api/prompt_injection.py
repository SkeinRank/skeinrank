"""Prompt-like instruction risk detection for untrusted runtime text.

The detector is intentionally small, deterministic, and dependency-free. It does
not try to classify every malicious prompt. It flags high-signal instruction-like
phrases that should be surfaced to reviewers before evidence, imports, or agent
proposals become trusted runtime terminology.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

PROMPT_INJECTION_RISK_SCHEMA_VERSION = "skeinrank.prompt_injection_risk.v1"
PROMPT_INJECTION_RISK_CODES = (
    "prompt_like_instruction",
    "hidden_prompt_request",
    "secret_exfiltration_request",
    "tool_injection_request",
    "destructive_action_request",
    "html_instruction_comment",
)

_MAX_FINDING_TEXT_CHARS = 160
_MAX_SCAN_TEXT_CHARS = 20000
_MAX_FINDINGS = 50


PROMPT_INJECTION_REGRESSION_CASE_SCHEMA_VERSION = (
    "skeinrank.prompt_injection_regression_case.v1"
)


def evaluate_prompt_injection_regression_case(
    record: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate one stable prompt-injection regression corpus record.

    Records may provide either a plain ``text`` value or a JSON-like ``payload``
    value. The evaluator is intentionally deterministic so the example corpus can
    be used in docs, local tests, and CI without external services.
    """

    case_id = str(record.get("id") or "")
    expected_status = str(record.get("expected_status") or "clear")
    expected_risk_codes = tuple(
        str(code) for code in record.get("expected_risk_codes", ())
    )
    base_path = str(record.get("base_path") or "$")

    if "payload" in record:
        findings = scan_untrusted_payload(record["payload"], base_path=base_path)
    else:
        findings = detect_prompt_like_instructions(record.get("text"), path=base_path)

    summary = build_prompt_injection_risk_summary(findings)
    actual_risk_codes = tuple(summary["risk_flags"])
    expected_code_set = set(expected_risk_codes)
    actual_code_set = set(actual_risk_codes)
    status_matches = summary["status"] == expected_status
    codes_match = expected_code_set.issubset(actual_code_set)
    expected_min_findings = int(record.get("expected_min_findings") or 0)
    min_findings_match = summary["findings_total"] >= expected_min_findings

    return {
        "schema_version": "skeinrank.prompt_injection_regression_result.v1",
        "case_id": case_id,
        "expected_status": expected_status,
        "actual_status": summary["status"],
        "expected_risk_codes": list(expected_risk_codes),
        "actual_risk_codes": list(actual_risk_codes),
        "findings_total": summary["findings_total"],
        "passed": status_matches and codes_match and min_findings_match,
        "summary": summary,
    }


@dataclass(frozen=True)
class PromptInjectionPattern:
    """Compiled prompt-like signal pattern."""

    risk_code: str
    category: str
    severity: str
    pattern: re.Pattern[str]
    message: str


@dataclass(frozen=True)
class PromptInjectionFinding:
    """One prompt-like signal found in untrusted text."""

    risk_code: str
    category: str
    severity: str
    message: str
    path: str
    matched_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_code": self.risk_code,
            "category": self.category,
            "severity": self.severity,
            "message": self.message,
            "path": self.path,
            "matched_text": self.matched_text,
        }


_PATTERNS: tuple[PromptInjectionPattern, ...] = (
    PromptInjectionPattern(
        risk_code="prompt_like_instruction",
        category="instruction_override",
        severity="high",
        pattern=re.compile(
            r"\b(?:ignore|disregard|forget|override)\s+(?:all\s+)?(?:previous|prior|above|system|developer)\s+instructions?\b",
            re.IGNORECASE,
        ),
        message="Text asks the model or agent to ignore higher-priority instructions.",
    ),
    PromptInjectionPattern(
        risk_code="prompt_like_instruction",
        category="instruction_override",
        severity="high",
        pattern=re.compile(
            r"\b(?:you\s+are\s+now|act\s+as|pretend\s+to\s+be)\s+(?:system|developer|admin|root|sudo|unrestricted)",
            re.IGNORECASE,
        ),
        message="Text attempts to redefine the model or agent role.",
    ),
    PromptInjectionPattern(
        risk_code="hidden_prompt_request",
        category="policy_exfiltration",
        severity="high",
        pattern=re.compile(
            r"\b(?:reveal|show|print|return|dump|display)\s+(?:the\s+)?(?:system\s+prompt|developer\s+message|hidden\s+instructions?|policy\s+prompt|secret\s+instructions?)\b",
            re.IGNORECASE,
        ),
        message="Text asks to expose hidden prompts or policy instructions.",
    ),
    PromptInjectionPattern(
        risk_code="secret_exfiltration_request",
        category="secret_exfiltration",
        severity="high",
        pattern=re.compile(
            r"\b(?:send|email|upload|exfiltrate|leak|print|dump|return)\s+(?:all\s+)?(?:credentials?|secrets?|api\s*keys?|tokens?|private\s+documents?|all\s+documents|context)\b",
            re.IGNORECASE,
        ),
        message="Text asks to expose credentials, secrets, context, or private documents.",
    ),
    PromptInjectionPattern(
        risk_code="tool_injection_request",
        category="tool_injection",
        severity="high",
        pattern=re.compile(
            r"\b(?:use|call|invoke|execute|run)\s+(?:the\s+)?(?:gmail|email|slack|github|kubectl|shell|bash|terminal|browser|deployment|tool)\b",
            re.IGNORECASE,
        ),
        message="Text asks an agent to call tools outside the evidence/import boundary.",
    ),
    PromptInjectionPattern(
        risk_code="destructive_action_request",
        category="destructive_action",
        severity="high",
        pattern=re.compile(
            r"\b(?:delete|drop|destroy|wipe|erase|remove)\s+(?:the\s+)?(?:cluster|index|database|table|production|prod|data|documents?|snapshots?)\b",
            re.IGNORECASE,
        ),
        message="Text asks for destructive infrastructure or data actions.",
    ),
    PromptInjectionPattern(
        risk_code="tool_injection_request",
        category="runtime_mutation",
        severity="high",
        pattern=re.compile(
            r"\b(?:publish|approve|apply|promote|rollback)\s+(?:the\s+)?(?:snapshot|proposal|binding|production|prod)\b",
            re.IGNORECASE,
        ),
        message="Text asks to mutate governed runtime state directly.",
    ),
    PromptInjectionPattern(
        risk_code="html_instruction_comment",
        category="hidden_instruction",
        severity="high",
        pattern=re.compile(
            r"<!--[^>]*(?:ignore|reveal|system\s+prompt|developer\s+message|send\s+credentials|delete\s+cluster)[^>]*-->",
            re.IGNORECASE | re.DOTALL,
        ),
        message="Hidden markup contains prompt-like or tool-like instructions.",
    ),
)


def detect_prompt_like_instructions(
    text: object,
    *,
    path: str = "$",
    max_findings: int = _MAX_FINDINGS,
) -> list[PromptInjectionFinding]:
    """Return prompt-like risk findings found in one text value."""

    if not isinstance(text, str) or not text.strip():
        return []
    scan_text = text[:_MAX_SCAN_TEXT_CHARS]
    findings: list[PromptInjectionFinding] = []
    seen: set[tuple[str, str, str]] = set()
    for entry in _PATTERNS:
        for match in entry.pattern.finditer(scan_text):
            matched_text = _compact_match(match.group(0))
            key = (entry.risk_code, path, matched_text.lower())
            if key in seen:
                continue
            seen.add(key)
            findings.append(
                PromptInjectionFinding(
                    risk_code=entry.risk_code,
                    category=entry.category,
                    severity=entry.severity,
                    message=entry.message,
                    path=path,
                    matched_text=matched_text,
                )
            )
            if len(findings) >= max_findings:
                return findings
    return findings


def scan_untrusted_payload(
    payload: object,
    *,
    base_path: str = "$",
    max_findings: int = _MAX_FINDINGS,
) -> list[PromptInjectionFinding]:
    """Recursively scan an untrusted JSON-like payload for prompt-like text."""

    findings: list[PromptInjectionFinding] = []
    for path, value in _iter_string_values(payload, base_path=base_path):
        remaining = max_findings - len(findings)
        if remaining <= 0:
            break
        findings.extend(
            detect_prompt_like_instructions(value, path=path, max_findings=remaining)
        )
    return findings[:max_findings]


def build_prompt_injection_risk_summary(
    findings: Sequence[PromptInjectionFinding],
) -> dict[str, Any]:
    """Build a stable JSON summary for detector output."""

    counts_by_severity: dict[str, int] = {}
    counts_by_code: dict[str, int] = {}
    for finding in findings:
        counts_by_severity[finding.severity] = (
            counts_by_severity.get(finding.severity, 0) + 1
        )
        counts_by_code[finding.risk_code] = counts_by_code.get(finding.risk_code, 0) + 1
    has_findings = bool(findings)
    return {
        "schema_version": PROMPT_INJECTION_RISK_SCHEMA_VERSION,
        "status": "review_required" if has_findings else "clear",
        "findings_total": len(findings),
        "high_risk": any(finding.severity == "high" for finding in findings),
        "counts_by_severity": counts_by_severity,
        "counts_by_code": counts_by_code,
        "risk_flags": sorted({finding.risk_code for finding in findings}),
        "findings": [finding.to_dict() for finding in findings],
    }


def prompt_injection_risk_flags(
    findings: Iterable[PromptInjectionFinding],
) -> list[str]:
    """Return stable risk flag values for apply-policy integration."""

    return sorted({finding.risk_code for finding in findings})


def _iter_string_values(
    payload: object, *, base_path: str
) -> Iterable[tuple[str, str]]:
    if isinstance(payload, str):
        yield base_path, payload
        return
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_text = str(key).replace("~", "~0").replace("/", "~1")
            child_path = f"{base_path}/{key_text}" if base_path else key_text
            yield from _iter_string_values(value, base_path=child_path)
        return
    if isinstance(payload, list | tuple):
        for index, value in enumerate(payload):
            yield from _iter_string_values(value, base_path=f"{base_path}[{index}]")


def _compact_match(value: str) -> str:
    compacted = " ".join(value.strip().split())
    if len(compacted) <= _MAX_FINDING_TEXT_CHARS:
        return compacted
    return f"{compacted[: _MAX_FINDING_TEXT_CHARS - 1]}…"
