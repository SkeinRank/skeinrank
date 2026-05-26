from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_benchmark_stack_module_is_valid_python_and_exposes_cli() -> None:
    source = _read(
        "packages/skeinrank-governance-api/skeinrank_governance_api/benchmark_stack.py"
    )
    tree = ast.parse(source)
    functions = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}

    assert "build_arg_parser" in functions
    assert "main" in functions
    for command in ["wait", "reset", "seed", "index", "eval", "report"]:
        assert f'"{command}"' in source


def test_makefile_exposes_containerized_benchmark_targets() -> None:
    makefile = _read("Makefile")

    for target in [
        "benchmark-stack-up:",
        "benchmark-stack-wait:",
        "benchmark-stack-reset:",
        "benchmark-stack-seed:",
        "benchmark-stack-eval:",
        "benchmark-stack-report:",
        "benchmark-stack-clean:",
        "benchmark-stack-down:",
        "benchmark-stack-run:",
    ]:
        assert target in makefile

    assert "--env-file $(BENCHMARK_STACK_ENV_FILE)" in makefile
    assert "-p $(BENCHMARK_STACK_COMPOSE_PROJECT)" in makefile
    assert "skeinrank_governance_api.benchmark_stack" in makefile
    assert (
        "postgres rabbitmq elasticsearch governance-migrate governance-api" in makefile
    )


def test_benchmark_stack_uses_dev_stack_defaults() -> None:
    makefile = _read("Makefile")

    assert "BENCHMARK_STACK_ENV_FILE ?= deploy/docker/benchmark.env.example" in makefile
    assert "BENCHMARK_STACK_COMPOSE_PROJECT ?= skeinrank-benchmark" in makefile
    assert "POSTGRES_PASSWORD=skeinrank_dev_password" in makefile
    assert "BENCHMARK_STACK_DATABASE_URL ?= postgresql+psycopg://app_user:" in makefile
    assert "BENCHMARK_STACK_API_URL ?= http://127.0.0.1:8010" in makefile
    assert "BENCHMARK_STACK_ES_URL ?= http://127.0.0.1:19200" in makefile
    assert "BENCHMARK_STACK_ADMIN_USERNAME ?= admin" in makefile
    assert "BENCHMARK_STACK_ADMIN_PASSWORD ?= change-me" in makefile


def test_benchmark_stack_docs_are_linked() -> None:
    docs_readme = _read("docs/README.md")
    root_readme = _read("README.md")
    package_readme = _read("packages/skeinrank-governance-api/README.md")
    guide = _read("docs/benchmarks/containerized-benchmark-integration.md")

    assert "benchmarks/containerized-benchmark-integration.md" in docs_readme
    assert "benchmark-stack-run" in root_readme
    assert "benchmark-stack-eval" in package_readme
    assert "skeinrank.benchmark_stack_report.v1" in guide
    assert "PostgreSQL, Governance API, and Elasticsearch" in guide
    assert "quality report" in guide
    assert "proposal quality metrics" in guide
    assert "agent decision diagnostics" in guide


def test_benchmark_stack_harness_is_not_openrouter_live_mode() -> None:
    source = _read(
        "packages/skeinrank-governance-api/skeinrank_governance_api/benchmark_stack.py"
    )

    assert "OPENROUTER_API_KEY" not in source
    assert "run_openrouter" not in source.lower()
    assert "openrouter_alias_scout" not in source
    assert "/v1/governance/elasticsearch/bindings/{binding_id}/evidence" in source
    assert "/v1/query/plan" in source
    assert "skeinrank.benchmark_stack_report.v1" in source
    assert 'base_report.get("quality")' in source
    assert 'base_report.get("proposal_quality")' in source
    assert 'base_report.get("agent_decision_diagnostics")' in source


def test_benchmark_stack_prunes_fixed_dev_container_names() -> None:
    makefile = _read("Makefile")

    assert "benchmark-stack-prune-containers:" in makefile
    assert "BENCHMARK_STACK_CONTAINERS ?=" in makefile
    assert "skeinrank-elasticsearch-dev" in makefile
    assert "docker rm -f $(BENCHMARK_STACK_CONTAINERS)" in makefile
    assert "BENCHMARK_STACK_VOLUMES ?=" in makefile
    assert "docker volume rm $(BENCHMARK_STACK_VOLUMES)" in makefile
    assert "down -v --remove-orphans" in makefile
    assert "benchmark-stack-up: benchmark-stack-prune-containers" in makefile


def test_benchmark_stack_declares_postgres_driver_dependency() -> None:
    pyproject = _read("packages/skeinrank-governance-api/pyproject.toml")
    source = _read(
        "packages/skeinrank-governance-api/skeinrank_governance_api/benchmark_stack.py"
    )

    assert "psycopg" in pyproject
    assert 'extras = ["binary"]' in pyproject
    assert "PostgreSQL benchmark stack requires the local psycopg driver" in source


def test_benchmark_stack_docs_include_troubleshooting() -> None:
    guide = _read("docs/benchmarks/containerized-benchmark-integration.md")

    assert "benchmark-stack-prune-containers" in guide
    assert "poetry install" in guide
    assert "deploy/docker/benchmark.env.example" in guide
    assert "password authentication failed" in guide


def test_benchmark_stack_env_file_is_pinned_to_expected_local_values() -> None:
    env_file = _read("deploy/docker/benchmark.env.example")

    assert "COMPOSE_PROJECT_NAME=skeinrank-benchmark" in env_file
    assert "POSTGRES_USER=app_user" in env_file
    assert "POSTGRES_PASSWORD=skeinrank_dev_password" in env_file
    assert "SKEINRANK_GOVERNANCE_API_ADMIN_USERNAME=admin" in env_file
    assert "SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD=change-me" in env_file


def test_benchmark_stack_user_facing_errors_are_clean() -> None:
    source = _read(
        "packages/skeinrank-governance-api/skeinrank_governance_api/benchmark_stack.py"
    )

    assert "remote end closed connection without response" in source
    assert "PostgreSQL benchmark stack authentication failed" in source
    assert "make benchmark-stack-prune-containers" in source
