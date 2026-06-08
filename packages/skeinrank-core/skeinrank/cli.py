"""Local CLI for dictionary-driven SkeinRank extraction.

This CLI is intentionally lightweight and uses only the public SDK/document
helpers. It does not require the governance API, Elasticsearch, Celery, or a DB.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, TextIO

from .documents import (
    DocumentExtractionError,
    extract_document_text,
    extract_terms_from_document,
)
from .facade import demo_dictionary, demo_dictionary_payload
from .importing import import_dictionary
from .sdk import canonicalize_text, extract_terms, load_dictionary, validate_dictionary

_DEFAULT_CONTEXT_CHARS = 48


def main(argv: list[str] | None = None) -> int:
    """Run the local SkeinRank CLI and return a process exit code."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except KeyboardInterrupt:  # pragma: no cover - process-level behavior.
        _print_error("Interrupted")
        return 130
    except (OSError, ValueError, DocumentExtractionError) as exc:
        _print_error(str(exc))
        return 1


def entrypoint() -> None:
    """Console-script entrypoint."""

    raise SystemExit(main())


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skeinrank",
        description=(
            "Validate dictionaries, extract canonical terms, and canonicalize "
            "local text/documents with the lightweight SkeinRank SDK."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser(
        "validate-dictionary",
        help="Validate a SkeinRank dictionary JSON/YAML file.",
    )
    validate_parser.add_argument("dictionary", help="Path to dictionary JSON/YAML.")
    validate_parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full validation report as JSON.",
    )
    validate_parser.add_argument(
        "--strict",
        action="store_true",
        help="Return a non-zero exit code when warnings are present.",
    )
    validate_parser.set_defaults(handler=_handle_validate_dictionary)

    extract_parser = subparsers.add_parser(
        "extract",
        help="Extract dictionary matches from local text or a supported document.",
    )
    _add_source_arguments(extract_parser)
    _add_dictionary_argument(extract_parser)
    _add_json_output_arguments(extract_parser)
    extract_parser.add_argument(
        "--max-matches",
        type=int,
        default=None,
        help="Maximum number of matches to return.",
    )
    extract_parser.add_argument(
        "--context-chars",
        type=int,
        default=_DEFAULT_CONTEXT_CHARS,
        help="Characters to include around each evidence fragment.",
    )
    extract_parser.set_defaults(handler=_handle_extract)

    canonicalize_parser = subparsers.add_parser(
        "canonicalize",
        help="Replace matched aliases/canonical values with canonical values.",
    )
    _add_source_arguments(canonicalize_parser)
    _add_dictionary_argument(canonicalize_parser)
    canonicalize_parser.add_argument(
        "--json",
        action="store_true",
        help="Print canonicalized text and replacement metadata as JSON.",
    )
    canonicalize_parser.add_argument(
        "--output",
        help="Write output to this file instead of stdout.",
    )
    canonicalize_parser.add_argument(
        "--compact",
        action="store_true",
        help="Write compact JSON when --json is used.",
    )
    canonicalize_parser.add_argument(
        "--max-matches",
        type=int,
        default=None,
        help="Maximum number of replacements to apply.",
    )
    canonicalize_parser.add_argument(
        "--context-chars",
        type=int,
        default=_DEFAULT_CONTEXT_CHARS,
        help="Characters to include around each replacement evidence fragment.",
    )
    canonicalize_parser.set_defaults(handler=_handle_canonicalize)

    demo_dictionary_parser = subparsers.add_parser(
        "demo-dictionary",
        help="Print the built-in platform-ops demo dictionary as JSON.",
    )
    demo_dictionary_parser.add_argument(
        "--output",
        help="Write the dictionary JSON to this file instead of stdout.",
    )
    demo_dictionary_parser.add_argument(
        "--compact",
        action="store_true",
        help="Write compact JSON instead of pretty-printed JSON.",
    )
    demo_dictionary_parser.set_defaults(handler=_handle_demo_dictionary)

    import_dictionary_parser = subparsers.add_parser(
        "import-dictionary",
        help=(
            "Convert an existing JSON, CSV, or Elasticsearch/OpenSearch synonym "
            "list into a SkeinRank dictionary candidate."
        ),
    )
    import_dictionary_parser.add_argument(
        "source",
        help="Path to the JSON/CSV/synonym-list file to import.",
    )
    import_dictionary_parser.add_argument(
        "--out",
        help="Write the imported SkeinRank dictionary JSON to this file.",
    )
    import_dictionary_parser.add_argument(
        "--format",
        choices=["json", "csv", "es-synonyms"],
        default=None,
        help="Override format detection.",
    )
    import_dictionary_parser.add_argument(
        "--name",
        default="imported",
        help="Profile name to use in the imported dictionary.",
    )
    import_dictionary_parser.add_argument(
        "--report",
        help="Write the markdown import report to this file.",
    )
    import_dictionary_parser.add_argument(
        "--json-report",
        action="store_true",
        help="Print the import report as JSON instead of markdown.",
    )
    import_dictionary_parser.add_argument(
        "--compact",
        action="store_true",
        help="Write compact JSON when --json-report is used.",
    )
    import_dictionary_parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip the dictionary validator bridge pass.",
    )
    import_dictionary_parser.add_argument(
        "--strict-validate",
        action="store_true",
        help="Treat validator errors as fatal import findings.",
    )
    import_dictionary_parser.set_defaults(handler=_handle_import_dictionary)

    document_text_parser = subparsers.add_parser(
        "document-text",
        help="Extract plain text from a supported local document.",
    )
    document_text_parser.add_argument("source", help="Path to the source document.")
    document_text_parser.add_argument(
        "--json",
        action="store_true",
        help="Print document text metadata and content as JSON.",
    )
    document_text_parser.add_argument(
        "--output",
        help="Write output to this file instead of stdout.",
    )
    document_text_parser.add_argument(
        "--compact",
        action="store_true",
        help="Write compact JSON when --json is used.",
    )
    document_text_parser.set_defaults(handler=_handle_document_text)

    return parser


