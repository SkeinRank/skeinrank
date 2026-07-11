"""Zero-friction SkeinRank SDK demo.

Run from the repository root with:

    cd packages/skeinrank-core
    poetry run python ../../examples/sdk/zero_friction_demo.py

The demo intentionally avoids Docker, OpenRouter, Elasticsearch, and the
Governance API. It only exercises the lightweight core SDK facade.
"""

from __future__ import annotations

from pathlib import Path

import skeinrank
from skeinrank import SkeinRank

EXAMPLES_DIR = Path(__file__).resolve().parent
DEMO_DICTIONARY_PATH = EXAMPLES_DIR / "platform_ops_demo.dictionary.json"


def main() -> None:
    print("module canonicalize:")
    print(skeinrank.canonicalize("sev1 on kube after pg migration"))

    print("\nmodule extract:")
    print(skeinrank.extract("gha rollout hit rmq latency spike"))

    print("\ncontext-shaped aliases:")
    print("pg timeout  ->", skeinrank.canonicalize("pg timeout"))
    print("pg layout   ->", skeinrank.canonicalize("pg layout"))
    print("pg dashboard ->", skeinrank.canonicalize("pg dashboard"))

    print("\ninline dictionary:")
    sr = SkeinRank(
        {
            "kubernetes": ["k8s", "kube"],
            "postgresql": ["pg", "postgres", "psql"],
        }
    )
    print(sr.canonicalize("kube timeout on pg"))

    print("\nfrom exported demo dictionary:")
    exported = SkeinRank.from_file(DEMO_DICTIONARY_PATH)
    explained = exported.extract(
        "api-server timed out after db migration", explain=True
    )
    print(explained.canonical_values)
    for match in explained.matches:
        print(f"- {match.slot}: {match.alias} -> {match.canonical_value}")


if __name__ == "__main__":
    main()
