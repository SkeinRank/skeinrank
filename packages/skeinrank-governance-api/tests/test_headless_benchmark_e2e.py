from __future__ import annotations

import json

from skeinrank_governance import (
    create_all,
    create_governance_engine,
    create_session_factory,
)
from skeinrank_governance.models import AgentRun, GovernanceSuggestion, TermAlias
from skeinrank_governance_api.benchmark import (
    BENCHMARK_FORMAT_VERSION,
    DEFAULT_BENCHMARK_NAME,
    DEFAULT_PROFILE_NAME,
    reset_benchmark_state,
    resolve_benchmark_paths,
    run_benchmark_evaluation,
    seed_benchmark_state,
)
from skeinrank_governance_api.benchmark import (
    main as benchmark_main,
)
from sqlalchemy import select


def _session_factory(tmp_path):
    engine = create_governance_engine(
        f"sqlite:///{tmp_path / 'governance-benchmark.db'}",
        connect_args={"check_same_thread": False},
    )
    create_all(engine)
    return create_session_factory(engine)


def test_benchmark_fixtures_include_agent_workflow_edge_cases() -> None:
    paths = resolve_benchmark_paths()
    corpus_lines = [
        json.loads(line)
        for line in paths.corpus.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    expected = json.loads(paths.expected_aliases.read_text(encoding="utf-8"))

    assert paths.seed_dictionary.exists()
    assert paths.golden_queries.exists()
    assert any(item.get("previously_seen") is True for item in corpus_lines)
    assert any(item.get("previous_body") for item in corpus_lines)
    assert "app" in expected["expected_blocked_aliases"]
    assert "kube" in expected["expected_idempotent_aliases"]
    assert {item["alias"] for item in expected["expected_new_aliases"]} >= {
        "rmq",
        "otel",
        "pg",
    }


def test_headless_benchmark_full_agent_workflow(tmp_path) -> None:
    session_factory = _session_factory(tmp_path)
    with session_factory() as session:
        reset_benchmark_state(session)
        seed_payload = seed_benchmark_state(session)
        assert seed_payload["status"] == "seeded"

        report = run_benchmark_evaluation(session)

        assert report["format_version"] == BENCHMARK_FORMAT_VERSION
        assert report["benchmark_name"] == DEFAULT_BENCHMARK_NAME
        assert report["status"] == "passed"
        assert report["scores"]["expected_alias_recall"] == 1.0
        assert report["scores"]["runtime_canonicalization_accuracy"] == 1.0
        assert report["scores"]["unexpected_proposals"] == 0
        assert report["counts"]["visit_statuses"]["unchanged_seen"] == 1
        assert report["counts"]["visit_statuses"]["content_changed"] == 1
        assert report["counts"]["idempotent_noops"] == 1
        assert report["counts"]["suggestions_approved"] == 3
        assert report["counts"]["validation_statuses"]["blocked"] == 1

        aliases = {
            alias.normalized_alias: alias.term.normalized_value
            for alias in session.scalars(select(TermAlias)).all()
        }
        assert aliases["rmq"] == "rabbitmq"
        assert aliases["otel"] == "opentelemetry"
        assert aliases["pg"] == "postgresql"
        assert "app" not in aliases

        suggestions = list(session.scalars(select(GovernanceSuggestion)).all())
        assert {suggestion.status for suggestion in suggestions} == {"approved"}

        run = session.scalar(
            select(AgentRun).where(AgentRun.run_id == report["run_id"])
        )
        assert run is not None
        assert run.status == "succeeded"
        assert run.summary_json["benchmark_name"] == DEFAULT_BENCHMARK_NAME


def test_benchmark_cli_seed_eval_report_and_reset(tmp_path, capsys) -> None:
    database_url = f"sqlite:///{tmp_path / 'benchmark-cli.db'}"
    report_path = tmp_path / "benchmark-report.json"

    assert benchmark_main(["--database-url", database_url, "seed", "--reset"]) == 0
    seed_stdout = capsys.readouterr().out
    assert '"status": "seeded"' in seed_stdout

    assert (
        benchmark_main(
            ["--database-url", database_url, "eval", "--out", str(report_path)]
        )
        == 0
    )
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "passed"

    assert (
        benchmark_main(
            ["--database-url", database_url, "report", "--file", str(report_path)]
        )
        == 0
    )
    report_stdout = capsys.readouterr().out
    assert '"format_version": "skeinrank.benchmark_report.v1"' in report_stdout

    assert benchmark_main(["--database-url", database_url, "reset"]) == 0
    reset_stdout = capsys.readouterr().out
    assert DEFAULT_PROFILE_NAME in reset_stdout
