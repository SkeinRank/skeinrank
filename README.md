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
- `packages/skeinrank-governance-api` — FastAPI control-plane API for profiles, terms, aliases, stop lists, suggestions/approval, auth/users/roles, and future governance workflows
- `packages/skeinrank-ui` — React/TypeScript governance console for terms, aliases, suggestions, guardrails, users, roles, and snapshots
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

The API reads `SKEINRANK_GOVERNANCE_API_DATABASE_URL` first and falls back to `SKEINRANK_GOVERNANCE_DATABASE_URL`. Before running the service in a production-like setup, upgrade the governance schema with Alembic:

```bash
poetry run python -m skeinrank_governance_api.migrations upgrade head
```

For local demos/tests only, set `SKEINRANK_GOVERNANCE_API_CREATE_TABLES=true` to create tables at startup.

Patch 23 adds the suggestions/approval workflow: contributors and future discovery jobs can create pending alias suggestions or propose new canonical terms, while moderators/admins can approve or reject them. Approved alias suggestions create active aliases; approved canonical term suggestions create active canonical terms; rejected suggestions remain as review history.


## Governance UI preview

The UI package is the first frontend for the SkeinRank governance console. It uses React, TypeScript, Vite, shadcn-style local components, TanStack Query, and TanStack Table.

Start the governance API first. For a production-like local run, apply migrations before starting the API:

```bash
cd packages/skeinrank-governance-api
poetry run python -m skeinrank_governance_api.migrations upgrade head
poetry run skeinrank-governance-api --reload
```

Optional local auth bootstrap for protected API testing:

```bash
export SKEINRANK_GOVERNANCE_API_AUTH_ENABLED=true
export SKEINRANK_GOVERNANCE_API_BOOTSTRAP_ADMIN=true
export SKEINRANK_GOVERNANCE_API_ADMIN_USERNAME=admin
export SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD='change-me'
```


For a quick throwaway demo database, you can still use:

```bash
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

- app shell with local login/logout session controls
- current user and role display in the top bar
- admin-only Users page for local user CRUD and role assignment
- role-aware controls for Admin, Moderator, and Contributor users
- Suggestions page for creating, filtering, approving, and rejecting alias/canonical term proposals
- searchable canonical term picker in manual suggestions with auto-filled slot and existing alias checks
- Guardrails page for profile-scoped stop-list management
- Integrations page for manual Elasticsearch binding configs with shared-index validation
- profile CRUD controls: create, select, rename, describe, and delete profiles
- terms table with row selection
- create, edit, and delete canonical terms
- term details panel with lifecycle status controls
- create, edit, and delete aliases with manual confidence hidden
- manual alias status choices limited to `active`, `deprecated`, and `disabled`; review-only statuses stay reserved for future suggestions and validation flags
- aliases display
- draft snapshot export and JSON download panel
- API state management through TanStack Query
- light/dark/system theme toggle with local persistence

The API and UI now include the suggestions/approval workflow and manual Elasticsearch binding configuration. Contributors can propose aliases without mutating active terminology, while moderators/admins can approve or reject suggestions. Manual alias suggestions use a searchable canonical term picker, auto-fill the canonical slot, show existing aliases, keep reviewers on the current queue filter after approve/reject, and submit `source = manual` with `confidence = 1.0` internally. The UI also supports canonical term suggestions so contributors can propose new canonical terms for moderator/admin review and approval into active terms. The Integrations page lets admins/moderators save profile-to-index binding configs with text fields, target field, document discriminator field/value, dry-run/write mode, and enabled state. When multiple profiles share the same index, the UI requires a document discriminator so enrichment does not mix documents across profiles. Publish/rollback, Elasticsearch write jobs, model-based discovery, and realtime collaboration are intentionally left for follow-up patches.

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

`packages/skeinrank-governance-api` is the HTTP layer for that control plane. It exposes configuration, database session wiring, `/healthz`, CRUD REST endpoints for profiles, canonical terms, aliases, stop lists, suggestions/approval, Elasticsearch binding configs, runtime-compatible snapshot export, local auth, users, and role-aware API permissions. Future patches will add snapshot publishing lifecycle, Elasticsearch write/reindex jobs, and model-based discovery ingestion.

The intended architecture is:

```text
Postgres governance store -> governance API/UI -> published snapshot JSON -> runtime matcher -> API / CLI / Elasticsearch enrichment
```

The hot extraction path still uses exported snapshots; it does not query Postgres or the governance API per request.

Elasticsearch binding configs now describe where a profile should be applied later: index/index pattern, source text fields, target enrichment field, optional document discriminator, dry-run/write mode, and enabled state. The UI can manage these configs manually through the Integrations page and validates the shared-index case: if multiple profiles point to the same index, a discriminator such as `team = infra` is required. They can now be tested with read-only connection/mapping discovery and binding dry-runs. Follow-up patches will add production write/reindex jobs.

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

The initial schema includes profiles, canonical terms, aliases, profile snapshots, suggestions, stop-list guardrails, users, and audit events.

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

### Patch 25d — Elasticsearch connection and mapping discovery

The governance API can now use an optional Elasticsearch connection for discovery-only workflows. Configure it with environment variables:

```bash
export SKEINRANK_ELASTICSEARCH_URL=http://localhost:9200
# optional:
export SKEINRANK_ELASTICSEARCH_USERNAME=elastic
export SKEINRANK_ELASTICSEARCH_PASSWORD=...
# or:
export SKEINRANK_ELASTICSEARCH_API_KEY=...
```

The discovery endpoints are read-only and do not run enrichment or write to Elasticsearch:

```text
GET /v1/governance/elasticsearch/connection/status
GET /v1/governance/elasticsearch/indices
GET /v1/governance/elasticsearch/indices/{index_name}/mapping
```

The Integrations UI keeps manual binding configuration as a fallback, but when Elasticsearch is configured it can show connection status, discovered indices, and mapping field suggestions for text fields and document discriminator fields.

### Patch 25e — Elasticsearch binding dry-run

The governance API can run a read-only dry-run for a saved Elasticsearch binding. Dry-run reads a small sample of documents from the configured index, extracts text from the binding `text_fields`, matches active aliases from the selected terminology profile, and returns the payload that would be written to the binding `target_field`.

```text
POST /v1/governance/elasticsearch/bindings/{binding_id}/dry-run
```

Example request:

```json
{"limit": 3}
```

Dry-run never writes to Elasticsearch. It is intended to validate profile/index/text-field/discriminator configuration before any future write strategy or reindex/alias-swap job is introduced.
### Patch 25g — reindex + alias swap jobs

Patch 25g adds the backend job contract for Elasticsearch enrichment writes. A
binding can now start a synchronous MVP enrichment job through:

```bash
POST /v1/governance/elasticsearch/bindings/{binding_id}/jobs
```

The job record stores status, write strategy, source index, target index, alias
name, counters, result JSON, and error message. The default production-oriented
write strategy is `reindex_alias_swap`; `in_place` remains available for
sandbox/dev use cases.

This patch intentionally does not add Celery/RabbitMQ yet. The API executes the
MVP job inline and records a durable job row so a future worker implementation
can reuse the same contract.

