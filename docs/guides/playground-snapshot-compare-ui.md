# Playground snapshot compare UI

Search Playground is a focused Control Plane UI surface: a binding-aware query lab with an optional split-screen compare mode.

The page stays headless-first. It does not introduce a new backend endpoint and it does not edit dictionaries, bindings, snapshots, enrichment jobs, or runtime state.

## What it compares

The compare mode uses the existing runtime query-plan endpoint twice:

```text
POST /v1/query/plan  # Column A binding
POST /v1/query/plan  # Column B binding
```

Each column is backed by a selected Elasticsearch binding. In production this maps naturally to:

- Column A: active prod binding/snapshot.
- Column B: staging, draft, or candidate binding/snapshot.

This avoids inventing a UI-only snapshot API and keeps the playground aligned with the runtime contract that already exists.

## User workflow

1. Open **Search Playground**.
2. Enter a user query, for example `k8s pg timeout`.
3. Use **Single mode** to preview one binding or run search.
4. Use **Compare snapshots** to select Column A and Column B bindings.
5. Click **Compare snapshots** to render a split-screen query-plan comparison.

The compare result shows:

- original query;
- canonical query per column;
- selected binding/profile/index;
- snapshot version/source;
- matched aliases;
- canonical values;
- alias replacements;
- added/removed canonical values;
- newly matched aliases;
- advanced DSL/slots/replacement debug details.

## Safety

- No new backend endpoint.
- No Elasticsearch search is run by compare mode.
- No proposal apply.
- No snapshot publish.
- No enrichment job start.
- No runtime mutation.
- No `dangerouslySetInnerHTML` or unsafe highlighting.

`Run search` remains a separate explicit action and still uses the existing runtime search endpoint.
