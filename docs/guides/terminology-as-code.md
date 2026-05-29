# Terminology-as-Code export/import workflow

Patch 60A documents the safe file-based workflow for moving terminology between
Git, the Governance API, PostgreSQL, and runtime snapshot artifacts.

SkeinRank uses a simple rule:

```text
YAML outside, JSON inside.
```

- Humans and CI jobs may keep dictionaries as YAML or JSON in Git.
- HTTP APIs receive and return JSON payloads.
- PostgreSQL is the control-plane source of truth for changing state.
- Runtime workers consume immutable binding-scoped snapshot artifacts instead of
  reading PostgreSQL on every search request.

The current stable dictionary contract is `skeinrank.dictionary.v1`; the portable
runtime artifact contract is `skeinrank.runtime_snapshot_artifact.v1`.

## What lives where

| Layer | Artifact | Owner | Notes |
| --- | --- | --- | --- |
| Git repository | `*.dictionary.yaml` or `*.dictionary.json` | humans, agents, CI | Human-reviewable Terminology-as-Code input. YAML is best for comments and pull-request diffs; JSON is the canonical API shape. |
| Governance API | JSON request/response | CI, services, agents | `POST /v1/headless/dictionaries/validate` and `POST /v1/headless/dictionaries/apply` validate and apply dictionary spec v1 payloads. |
| PostgreSQL | profiles, terms, aliases, stop lists, bindings, snapshots | SkeinRank Control Plane | Stores the current governed state, audit metadata, and binding runtime pointers. |
| Runtime artifact | `skeinrank.runtime_snapshot_artifact.v1` JSON | GitOps delivery, headless workers | Immutable read model built for one binding. It includes binding context, compiled aliases, snapshot metadata, and a checksum. |

## Import path: Git -> validate -> apply

Start with a dictionary file in Git. See
[`examples/terminology-as-code/platform_ops.dictionary.yaml`](../../examples/terminology-as-code/platform_ops.dictionary.yaml)
and
[`examples/terminology-as-code/platform_ops.dictionary.json`](../../examples/terminology-as-code/platform_ops.dictionary.json).

Validate the file before writing any state:

```bash
cd packages/skeinrank-governance-api
poetry run skeinrank-migrate validate \
  ../../examples/terminology-as-code/platform_ops.dictionary.yaml
```

Apply the same file after review and validation:

```bash
cd packages/skeinrank-governance-api
poetry run skeinrank-migrate apply \
  ../../examples/terminology-as-code/platform_ops.dictionary.yaml
```

For direct headless API automation, send JSON to the automation-first facade:

```bash
curl -s -X POST "http://127.0.0.1:8010/v1/headless/dictionaries/validate" \
  -H "Content-Type: application/json" \
  -H "X-SkeinRank-Role: admin" \
  -d @examples/terminology-as-code/platform_ops.dictionary.json

curl -s -X POST "http://127.0.0.1:8010/v1/headless/dictionaries/apply" \
  -H "Content-Type: application/json" \
  -H "X-SkeinRank-Role: admin" \
  -d @examples/terminology-as-code/platform_ops.dictionary.json
```

`validate` is read-only. `apply` validates first and writes profile, term, alias,
profile stop-list, and global stop-list changes in one transaction.

## Export path: Control Plane -> Git

Export the current profile dictionary as JSON:

```bash
cd packages/skeinrank-governance-api
poetry run skeinrank-migrate export \
  --profile-name platform_ops \
  --output ../../examples/terminology-as-code/platform_ops.exported.dictionary.json
```

The same shape is available through the headless API:

```bash
curl -s \
  "http://127.0.0.1:8010/v1/headless/dictionaries/export?profile_name=platform_ops" \
  -H "X-SkeinRank-Role: admin" \
  > examples/terminology-as-code/platform_ops.exported.dictionary.json
```

Exported dictionaries include `schema_version: skeinrank.dictionary.v1`, so CI
jobs, bots, and reviewers can detect the expected contract. If your GitOps
repository prefers YAML, convert the exported JSON in your own pipeline before
opening a pull request; SkeinRank keeps JSON as the canonical API shape.

## Runtime artifact path: binding -> immutable snapshot JSON

A dictionary describes terminology. A binding describes where and how a profile is
served at runtime: index or alias, text fields, target field, write strategy,
filters, and the pinned runtime snapshot.

After a binding exists, export a portable runtime artifact:

```bash
cd packages/skeinrank-governance-api
poetry run skeinrank-migrate snapshot-export \
  --binding-id 1 \
  --source latest \
  --snapshot-version platform_ops@v1 \
  --output ../../snapshots/platform_ops.binding-1.v1.json
```

Inspect the artifact locally without contacting the API:

```bash
cd packages/skeinrank-governance-api
poetry run skeinrank-migrate snapshot-inspect \
  ../../snapshots/platform_ops.binding-1.v1.json
```

Compare two artifact files when you need a local before/after canonicalization
report:

```bash
cd packages/skeinrank-governance-api
poetry run skeinrank-migrate snapshot-eval \
  --before ../../snapshots/platform_ops.binding-1.v1.json \
  --after ../../snapshots/platform_ops.binding-1.v2.json
```

The HTTP equivalent is:

```text
GET /v1/headless/snapshots/export?binding_id=1&source=latest&snapshot_version=platform_ops%40v1
```

Use `source=latest` to build from the current profile state. Use `source=runtime`
to export the binding-pinned runtime snapshot; that path returns `409` when the
binding has not published a runtime snapshot yet.

## Recommended CI shape

After 60B, prefer an explicit lint/plan/apply sequence:

```text
pull request changes dictionary file
  -> skeinrank-migrate lint
  -> skeinrank-migrate plan --output plan.json
  -> human review / policy checks
  -> skeinrank-migrate apply --plan-output applied-plan.json
  -> skeinrank-migrate export
  -> skeinrank-migrate snapshot-export
  -> commit/export artifact to the delivery repository or object storage
```

SkeinRank is the manager of terminology state. GitLab CI, Jenkins, ArgoCD, Flux,
or another GitOps tool should deliver the approved file or runtime artifact to
serving workers. SkeinRank should not pretend to replace CI/CD.

Patch 60B adds [`dictionary-cli-planning.md`](dictionary-cli-planning.md) with
local `lint`, server-backed `plan`, and `apply --plan-output` guidance. Use
`validate`, `export`, `snapshot-export`, `snapshot-inspect`, and `snapshot-eval`
for the rest of the existing flow.

## Safety guarantees in this workflow

- Agents and CI jobs can validate dictionaries without writing state.
- Runtime workers can load immutable artifacts and avoid direct PostgreSQL access.
- Bindings let different search contexts pin different snapshot versions.
- Git remains the audit trail for delivered files.
- Rollback is operationally simple: revert the delivered dictionary or artifact
  commit, then reload the worker configuration through your existing delivery
  tooling.
