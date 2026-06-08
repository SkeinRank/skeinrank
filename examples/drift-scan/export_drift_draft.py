"""Export alias-drift findings from the example report into a reviewable draft."""

from __future__ import annotations

import sys
from pathlib import Path

EXAMPLE_DIR = Path(__file__).resolve().parent
REPO_ROOT = EXAMPLE_DIR.parents[1]
CORE_SRC = REPO_ROOT / "packages" / "skeinrank-core"


def _ensure_core_src_on_path() -> None:
    if CORE_SRC.exists() and str(CORE_SRC) not in sys.path:
        sys.path.insert(0, str(CORE_SRC))


def main() -> None:
    _ensure_core_src_on_path()
    from skeinrank import (
        DriftScanConfig,
        drift_report_to_dictionary_draft,
        merge_binding_metadata,
        scan_dictionary_drift,
    )

    config = merge_binding_metadata(
        DriftScanConfig(discovery={"min_frequency": 2, "max_candidates": 25}),
        EXAMPLE_DIR / "binding-metadata.json",
    )
    report = scan_dictionary_drift(
        dictionary=EXAMPLE_DIR / "company.dictionary.json",
        docs=[EXAMPLE_DIR / "docs"],
        config=config,
    )
    result = drift_report_to_dictionary_draft(report)

    print(result.review_markdown())


if __name__ == "__main__":
    main()