def _add_source_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "source",
        help=(
            "Document path by default. Use --text to treat this argument as raw "
            "input text."
        ),
    )
    parser.add_argument(
        "--text",
        action="store_true",
        help="Treat SOURCE as raw text instead of a document path.",
    )


def _add_dictionary_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--dictionary",
        default=None,
        help=(
            "Path to SkeinRank dictionary JSON/YAML. "
            "Omit to use the built-in platform-ops demo dictionary."
        ),
    )


def _add_json_output_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--output",
        help="Write JSON output to this file instead of stdout.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Write compact JSON instead of pretty-printed JSON.",
    )


def _handle_validate_dictionary(args: argparse.Namespace) -> int:
    report = validate_dictionary(args.dictionary)
    if args.json:
        _write_json(report.model_dump(mode="json"), output_path=None, compact=False)
    else:
        _print_validation_report(report)
    if report.error_count:
        return 1
    if args.strict and report.warning_count:
        return 1
    return 0


def _load_runtime_dictionary(source: str | None):
    if source:
        return load_dictionary(source)
    return demo_dictionary()


def _handle_extract(args: argparse.Namespace) -> int:
    dictionary = _load_runtime_dictionary(args.dictionary)
    if args.text:
        result = extract_terms(
            args.source,
            dictionary=dictionary,
            max_matches=args.max_matches,
            context_chars=args.context_chars,
        )
        payload: dict[str, Any] = result.model_dump(mode="json")
    else:
        result = extract_terms_from_document(
            args.source,
            dictionary=dictionary,
            max_matches=args.max_matches,
            context_chars=args.context_chars,
        )
        payload = result.model_dump(mode="json")
    _write_json(payload, output_path=args.output, compact=args.compact)
    return 0


def _handle_canonicalize(args: argparse.Namespace) -> int:
    dictionary = _load_runtime_dictionary(args.dictionary)
    source_text = args.source if args.text else extract_document_text(args.source).text
    result = canonicalize_text(
        source_text,
        dictionary=dictionary,
        max_matches=args.max_matches,
        context_chars=args.context_chars,
    )
    if args.json:
        _write_json(
            result.model_dump(mode="json"),
            output_path=args.output,
            compact=args.compact,
        )
    else:
        _write_text(result.text, output_path=args.output)
    return 0


def _handle_demo_dictionary(args: argparse.Namespace) -> int:
    _write_json(
        demo_dictionary_payload(),
        output_path=args.output,
        compact=args.compact,
    )
    return 0


def _handle_import_dictionary(args: argparse.Namespace) -> int:
    result = import_dictionary(
        args.source,
        fmt=args.format,
        name=args.name,
        run_validator=not args.no_validate,
        strict_validator=args.strict_validate,
    )
    if args.json_report:
        _write_json(
            result.report.to_dict(),
            output_path=args.report,
            compact=args.compact,
        )
    else:
        _write_text(result.report.to_markdown(), output_path=args.report)

    if not result.report.is_ok:
        return 1
    if args.out:
        result.save(args.out)
        print(f"Wrote {args.out}")
    return 0


def _handle_document_text(args: argparse.Namespace) -> int:
    document = extract_document_text(args.source)
    if args.json:
        _write_json(
            document.model_dump(mode="json"),
            output_path=args.output,
            compact=args.compact,
        )
    else:
        _write_text(document.text, output_path=args.output)
    return 0


def _write_json(
    payload: MappingLike,
    *,
    output_path: str | None,
    compact: bool,
) -> None:
    if compact:
        rendered = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    else:
        rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    _write_text(rendered, output_path=output_path)


MappingLike = dict[str, Any]


def _write_text(value: str, *, output_path: str | None) -> None:
    if output_path:
        Path(output_path).write_text(value, encoding="utf-8")
        return
    print(value)


def _print_validation_report(report: Any, *, stream: TextIO | None = None) -> None:
    if stream is None:
        stream = sys.stdout
    status = "valid" if report.ok else "invalid"
    print(f"Dictionary: {report.profile_name or '<unknown>'}", file=stream)
    print(f"Status: {status}", file=stream)
    print(f"Errors: {report.error_count}", file=stream)
    print(f"Warnings: {report.warning_count}", file=stream)
    if not report.issues:
        return
    print("Issues:", file=stream)
    for issue in report.issues:
        location = f" [{issue.value}]" if issue.value else ""
        print(
            f"- {issue.severity}: {issue.code}{location}: {issue.message}",
            file=stream,
        )


def _print_error(message: str) -> None:
    print(f"skeinrank: {message}", file=sys.stderr)


if __name__ == "__main__":  # pragma: no cover - manual execution path.
    entrypoint()
