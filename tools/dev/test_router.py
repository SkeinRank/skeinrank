"""Route local tests from the files changed in the working tree.

The router is intentionally conservative. It selects existing Make targets from
repository paths instead of trying to run pytest modules directly. This keeps the
routing logic small while preserving the package-specific Poetry environments
owned by the root Makefile.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass

from console import Console, Timer, format_duration


@dataclass(frozen=True)
class RouteRule:
    """Map changed file prefixes to root Makefile targets."""

    name: str
    targets: tuple[str, ...]
    prefixes: tuple[str, ...]
    exact_paths: tuple[str, ...] = ()

    def matches(self, path: str) -> bool:
        return path in self.exact_paths or any(
            path.startswith(prefix) for prefix in self.prefixes
        )


TARGET_ORDER: tuple[str, ...] = (
    "test-fast",
    "test-scout",
    "test-migrations",
    "test-docs",
    "test-governance-models",
    "test-governance-api",
    "test-core",
    "test-provider-elasticsearch",
    "test-server",
    "test-ui",
)

ROUTE_RULES: tuple[RouteRule, ...] = (
    RouteRule(
        name="developer commands and public docs",
        targets=("test-docs",),
        prefixes=(
            "docs/",
            "examples/agents/openrouter_alias_scout/README.md",
            "packages/skeinrank-core/README.md",
            "packages/skeinrank-governance-api/README.md",
        ),
        exact_paths=(
            "README.md",
            "CONTRIBUTING.md",
            "Makefile",
            "tools/dev/resolve_ruff.py",
            "tools/dev/test_router.py",
        ),
    ),
    RouteRule(
        name="core candidate and SDK code",
        targets=("test-fast",),
        prefixes=(
            "packages/skeinrank-core/skeinrank/",
            "packages/skeinrank-core/tests/test_candidate_discovery.py",
            "packages/skeinrank-core/tests/test_dictionary_suggestions.py",
            "packages/skeinrank-core/tests/test_drift_scan_cli.py",
        ),
        exact_paths=("packages/skeinrank-core/pyproject.toml",),
    ),
    RouteRule(
        name="Alias Scout and review workflow",
        targets=("test-scout",),
        prefixes=(
            "examples/agents/openrouter_alias_scout/",
            "packages/skeinrank-governance-api/skeinrank_governance_api/agent_llm_reviews.py",
            "packages/skeinrank-governance-api/skeinrank_governance_api/review_dataset_events.py",
            "packages/skeinrank-governance-api/skeinrank_governance_api/canonical_lifecycle.py",
            "packages/skeinrank-governance-api/tests/test_openrouter_agent_",
            "packages/skeinrank-governance-api/tests/test_agent_review_dataset_events.py",
            "packages/skeinrank-governance-api/tests/test_canonical_lifecycle_migrations.py",
        ),
    ),
    RouteRule(
        name="governance API routes and schemas",
        targets=("test-governance-api",),
        prefixes=(
            "packages/skeinrank-governance-api/skeinrank_governance_api/routes/",
            "packages/skeinrank-governance-api/skeinrank_governance_api/schemas.py",
            "packages/skeinrank-governance-api/tests/test_governance_",
            "packages/skeinrank-governance-api/tests/test_proposal_",
        ),
        exact_paths=("packages/skeinrank-governance-api/pyproject.toml",),
    ),
    RouteRule(
        name="database models and migrations",
        targets=("test-migrations", "test-governance-models"),
        prefixes=(
            "packages/skeinrank-governance/alembic/",
            "packages/skeinrank-governance/skeinrank_governance/",
            "packages/skeinrank-governance-api/tests/test_migrations.py",
            "packages/skeinrank-governance-api/tests/test_schema_health.py",
        ),
        exact_paths=("packages/skeinrank-governance/pyproject.toml",),
    ),
    RouteRule(
        name="Elasticsearch provider",
        targets=("test-provider-elasticsearch",),
        prefixes=("packages/skeinrank-provider-elasticsearch/",),
    ),
    RouteRule(
        name="server package",
        targets=("test-server",),
        prefixes=("packages/skeinrank-server/",),
    ),
    RouteRule(
        name="UI package",
        targets=("test-ui",),
        prefixes=("packages/skeinrank-ui/",),
    ),
    RouteRule(
        name="CI and packaging metadata",
        targets=("test-docs",),
        prefixes=(".github/",),
        exact_paths=("pyproject.toml", "poetry.lock"),
    ),
)


def _run_git(args: list[str]) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise RuntimeError(message)
    return [line.rstrip() for line in result.stdout.splitlines() if line.strip()]


def _parse_porcelain_path(line: str) -> str | None:
    if len(line) < 4:
        return None
    payload = line[3:]
    if " -> " in payload:
        payload = payload.rsplit(" -> ", maxsplit=1)[-1]
    return payload.strip() or None


def changed_files(base: str | None = None) -> list[str]:
    """Return repository-relative changed files.

    Without a base, both staged and unstaged working-tree changes are included.
    With a base, committed branch changes are included as well, then combined
    with the current working tree so local edits are not missed.
    """

    files: set[str] = set()
    for line in _run_git(["status", "--porcelain"]):
        path = _parse_porcelain_path(line)
        if path:
            files.add(path)

    if base:
        for path in _run_git(["diff", "--name-only", f"{base}...HEAD"]):
            files.add(path)

    return sorted(files)


def selected_targets(paths: list[str]) -> list[str]:
    targets: set[str] = set()
    for path in paths:
        for rule in ROUTE_RULES:
            if rule.matches(path):
                targets.update(rule.targets)

    if not targets and paths:
        targets.add("test-fast")

    return [target for target in TARGET_ORDER if target in targets]


def print_plan(
    paths: list[str],
    targets: list[str],
    *,
    console: Console | None = None,
) -> None:
    console = console or Console()
    console.title("SkeinRank developer checks")

    console.section("Changed files")
    if paths:
        for path in paths:
            console.bullet(path)
    else:
        console.muted("none detected")

    console.section("Selected checks")
    if targets:
        for target in targets:
            console.success(f"make {target}")
    else:
        console.muted("none")


def run_targets(targets: list[str], *, console: Console | None = None) -> int:
    console = console or Console()
    if not targets:
        console.section("Result")
        console.muted("No changed files matched a test route. Nothing to run.")
        return 0

    overall = Timer()
    for target in targets:
        console.section(f"Running make {target}")
        console.command(f"make {target}")
        timer = Timer()
        returncode = subprocess.call(["make", target])
        elapsed = format_duration(timer.elapsed())
        if returncode != 0:
            console.section("Result")
            console.error(f"make {target} failed after {elapsed}")
            return returncode
        console.success(f"make {target} passed in {elapsed}")

    console.section("Result")
    console.success(
        f"all selected checks passed in {format_duration(overall.elapsed())}"
    )
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Route local tests from changed files."
    )
    parser.add_argument(
        "--base", help="Optional git base ref, for example origin/main."
    )
    parser.add_argument("--run", action="store_true", help="Run selected Make targets.")
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Print selected Make targets without running them.",
    )
    args = parser.parse_args(argv)

    try:
        paths = changed_files(base=args.base)
    except RuntimeError as exc:
        print(f"Unable to inspect changed files: {exc}", file=sys.stderr)
        return 2

    console = Console()
    targets = selected_targets(paths)
    print_plan(paths, targets, console=console)

    if args.run:
        return run_targets(targets, console=console)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
