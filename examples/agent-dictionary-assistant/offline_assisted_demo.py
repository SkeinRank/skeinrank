"""Run the assistant contract without calling OpenRouter.

Run from ``packages/skeinrank-core``:

    poetry run python ../../examples/agent-dictionary-assistant/offline_assisted_demo.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from skeinrank import SkeinRank, build_dictionary_from_docs

EXAMPLE_DIR = Path(__file__).resolve().parent
DOCS = EXAMPLE_DIR / "docs"


def fake_openrouter_transport(
    payload: Mapping[str, Any],
    config: Any,
) -> Mapping[str, Any]:
    """Return a deterministic assistant response for local demos and tests."""

    request = json.loads(payload["messages"][1]["content"])
    available = {item["canonical_value"] for item in request["candidates"]}
    candidates = []
    if "KubeletOOM" in available:
        candidates.append(
            {
                "canonical_value": "kubelet out of memory",
                "aliases": ["KubeletOOM"],
                "slot": "INCIDENT_SIGNAL",
                "confidence": 0.91,
                "source_values": ["KubeletOOM"],
            }
        )
    if "EdgeGateway" in available:
        candidates.append(
            {
                "canonical_value": "edge gateway",
                "aliases": ["EdgeGateway"],
                "slot": "SERVICE",
                "confidence": 0.88,
                "source_values": ["EdgeGateway"],
            }
        )

    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps({"candidates": candidates}),
                }
            }
        ]
    }


def main() -> None:
    result = build_dictionary_from_docs(
        [DOCS],
        model="offline/demo-model",
        config={
            "profile_name": "platform_assisted_terms",
            "min_frequency": 2,
            "max_candidates": 8,
        },
        transport=fake_openrouter_transport,
    )
    print(result.review_markdown())

    runtime_dictionary = result.draft.accept_all().to_dictionary()
    sr = SkeinRank(runtime_dictionary)
    print("\n--- Local preview ---")
    print(sr.canonicalize("KubeletOOM on EdgeGateway"))


if __name__ == "__main__":
    main()
