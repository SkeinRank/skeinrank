# SkeinRank product positioning

SkeinRank is an open-source **Terminology Control Plane** for enterprise search, RAG, and AI-agent workflows.

It turns noisy domain language such as `k8s`, `pg`, `phoenix`, service nicknames, incident shorthand, and team-specific abbreviations into governed runtime context that can be reviewed, versioned, snapshotted, and safely delivered to search systems.

## One-line value proposition

> Govern company terminology once, then serve the same canonical context to Elasticsearch, RAG pipelines, local agents, and review workflows without turning the UI into a direct production editor.

## Who it is for

| Persona | What they need from SkeinRank |
| --- | --- |
| Search / platform engineers | A deterministic normalization layer before Elasticsearch, OpenSearch, vector retrieval, or hybrid search. |
| ML / RAG engineers | Cleaner input context before embedding, reranking, or LLM answer generation. |
| Knowledge managers / reviewers | A small AI Inbox for reviewing proposed terminology changes with evidence and risk. |
| SRE / platform teams | Read-only support, backup, alerting, and demo-smoke commands that do not mutate production state by surprise. |
| Security / enterprise architects | A control-plane/data-plane boundary where customer indexes can stay inside the customer environment. |

## Product shape

SkeinRank intentionally separates **control** from **serving**:

```text
Control Plane
  Profiles, proposals, evidence, risk policy, snapshots, UI review, audit

Data Plane / Runtime
  Immutable snapshot, fast canonicalization, local enrichment workers, search/RAG integration
```

The UI is not the primary way to edit production terminology. The focused Control Plane UI is for:

1. **Playground** — debug how a query is canonicalized and compare runtime contexts.
2. **AI Inbox** — review evidence-backed proposals from agents and discovery workflows.
3. **Schema & Snapshots** — inspect profiles, bindings, canonical aliases, and snapshot state.

Legacy write tools are locked down by default. Production changes should go through:

```text
proposal -> validation -> risk policy -> human review -> snapshot / GitOps rollout
```

## What SkeinRank is not

SkeinRank is not trying to replace Elasticsearch, OpenSearch, Qdrant, pgvector, or an internal RAG stack. It is the terminology governance and canonicalization layer that sits before or beside those systems.

It is also not a direct production CRUD console. Manual write paths exist only for local development and debugging when explicitly enabled.

## Demo path

The local product tour demonstrates the complete story:

```bash
make demo-tour
```

For an already seeded local stack, use the read-oriented smoke check:

```bash
make demo-tour-smoke
make demo-tour-show
```

The smoke report is written to:

```text
examples/platform_ops_demo/reports/platform_ops_demo_tour_report.json
```

The walkthrough covers:

```text
Playground -> AI Inbox -> Schema & Snapshots -> locked Developer Cockpit
```

## Safety posture

The current repository focuses on a controlled pilot / public beta posture:

- no auto-apply from agents;
- agents submit proposals instead of mutating dictionaries directly;
- role boundaries separate agent, reviewer, and admin responsibilities;
- legacy UI writes are locked by default;
- support bundles and alert reports are redacted/read-only;
- backup/restore and demo-smoke flows are explicit commands;
- enrichment is treated as an operator-controlled workflow, not a casual UI click.

## Public beta readiness checklist

Before public promotion, the repository should keep these items easy to find:

- `README.md` with a clear value proposition and demo commands;
- `docs/product-positioning.md` for the product narrative;
- `docs/guides/seeded-demo-walkthrough.md` and `docs/guides/demo-product-tour.md` for screenshots/demo prep;
- `CONTRIBUTING.md` for setup and contribution expectations;
- `SECURITY.md` for private vulnerability disclosure;
- `CODE_OF_CONDUCT.md` for community expectations;
- GitHub issue templates for bugs and feature requests;
- CI that runs backend tests, UI tests, typechecks, and builds.
