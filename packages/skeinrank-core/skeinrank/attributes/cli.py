from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .demo import enrich_jsonl, evaluate_demo_queries, load_jsonl
from .pipeline import extract_attributes


def _dump_json(payload: dict[str, Any], *, pretty: bool = True) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None)


def _attributes_payload(text: str, *, profile: str, debug: bool) -> dict[str, Any]:
    pack = extract_attributes(text, profile=profile, debug=debug)
    attributes = [item.model_dump(mode="json") for item in pack.attributes]
    canonical_values = sorted({item["value"] for item in attributes})
    slots: dict[str, list[str]] = {}
    for item in attributes:
        slots.setdefault(item["slot"], [])
        if item["value"] not in slots[item["slot"]]:
            slots[item["slot"]].append(item["value"])

    payload: dict[str, Any] = {
        "profile_id": pack.profile_id,
        "snapshot_version": pack.snapshot.version
        if pack.snapshot is not None
        else None,
        "alias_matcher_backend": pack.alias_matcher_backend,
        "canonical_values": canonical_values,
        "slots": {slot: sorted(values) for slot, values in sorted(slots.items())},
        "attributes": attributes,
    }
    if debug and pack.passport is not None:
        passport = pack.passport.model_dump(mode="json")
        if not passport.get("stage_status"):
            passport.pop("stage_status", None)
        payload["passport"] = passport
    return payload


def build_extract_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract normalized technical attributes from text."
    )
    parser.add_argument("--text", help="Text to process. If omitted, stdin is used.")
    parser.add_argument(
        "--profile", default="default_it", help="Attribute profile name."
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Include passport/debug trace in the output.",
    )
    parser.add_argument(
        "--compact", action="store_true", help="Print compact one-line JSON."
    )
    return parser


def extract_main(argv: list[str] | None = None) -> int:
    parser = build_extract_parser()
    args = parser.parse_args(argv)
    text = args.text if args.text is not None else sys.stdin.read()
    if not text or not text.strip():
        parser.error("Provide --text or pipe text to stdin.")
    payload = _attributes_payload(text.strip(), profile=args.profile, debug=args.debug)
    print(_dump_json(payload, pretty=not args.compact))
    return 0


def build_enrich_jsonl_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Batch-enrich a JSONL corpus with SkeinRank attributes."
    )
    parser.add_argument("input", type=Path, help="Input JSONL path.")
    parser.add_argument("output", type=Path, help="Output enriched JSONL path.")
    parser.add_argument(
        "--profile", default="default_it", help="Attribute profile name."
    )
    parser.add_argument(
        "--no-debug",
        action="store_true",
        help="Do not include passport/debug traces in output rows.",
    )
    parser.add_argument(
        "--title-field", default="title", help="Document title field name."
    )
    parser.add_argument(
        "--text-field", default="text", help="Document body/text field name."
    )
    return parser


def enrich_jsonl_main(argv: list[str] | None = None) -> int:
    args = build_enrich_jsonl_parser().parse_args(argv)
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


def build_eval_demo_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run baseline vs normalized evaluation over demo JSONL files."
    )
    parser.add_argument("queries", type=Path, help="Queries JSONL path.")
    parser.add_argument("documents", type=Path, help="Enriched documents JSONL path.")
    parser.add_argument(
        "--profile", default="default_it", help="Attribute profile name."
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Number of ranked items to include per query.",
    )
    parser.add_argument(
        "--out", type=Path, default=None, help="Optional path for full JSON report."
    )
    parser.add_argument(
        "--title-field", default="title", help="Document title field name."
    )
    parser.add_argument(
        "--text-field", default="text", help="Document body/text field name."
    )
    parser.add_argument(
        "--compact", action="store_true", help="Print compact one-line summary JSON."
    )
    return parser


def eval_demo_main(argv: list[str] | None = None) -> int:
    args = build_eval_demo_parser().parse_args(argv)
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
    print(_dump_json(report["summary"], pretty=not args.compact))
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"report={args.out}")
    return 0
