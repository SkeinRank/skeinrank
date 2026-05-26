from __future__ import annotations

import json

from skeinrank_governance import (
    create_all,
    create_governance_engine,
    create_session_factory,
)
from skeinrank_governance.models import (
    AgentDocumentVisit,
    AgentRun,
    GovernanceSuggestion,
    TermAlias,
)
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
    assert len(corpus_lines) == 50
    assert {item["alias"] for item in expected["expected_new_aliases"]} >= {
        "rmq",
        "otel",
        "pg",
        "prom",
        "lk",
        "ns",
        "svc",
        "redis-sentinel",
        "redis-cluster",
        "slo",
        "es",
    }
    assert expected["quality_thresholds"]["min_proposal_precision_like"] == 1.0


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
        assert report["scores"]["proposal_precision_like"] == 1.0
        assert report["scores"]["proposal_recall_like"] == 1.0
        assert report["scores"]["alias_coverage"] == 1.0
        assert report["scores"]["noise_rate"] == 0.0
        assert report["counts"]["documents_total"] == 50
        assert report["counts"]["visit_statuses"]["unchanged_seen"] == 2
        assert report["counts"]["visit_statuses"]["content_changed"] == 2
        assert report["counts"]["idempotent_noops"] == 3
        assert report["counts"]["suggestions_approved"] == 11
        assert report["counts"]["validation_statuses"]["blocked"] == 4
        assert report["quality"]["schema_version"] == "skeinrank.benchmark_quality.v1"
        assert report["quality"]["proposal_precision_like"] == 1.0
        assert report["quality"]["accepted_expected_proposals"] == 11
        assert report["quality"]["unexpected_created_proposals"] == 0
        assert report["quality"]["blocked_proposals_count"] == 4
        assert report["quality"]["warning_proposals_count"] >= 1
        assert report["quality"]["missing_warning_aliases"] == []
        assert report["quality"]["expected_warning_aliases_count"] == 4
        assert report["quality"]["snapshot_created"] is True
        assert all(
            item["status"] == "passed" for item in report["quality"]["quality_gates"]
        )
        assert (
            report["proposal_quality"]["schema_version"]
            == "skeinrank.proposal_quality_metrics.v1"
        )
        assert report["proposal_quality"]["totals"]["proposal_attempts"] == 18
        assert report["proposal_quality"]["totals"]["candidate_observations"] == 18
        assert report["proposal_quality"]["rates"]["proposal_precision_like"] == 1.0
        assert report["proposal_quality"]["rates"]["proposal_recall_like"] == 1.0
        assert report["proposal_quality"]["rates"]["evidence_window_coverage"] == 1.0
        assert report["proposal_quality"]["rates"]["proposal_attempt_coverage"] == 1.0
        assert report["proposal_quality"]["coverage"]["missed_expected_proposals"] == 0
        assert report["proposal_quality"]["coverage"]["blocked_missing"] == []
        assert (
            report["proposal_quality"]["breakdowns"]["by_alias_class"]["blocked_noise"]
            == 4
        )
        assert (
            report["proposal_quality"]["breakdowns"]["by_outcome"]["approved_expected"]
            == 11
        )
        assert report["proposal_quality"]["aliases"]["unexpected_created"] == []
        assert len(report["proposal_quality"]["alias_outcomes"]) == 18
        assert all(
            item["status"] == "passed"
            for item in report["proposal_quality"]["quality_gates"]
        )

        aliases = {
            alias.normalized_alias: alias.term.normalized_value
            for alias in session.scalars(select(TermAlias)).all()
        }
        assert aliases["rmq"] == "rabbitmq"
        assert aliases["otel"] == "opentelemetry"
        assert aliases["pg"] == "postgresql"
        assert aliases["prom"] == "prometheus"
        assert aliases["lk"] == "loki"
        assert aliases["ns"] == "namespace"
        assert aliases["svc"] == "service"
        assert aliases["redis-sentinel"] == "redis sentinel"
        assert aliases["redis-cluster"] == "redis cluster"
        assert aliases["slo"] == "service level objective"
        assert aliases["es"] == "elasticsearch"
        assert "app" not in aliases
        assert "error" not in aliases
        assert "job" not in aliases
        assert "api" not in aliases

        suggestions = list(session.scalars(select(GovernanceSuggestion)).all())
        assert {suggestion.status for suggestion in suggestions} == {"approved"}

        run = session.scalar(
            select(AgentRun).where(AgentRun.run_id == report["run_id"])
        )
        assert run is not None
        assert run.status == "succeeded"
        assert run.summary_json["benchmark_name"] == DEFAULT_BENCHMARK_NAME


def test_benchmark_reset_cleans_agent_tracking_for_reruns(tmp_path) -> None:
    session_factory = _session_factory(tmp_path)
    with session_factory() as session:
        reset_benchmark_state(session)
        seed_benchmark_state(session)
        first_report = run_benchmark_evaluation(session)

        assert first_report["status"] == "passed"
        assert session.scalar(select(AgentRun)) is not None
        assert session.scalar(select(AgentDocumentVisit)) is not None

        reset_benchmark_state(session)

        assert list(session.scalars(select(AgentRun)).all()) == []
        assert list(session.scalars(select(AgentDocumentVisit)).all()) == []

        seed_benchmark_state(session)
        second_report = run_benchmark_evaluation(session)

        assert second_report["status"] == "passed"
        assert second_report["counts"]["documents_total"] == 50


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
