from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

try:
    from elasticsearch import Elasticsearch
except Exception:  # pragma: no cover
    Elasticsearch = None  # type: ignore[assignment]

from skeinrank import load_attribute_profile

from .enrichment import (
    ElasticsearchEnrichmentConfig,
    preview_enrichment,
    write_enrichment,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skeinrank-es-enrich",
        description="Enrich an Elasticsearch index with SkeinRank attributes.",
    )
    parser.add_argument(
        "--url", default="http://localhost:9200", help="Elasticsearch URL"
    )
    parser.add_argument("--index", required=True, help="Elasticsearch index to read")
    parser.add_argument(
        "--text-field",
        action="append",
        dest="text_fields",
        required=True,
        help="Text field to read. Can be passed multiple times, e.g. --text-field title --text-field body.",
    )
    parser.add_argument(
        "--target-field",
        default="skeinrank",
        help="Field that would receive the enrichment payload",
    )
    parser.add_argument(
        "--profile", default="default_it", help="Built-in SkeinRank attribute profile"
    )
    parser.add_argument(
        "--profile-file",
        type=Path,
        default=None,
        help="Path to a custom JSON terminology profile snapshot",
    )
    parser.add_argument(
        "--limit", type=int, default=20, help="Maximum number of documents to preview"
    )
    parser.add_argument(
        "--batch-size", type=int, default=50, help="Elasticsearch read batch size"
    )
    parser.add_argument(
        "--include-passport",
        action="store_true",
        help="Include full passport/debug trace in enrichment payloads",
    )
    parser.add_argument(
        "--include-evidence",
        action="store_true",
        help="Include full attributes, evidences, and snapshot metadata instead of the compact production payload",
    )
    parser.add_argument(
        "--enable-fuzzy",
        action="store_true",
        help="Enable conservative fuzzy alias fallback for typo-like terms.",
    )
    parser.add_argument(
        "--fuzzy-threshold",
        type=float,
        default=0.9,
        help="Minimum fuzzy similarity in the range (0, 1]. Default: 0.9.",
    )
    parser.add_argument(
        "--fuzzy-min-length",
        type=int,
        default=4,
        help="Minimum token/alias length for fuzzy matching. Default: 4.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview updates without writing to Elasticsearch",
    )
    mode.add_argument(
        "--write",
        action="store_true",
        help="Write enrichment payloads to Elasticsearch with bulk update",
    )
    parser.add_argument("--out", help="Optional path to write the JSON dry-run report")
    return parser


def _make_client(url: str) -> Any:
    if Elasticsearch is None:  # pragma: no cover - depends on optional install state
        raise RuntimeError("elasticsearch package is not installed")
    return Elasticsearch(url)


def run(
    argv: Sequence[str] | None = None, *, client: Any | None = None
) -> dict[str, Any]:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    config = ElasticsearchEnrichmentConfig(
        index=args.index,
        text_fields=tuple(args.text_fields),
        target_field=args.target_field,
        profile=load_attribute_profile(args.profile_file)
        if args.profile_file is not None
        else args.profile,
        limit=args.limit,
        batch_size=args.batch_size,
        include_passport=bool(args.include_passport),
        include_evidence=bool(args.include_evidence),
        enable_fuzzy=bool(args.enable_fuzzy),
        fuzzy_threshold=args.fuzzy_threshold,
        fuzzy_min_length=args.fuzzy_min_length,
    )
    es_client = client if client is not None else _make_client(args.url)
    report = (
        preview_enrichment(es_client, config)
        if args.dry_run
        else write_enrichment(es_client, config)
    )

    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    try:
        run(argv)
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover - defensive CLI path
        print(f"skeinrank-es-enrich: error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
