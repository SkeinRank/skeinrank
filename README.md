# SkeinRank

SkeinRank is an **attribute extraction and normalization engine** for semi-structured technical documents, incident notes, and log fragments.

It focuses on a pragmatic workflow:

- extract technical attributes from noisy text
- canonicalize aliases such as `k8s -> kubernetes` and `asp.net -> dotnet`
- load versioned terminology snapshots from file-based profiles
- use an in-memory Aho-Corasick matcher for fast alias lookup with simple fallback
- expose an explainable `passport` trace for debug and review
- serve the pipeline through a small FastAPI endpoint
- batch-enrich a document corpus and run a tiny demo evaluation

## What problem it solves

Internal technical knowledge is rarely clean. Teams search across wiki pages, incident summaries, pasted stack traces, and troubleshooting notes where the same concept appears under different names.

SkeinRank helps normalize that mess into reusable attributes that can later power search, retrieval, and reranking systems.

## Repository layout

- `packages/skeinrank-core` — core library and attribute extraction pipeline
- `packages/skeinrank-server` — FastAPI service wrapper
- `packages/skeinrank-provider-elasticsearch` — optional Elasticsearch retrieval provider and enrichment CLI
- `packages/skeinrank-governance` — SQLAlchemy/Alembic foundation and admin CLI for Postgres terminology governance
- `packages/skeinrank-governance-api` — FastAPI control-plane API for profiles, terms, aliases, and future governance UI
- `packages/skeinrank-ui` — React/TypeScript governance console for terms, aliases, and snapshots
- `examples/demo/` — small demo corpus, demo queries, and usage notes

## Quickstart

### CLI commands

After installing the package you can use the small command-line tools directly:

```bash
skeinrank-extract --text "kube api timeout" --debug
skeinrank-enrich-jsonl examples/demo/demo_documents.jsonl examples/demo/demo_enriched_documents.jsonl
skeinrank-eval-demo examples/demo/demo_queries.jsonl examples/demo/demo_enriched_documents.jsonl
skeinrank-server --reload
skeinrank-es-enrich --help
```

### 1) Core tests

```bash
cd packages/skeinrank-core
poetry install
poetry run pytest -q
```

### 2) Start the FastAPI server

```bash
cd ../skeinrank-server
poetry install
poetry run skeinrank-server --reload
```

### 3) Extract attributes with curl

```bash
curl -s http://127.0.0.1:8000/v1/attributes/extract \
  -H "Content-Type: application/json" \
  -d '{
    "text": "k8s timeout on production api-server version 1.28",
    "profile": "default_it",
    "debug": true
  }'
```

Example result shape:

```json
{
  "profile": "default_it",
  "attributes": [
    {"slot": "TOOL", "value": "kubernetes", "source": "alias"},
    {"slot": "VERSION", "value": "1.28", "source": "regex"},
    {"slot": "COMPONENT", "value": "api-server", "source": "regex"},
    {"slot": "ERROR", "value": "timeout", "source": "regex"}
  ],
  "passport": {
    "snapshot": {"version": "default_it@2026-04-29-v1", "source": "file"},
    "alias_matcher_backend": "aho_corasick",
    "accepted": [...],
    "filtered_out": [...],
    "warnings": []
  }
}
```


## Development hygiene

This repository uses Ruff and pre-commit for lightweight linting and formatting.

Install local developer tools from the repository root:

```bash
python -m pip install -r requirements-dev.txt
pre-commit install
```

Run the same checks manually:

```bash
ruff check \
  packages/skeinrank-core/skeinrank packages/skeinrank-core/tests \
  packages/skeinrank-server/skeinrank_server packages/skeinrank-server/tests \
  packages/skeinrank-provider-elasticsearch/skeinrank_provider_elasticsearch packages/skeinrank-provider-elasticsearch/tests \
  packages/skeinrank-governance/skeinrank_governance packages/skeinrank-governance/tests \
  packages/skeinrank-governance-api/skeinrank_governance_api packages/skeinrank-governance-api/tests

ruff format --check \
  packages/skeinrank-core/skeinrank packages/skeinrank-core/tests \
  packages/skeinrank-server/skeinrank_server packages/skeinrank-server/tests \
  packages/skeinrank-provider-elasticsearch/skeinrank_provider_elasticsearch packages/skeinrank-provider-elasticsearch/tests \
  packages/skeinrank-governance/skeinrank_governance packages/skeinrank-governance/tests \
  packages/skeinrank-governance-api/skeinrank_governance_api packages/skeinrank-governance-api/tests
```

GitHub Actions runs Ruff once at the repository level, runs package tests through Poetry for each Python package, and runs UI typecheck/tests/build for `packages/skeinrank-ui`.

## Governance API preview

