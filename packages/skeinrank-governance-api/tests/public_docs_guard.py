from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

PRODUCT_DOC_FORBIDDEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b[Pp]atch(?:es)?\b"),
    re.compile(r"\bpatch-era\b", re.IGNORECASE),
    re.compile(r"\bfollow-up patches\b", re.IGNORECASE),
    re.compile(r"\blater patches\b", re.IGNORECASE),
    re.compile(r"\bfuture patches\b", re.IGNORECASE),
    re.compile(r"\bdev[- ]?journal\b", re.IGNORECASE),
    re.compile(r"\bdevelopment diary\b", re.IGNORECASE),
)

INTERNAL_MILESTONE_PATTERN = re.compile(r"\b\d{2}[A-Z]\b")


def read_repo_file(path: str | Path) -> str:
    repo_path = REPO_ROOT / path if isinstance(path, str) else path
    return repo_path.read_text(encoding="utf-8")


def assert_required_fragments(
    content: str, fragments: tuple[str, ...] | list[str]
) -> None:
    missing = [fragment for fragment in fragments if fragment not in content]
    assert not missing, f"Missing expected fragments: {missing}"


def assert_productized_text(
    content: str,
    *,
    source: str | Path,
    extra_forbidden: tuple[str | re.Pattern[str], ...] = (),
    forbid_internal_milestones: bool = False,
) -> None:
    patterns: list[re.Pattern[str]] = list(PRODUCT_DOC_FORBIDDEN_PATTERNS)
    if forbid_internal_milestones:
        patterns.append(INTERNAL_MILESTONE_PATTERN)
    for item in extra_forbidden:
        patterns.append(re.compile(re.escape(item)) if isinstance(item, str) else item)

    violations = [pattern.pattern for pattern in patterns if pattern.search(content)]
    assert (
        not violations
    ), f"{source}: forbidden public-doc patterns found: {violations}"


def assert_productized_repo_files(
    paths: tuple[str | Path, ...] | list[str | Path],
    *,
    extra_forbidden: tuple[str | re.Pattern[str], ...] = (),
    forbid_internal_milestones: bool = False,
) -> None:
    for path in paths:
        repo_path = REPO_ROOT / path if isinstance(path, str) else path
        assert_productized_text(
            repo_path.read_text(encoding="utf-8"),
            source=repo_path.relative_to(REPO_ROOT),
            extra_forbidden=extra_forbidden,
            forbid_internal_milestones=forbid_internal_milestones,
        )
