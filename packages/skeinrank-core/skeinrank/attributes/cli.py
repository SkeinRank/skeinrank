from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .demo import enrich_jsonl, evaluate_demo_queries, load_jsonl
from .pipeline import extract_attributes
from .profiles import (
    AttributeProfileInput,
    load_attribute_profile,
    write_attribute_profile_template,
)
from .validation import ProfileValidationReport, validate_attribute_profile


def _dump_json(payload: dict[str, Any], *, pretty: bool = True) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None)


def _validation_payload(report: ProfileValidationReport) -> dict[str, Any]:
    return report.model_dump(mode="json")


def _print_validation_human(report: ProfileValidationReport) -> None:
    status = "ok" if report.ok else "failed"
    print(
        f"profile_id={report.profile_id or '-'} status={status} "
        f"errors={report.error_count} warnings={report.warning_count} "
        f"info={report.info_count}"
    )
    for issue in report.issues:
        parts = [f"[{issue.severity}]", issue.code]
        if issue.alias is not None:
            parts.append(f"alias={issue.alias}")
        if issue.canonical is not None:
            parts.append(f"canonical={issue.canonical}")
        if issue.slot is not None:
            parts.append(f"slot={issue.slot}")
        print(" ".join(parts))
        print(f"  {issue.message}")


def _attributes_payload(
    text: str,
    *,
    profile: AttributeProfileInput,
    debug: bool,
    enable_fuzzy: bool = False,
    fuzzy_threshold: float = 0.9,
    fuzzy_min_length: int = 4,
) -> dict[str, Any]:
    pack = extract_attributes(
        text,
        profile=profile,
        debug=debug,
        enable_fuzzy=enable_fuzzy,
        fuzzy_threshold=fuzzy_threshold,
        fuzzy_min_length=fuzzy_min_length,
    )
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


def _resolve_profile(profile: str, profile_file: Path | None) -> AttributeProfileInput:
    return load_attribute_profile(profile_file) if profile_file is not None else profile


def build_extract_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract normalized technical attributes from text."
    )
    parser.add_argument("--text", help="Text to process. If omitted, stdin is used.")
    parser.add_argument(
        "--profile", default="default_it", help="Built-in attribute profile name."
    )
    parser.add_argument(
        "--profile-file",
        type=Path,
        default=None,
        help="Path to a custom JSON terminology profile snapshot.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Include passport/debug trace in the output.",
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
    profile = _resolve_profile(args.profile, args.profile_file)
    payload = _attributes_payload(
        text.strip(),
        profile=profile,
        debug=args.debug,
        enable_fuzzy=args.enable_fuzzy,
        fuzzy_threshold=args.fuzzy_threshold,
        fuzzy_min_length=args.fuzzy_min_length,
    )
    print(_dump_json(payload, pretty=not args.compact))
    return 0


def build_enrich_jsonl_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Batch-enrich a JSONL corpus with SkeinRank attributes."
    )
    parser.add_argument("input", type=Path, help="Input JSONL path.")
    parser.add_argument("output", type=Path, help="Output enriched JSONL path.")
    parser.add_argument(
        "--profile", default="default_it", help="Built-in attribute profile name."
    )
    parser.add_argument(
        "--profile-file",
        type=Path,
        default=None,
        help="Path to a custom JSON terminology profile snapshot.",
    )
    parser.add_argument(
        "--no-debug",
        action="store_true",
        help="Do not include passport/debug traces in output rows.",
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
        profile=_resolve_profile(args.profile, args.profile_file),
        debug=not args.no_debug,
        title_field=args.title_field,
        text_field=args.text_field,
        enable_fuzzy=args.enable_fuzzy,
        fuzzy_threshold=args.fuzzy_threshold,
        fuzzy_min_length=args.fuzzy_min_length,
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
        "--profile", default="default_it", help="Built-in attribute profile name."
    )
    parser.add_argument(
        "--profile-file",
        type=Path,
        default=None,
        help="Path to a custom JSON terminology profile snapshot.",
    )
    parser.add_argument(
        "--enable-fuzzy",
        action="store_true",
        help="Enable conservative fuzzy alias fallback for query extraction.",
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
        profile=_resolve_profile(args.profile, args.profile_file),
        top_k=args.top_k,
        title_field=args.title_field,
        text_field=args.text_field,
        enable_fuzzy=args.enable_fuzzy,
        fuzzy_threshold=args.fuzzy_threshold,
        fuzzy_min_length=args.fuzzy_min_length,
    )
    print(_dump_json(report["summary"], pretty=not args.compact))
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"report={args.out}")
    return 0


def build_validate_profile_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a SkeinRank terminology profile snapshot."
    )
    parser.add_argument("profile_file", type=Path, help="Profile JSON snapshot path.")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON validation report.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Elevate governance warnings to errors and return a non-zero exit "
            "code when the profile is not strict-publishable."
        ),
    )
    parser.add_argument(
        "--min-short-alias-length",
        type=int,
        default=3,
        help="Aliases shorter than this length are reported as short. Default: 3.",
    )
    return parser


def validate_profile_main(argv: list[str] | None = None) -> int:
    args = build_validate_profile_parser().parse_args(argv)
    report = validate_attribute_profile(
        args.profile_file,
        strict=args.strict,
        min_short_alias_length=args.min_short_alias_length,
    )
    if args.json:
        print(_dump_json(_validation_payload(report), pretty=True))
    else:
        _print_validation_human(report)
    if report.error_count:
        return 1
    return 0


def build_init_profile_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a starter SkeinRank terminology profile JSON file."
    )
    parser.add_argument("output", type=Path, help="Output profile JSON path.")
    parser.add_argument(
        "--profile-id",
        default=None,
        help="Profile id to write. Defaults to the output filename stem.",
    )
    parser.add_argument(
        "--snapshot-version",
        default=None,
        help="Snapshot version to write. Defaults to '<profile_id>@v1'.",
    )
    parser.add_argument(
        "--description",
        default=None,
        help="Profile description to include in the generated file.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the output file if it already exists.",
    )
    return parser


def init_profile_main(argv: list[str] | None = None) -> int:
    parser = build_init_profile_parser()
    args = parser.parse_args(argv)
    try:
        output = write_attribute_profile_template(
            args.output,
            profile_id=args.profile_id,
            description=args.description,
            snapshot_version=args.snapshot_version,
            overwrite=args.overwrite,
        )
    except FileExistsError as exc:
        parser.error(str(exc))

    profile = load_attribute_profile(output)
    snapshot = profile.get("snapshot") or {}
    print(f"created_profile={output}")
    print(f"profile_id={profile.get('profile_id')}")
    print(f"snapshot_version={snapshot.get('version')}")
    return 0
