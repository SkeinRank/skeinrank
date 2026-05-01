from __future__ import annotations

import argparse
import json
from pathlib import Path

from .demo import enrich_jsonl, evaluate_demo_queries, load_jsonl


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m skeinrank.attributes.demo_cli")
    sub = parser.add_subparsers(dest="command", required=True)

    enrich = sub.add_parser(
        "enrich", help="Enrich a JSONL corpus with extracted attributes."
    )
    enrich.add_argument("input", type=Path)
    enrich.add_argument("output", type=Path)
    enrich.add_argument("--profile", default="default_it")
    enrich.add_argument("--no-debug", action="store_true")
    enrich.add_argument("--title-field", default="title")
    enrich.add_argument("--text-field", default="text")

    evaluate = sub.add_parser(
        "eval", help="Run a tiny baseline vs normalized eval over demo JSONL files."
    )
    evaluate.add_argument("queries", type=Path)
    evaluate.add_argument(
        "documents", type=Path, help="Path to enriched document JSONL"
    )
    evaluate.add_argument("--profile", default="default_it")
    evaluate.add_argument("--top-k", type=int, default=3)
    evaluate.add_argument("--out", type=Path, default=None)
    evaluate.add_argument("--title-field", default="title")
    evaluate.add_argument("--text-field", default="text")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "enrich":
        count = enrich_jsonl(
            args.input,
            args.output,
            profile=args.profile,
            debug=not args.no_debug,
            title_field=args.title_field,
            text_field=args.text_field,
        )
        print(f"enriched_documents={count}")
        print(f"output={args.output}")
        return 0

    if args.command == "eval":
        queries = load_jsonl(args.queries)
        documents = load_jsonl(args.documents)
        report = evaluate_demo_queries(
            queries,
            documents,
            profile=args.profile,
            top_k=args.top_k,
            title_field=args.title_field,
            text_field=args.text_field,
        )
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"report={args.out}")
        else:
            for row in report["rows"]:
                print(
                    f"{row['query_id']}: baseline={row['baseline_top1']} normalized={row['normalized_top1']} "
                    f"relevant={','.join(row['relevant'])} canonical={','.join(row['query_canonical_values'])}"
                )
        return 0

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