The governance API package is the HTTP control-plane layer that will later power the SkeinRank UI. It uses `skeinrank-governance` as the database/model layer and keeps runtime extraction snapshot-based.

```bash
cd packages/skeinrank-governance-api
poetry install
poetry run skeinrank-governance-api --reload
```

Health check:

```bash
curl http://127.0.0.1:8010/healthz
```

The API reads `SKEINRANK_GOVERNANCE_DATABASE_URL` or `SKEINRANK_GOVERNANCE_API_DATABASE_URL`. For local demos only, set `SKEINRANK_GOVERNANCE_API_CREATE_TABLES=true`; production deployments should use Alembic migrations from `packages/skeinrank-governance`.


## Governance UI preview

The UI package is the first frontend for the SkeinRank governance console. It uses React, TypeScript, Vite, shadcn-style local components, TanStack Query, and TanStack Table.

Start the governance API first:

```bash
cd packages/skeinrank-governance-api
export SKEINRANK_GOVERNANCE_API_CREATE_TABLES=true
poetry run skeinrank-governance-api --reload
```

Then start the UI:

```bash
cd packages/skeinrank-ui
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

Current UI scope:

- app shell
- profile CRUD controls: create, select, rename, describe, and delete profiles
- terms table with row selection
- create, edit, and delete canonical terms
- term details panel with lifecycle status controls
- create, edit, and delete aliases with manual confidence hidden
- aliases display
- draft snapshot export and JSON download panel
- API state management through TanStack Query
- light/dark/system theme toggle with local persistence

Authentication, suggestions approval, publish/rollback, Elasticsearch bindings, and realtime collaboration are intentionally left for follow-up patches.

## Bring your own terminology

You can use a built-in profile such as `default_it`, generate a starter profile, or pass a custom JSON snapshot without editing SkeinRank source code.

Create a starter profile:

```bash
skeinrank-init-profile company_terms.json
skeinrank-validate-profile company_terms.json
```

Python API:

```python
from skeinrank import build_attribute_profile, extract_attributes

profile = build_attribute_profile(
    profile_id="company_terms",
    aliases={
        "kubernetes": ["k8s", "kube", "kuber"],
        "postgresql": ["pg", "postgres", "psql"],
    },
    slots={
        "kubernetes": "TOOL",
        "postgresql": "DB",
    },
    snapshot_version="company_terms@v1",
)

pack = extract_attributes("kuber timeout on pg", profile=profile)
```

CLI with a custom profile file:

```bash
skeinrank-extract --text "kuber timeout on pg" --profile-file ./company_terms.json
skeinrank-enrich-jsonl docs.jsonl enriched.jsonl --profile-file ./company_terms.json
skeinrank-es-enrich --index docs --text-field body --profile-file ./company_terms.json --dry-run
```

Validate a profile before using it in enrichment jobs:

```bash
skeinrank-validate-profile ./company_terms.json
skeinrank-validate-profile ./company_terms.json --json
skeinrank-validate-profile ./company_terms.json --strict
# Optional: customize short-alias warning threshold
skeinrank-validate-profile ./company_terms.json --min-short-alias-length 4
```

The validator reports collisions such as one alias pointing to multiple canonical terms, warns about generic or short aliases such as `api`, `service`, or `pg`, and understands governance statuses such as `active`, `deprecated`, `pending`, `ambiguous`, `disabled`, and `rejected`. In `--strict` mode, governance warnings are elevated to errors so the command can be used as a snapshot publishing gate in CI.

### Optional fuzzy alias fallback

Exact alias matching remains the default. If you want to catch typo-like terms, enable conservative fuzzy fallback explicitly:

```bash
skeinrank-extract \
  --text "kubernets timeout on postgress" \
  --profile-file ./company_terms.json \
  --enable-fuzzy \
  --fuzzy-threshold 0.88
```

Fuzzy matching is disabled by default, ignores short aliases such as `pg`, and is reported as `fuzzy_alias` in attributes/passport output.

## Demo flow

The repository includes a tiny demo corpus under `examples/demo/`:

- `demo_documents.jsonl`
- `demo_queries.jsonl`

### Batch-enrich demo documents

```bash
cd packages/skeinrank-core
poetry run skeinrank-enrich-jsonl \
  ../../examples/demo/demo_documents.jsonl \
  ../../examples/demo/demo_enriched_documents.jsonl
```

The enriched JSONL contains:

- original document fields
- `original_text`
- `extracted_attributes`
- `canonical_values`
- `snapshot`
- `alias_matcher_backend`
- `passport`

### Run a tiny baseline vs normalized evaluation

```bash
cd packages/skeinrank-core
poetry run skeinrank-eval-demo \
  ../../examples/demo/demo_queries.jsonl \
  ../../examples/demo/demo_enriched_documents.jsonl \
  --out ../../examples/demo/demo_eval_results.json
