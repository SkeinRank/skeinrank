"""Command-line launcher for the SkeinRank governance Celery worker."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from .worker import MissingCeleryApp, celery_app


def main(argv: Sequence[str] | None = None) -> int:
    """Run a Celery worker for governance enrichment jobs."""

    parser = argparse.ArgumentParser(
        prog="skeinrank-governance-worker",
        description="Run the SkeinRank governance Celery worker.",
    )
    parser.add_argument("--loglevel", default="info")
    parser.add_argument("--queues", default=None)
    parser.add_argument("--pool", default=None)
    parser.add_argument("--concurrency", default=None)
    args = parser.parse_args(argv)

    if isinstance(celery_app, MissingCeleryApp) or not hasattr(
        celery_app, "worker_main"
    ):
        raise RuntimeError(MissingCeleryApp.missing_reason)

    command = ["worker", f"--loglevel={args.loglevel}"]
    if args.queues:
        command.append(f"--queues={args.queues}")
    if args.pool:
        command.append(f"--pool={args.pool}")
    if args.concurrency:
        command.append(f"--concurrency={args.concurrency}")
    return int(celery_app.worker_main(argv=command) or 0)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
