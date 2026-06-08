"""Suggest a reviewable dictionary draft from local documents.

Run from ``packages/skeinrank-core``:

    poetry run python ../../examples/suggest-dictionary/suggest_from_docs.py
"""

from __future__ import annotations

from pathlib import Path

from skeinrank import SkeinRank, suggest_dictionary_from_documents

EXAMPLE_DIR = Path(__file__).resolve().parent
DOCS = EXAMPLE_DIR / "docs"


def main() -> None:
    result = suggest_dictionary_from_documents(
        [DOCS],
        config={
            "profile_name": "platform_candidates",
            "discovery": {"min_frequency": 2, "max_candidates": 8},
        },
    )
    print(result.review_markdown())

    print("\n--- Review boundary ---")
    print("Suggested candidates stay proposed until a reviewer accepts them.")
    try:
        runtime_dictionary = result.draft.accept_all().to_dictionary()
    except ValueError as exc:
        print(f"Local preview skipped: {exc}")
        return

    sr = SkeinRank(runtime_dictionary)
    print("\n--- Local preview ---")
    print(sr.extract("KubeletOOM returned on EdgeGateway"))


if __name__ == "__main__":
    main()