```

This produces a small report with:

- baseline top-1 / top-k results
- normalized top-1 / top-k results
- per-query canonical values
- summary metrics such as top-1 hits and MRR

On the bundled toy demo, a few alias-heavy queries are designed so the normalized path visibly beats the lexical baseline (`0.8` vs `1.0` top-1 accuracy in the generated report).

## Rule and alias configuration

The default attribute profile is file-based and lives under:

```text
packages/skeinrank-core/skeinrank/attributes/config/default_it.json
```

That profile currently controls:

- alias canonicalization
- snapshot metadata
- Aho-Corasick alias matcher backend
- regex/rule extraction
- slot-level and total limits
- stopwords
- rule-based runtime settings

## Governance package preview

`packages/skeinrank-governance` is the first platform-foundation package. It contains SQLAlchemy models, Alembic migrations, and the `skeinrank-admin` CLI for a future Postgres-backed terminology control plane.

`packages/skeinrank-governance-api` is the first HTTP layer for that control plane. It currently exposes configuration, database session wiring, `/healthz`, CRUD REST endpoints for profiles, canonical terms, aliases, and runtime-compatible snapshot export. Future patches will add UI controls for update/delete flows, snapshot publishing lifecycle, suggestions, approval flow, and authentication.

The intended architecture is:

```text
Postgres governance store -> governance API/UI -> published snapshot JSON -> runtime matcher -> API / CLI / Elasticsearch enrichment
```

The hot extraction path still uses exported snapshots; it does not query Postgres or the governance API per request.

Local smoke tests:

```bash
cd packages/skeinrank-governance
poetry install
poetry run pytest -q
poetry run alembic upgrade head

cd ../skeinrank-governance-api
poetry install
poetry run pytest -q
poetry run skeinrank-governance-api --reload
```

Export a runtime-compatible snapshot through the API:

```bash
curl -X POST http://127.0.0.1:8010/v1/governance/profiles/default_it/snapshot/export \
  -H "Content-Type: application/json" \
  -d '{"snapshot_version":"default_it@v1"}'
```

The initial schema includes profiles, canonical terms, aliases, profile snapshots, and audit events.

## Notes and current limitations

- The default demo path is intentionally **rules-first** and explainable.
- Experimental model adapters are kept out of the default passport; the current MVP presents the rules-first runtime by default.
- The `/v1/attributes/extract` endpoint works without Elasticsearch.
- `/healthz` may still show `degraded` when Elasticsearch is not configured because the server also exposes an optional rerank route.

## Roadmap

- richer demo corpus and examples
- safer production-style reindex/alias orchestration examples for Elasticsearch/OpenSearch
- offline enrichment for larger corpora
- stronger retrieval / rerank harness
- optional backend integrations for real search stores
- optional model-backed extraction stages when they prove useful on real corpora

## Elasticsearch enrichment

The provider package can enrich an existing Elasticsearch index. The command is intentionally explicit: users provide the index, one or more source text fields, and the target field that receives SkeinRank attributes. The default payload is compact for production indexes; add `--include-matched-aliases` when you need a compact alias trace, and add `--include-evidence` only when you need full debug evidence. Start with `--dry-run`; use `--write` only when the preview is correct.

```bash
cd packages/skeinrank-provider-elasticsearch
poetry run skeinrank-es-enrich \
  --url http://localhost:9200 \
  --index docs \
  --text-field title \
  --text-field body \
  --target-field skeinrank \
  --profile default_it \
  --limit 10 \
  --dry-run
```

Dry-run does not modify the Elasticsearch index. Write mode uses bulk partial updates and only adds/replaces the configured `--target-field`. By default the target field stores `profile_id`, `snapshot_version`, `alias_matcher_backend`, `canonical_values`, and slot-grouped values. Compact alias traces are opt-in via `--include-matched-aliases`; full attributes/evidences are opt-in via `--include-evidence`.

### Optional matched aliases mode

Use `--include-matched-aliases` when you want to keep a compact trace of the surface forms that produced canonical values, without storing full evidence payloads:

```bash
skeinrank-es-enrich \
  --url http://localhost:9200 \
  --index docs \
  --text-field title \
  --text-field body \
  --target-field skeinrank \
  --include-matched-aliases \
  --dry-run
```

This adds `matched_aliases` and `matched_aliases_by_value` to the compact Elasticsearch payload.

### Elasticsearch write mode

```bash
cd packages/skeinrank-provider-elasticsearch
poetry run skeinrank-es-enrich \
  --url http://localhost:9200 \
  --index docs \
  --text-field title \
  --text-field body \
  --target-field skeinrank \
  --limit 100 \
  --batch-size 25 \
  --write
```

For safety, the CLI requires either `--dry-run` or `--write`; it never writes by default.
