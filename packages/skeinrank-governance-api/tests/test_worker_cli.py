from __future__ import annotations

import pytest
from skeinrank_governance_api import worker_cli


class FakeCeleryApp:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def worker_main(self, argv: list[str]) -> int:
        self.calls.append(argv)
        return 0


def test_worker_cli_invokes_app_worker_main(monkeypatch):
    app = FakeCeleryApp()
    monkeypatch.setattr(worker_cli, "celery_app", app)

    exit_code = worker_cli.main(
        [
            "--loglevel",
            "debug",
            "--queues",
            "skeinrank.enrichment",
            "--pool",
            "solo",
            "--concurrency",
            "1",
        ]
    )

    assert exit_code == 0
    assert app.calls == [
        [
            "worker",
            "--loglevel=debug",
            "--queues=skeinrank.enrichment",
            "--pool=solo",
            "--concurrency=1",
        ]
    ]


def test_worker_cli_raises_when_celery_app_is_missing(monkeypatch):
    monkeypatch.setattr(worker_cli, "celery_app", object())

    with pytest.raises(RuntimeError, match="Celery is not installed"):
        worker_cli.main([])
