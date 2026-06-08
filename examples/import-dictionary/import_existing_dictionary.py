"""Import an existing synonym list and review it locally.

Run from ``packages/skeinrank-core``:

    poetry run python ../../examples/import-dictionary/import_existing_dictionary.py
"""

from __future__ import annotations

from pathlib import Path

from skeinrank import SkeinRank, import_dictionary

EXAMPLE_DIR = Path(__file__).resolve().parent
SOURCE = EXAMPLE_DIR / "es_synonyms.txt"


def main() -> None:
    result = import_dictionary(SOURCE, fmt="es-synonyms", name="platform_ops_import")
    print(result.report.to_markdown())

    draft = result.to_draft()
    print("\n--- Draft preview ---")
    print(draft.review_markdown())

    runtime_dictionary = draft.accept_all().to_dictionary()
    sr = SkeinRank(runtime_dictionary)
    print("\n--- Local preview ---")
    print(sr.canonicalize("k8s pg sev1 in gha"))


if __name__ == "__main__":
    main()
