"""Command-line launcher for the SkeinRank governance Celery worker."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from .worker import MissingCeleryApp


def main(argv: Sequence[str] | None = None) -> int:
    """Run a Celery worker for governance enrichment jobs."""

    parser = argparse.ArgumentParser(
        prog="skeinrank-governance-worker",
        description="Run the SkeinRank governance Celery worker.",
    )
    parser.add_argument("--loglevel", default="info")
    parser.add_argument("--queues", default=None)
    args = parser.parse_args(argv)

    try:
        from celery.bin.celery import main as celery_main
    except ImportError as exc:  # pragma: no cover - depends on optional dependency
        raise RuntimeError(MissingCeleryApp.missing_reason) from exc

    command = [
        "celery",
        "-A",
        "skeinrank_governance_api.worker:celery_app",
        "worker",
        f"--loglevel={args.loglevel}",
    ]
    if args.queues:
        command.append(f"--queues={args.queues}")
    return int(celery_main(command) or 0)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
