# Zero-friction SDK examples

These examples show the lightweight `skeinrank-core` entrypoint without Docker, Elasticsearch, OpenRouter, or a governance database.

## Run the Python demo

From the repository root:

```bash
cd packages/skeinrank-core
poetry install
poetry run python ../../examples/sdk/zero_friction_demo.py
```

The demo covers:

- module-level `skeinrank.canonicalize(...)` and `skeinrank.extract(...)`;
- `SkeinRank({...})` with a simple Python dictionary;
- loading the exported demo dictionary from JSON;
- explainable matches with slots, aliases, offsets, and highlighted fragments;
- short ambiguous-company-language examples such as `pg timeout`, `pg layout`, and `pg dashboard`.

## Inspect the built-in dictionary

The built-in `platform_ops_demo` dictionary is exported here as [`platform_ops_demo.dictionary.json`](platform_ops_demo.dictionary.json) so users can inspect the shape without reading package internals.

You can also print the same dictionary through the CLI:

```bash
cd packages/skeinrank-core
poetry run skeinrank demo-dictionary --output ../../examples/sdk/platform_ops_demo.dictionary.json
```

## Try the CLI without a dictionary file

```bash
cd packages/skeinrank-core
poetry run skeinrank canonicalize "sev1 on kube after pg migration" --text
poetry run skeinrank extract "gha deploy hit rmq latency spike" --text --compact
```

When `--dictionary` is omitted, the CLI uses the same built-in `platform_ops_demo` dictionary as the Python facade.
