# OpenRouter alias scout agent example

The OpenRouter alias scout example is a safe reference path for agent-assisted
terminology discovery. It keeps the production invariant simple:

```text
LLM / agent -> proposal -> validation -> review/policy -> snapshot -> runtime
```

Patch 40F introduced the dependency-light runner foundation. Patch 40G added
OpenRouter/OpenAI-compatible tool schemas and safety prompts. Patch 40H added
failed-query candidate discovery and pruning. Patch 40I added compact evidence
windows. Patch 40K adds the local E2E demo report.

## Run the local demo

From the repository root:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --run-demo-report
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-demo-review-prompt
```

Or use the Makefile helper:

```bash
make agent-demo
```

The demo report schema is `skeinrank.agent_demo_report.v1`. It is intentionally
local-only: no OpenRouter calls, no Elasticsearch calls, no SkeinRank API calls,
and no proposals are submitted.

## What the report contains

The report joins these local stages:

```text
failed queries -> candidate discovery -> evidence windows -> candidate packs -> review queue
```

It includes:

- discovered alias-like surfaces such as `pg`, `k8s`, and `kube`;
- compact evidence windows with explicit character and document limits;
- idempotency keys for future proposal retries;
- `source_quality` placeholders for future accepted/rejected proposal metrics;
- safety metadata that blocks direct dictionary writes, direct Git pushes, and
  snapshot publishing.

## What it does not do yet

Patch 40K does not call OpenRouter and does not submit proposals. Later patches
can consume the review queue, call a model, validate `propose` judgments through
`/v1/tools/validate-alias`, and submit pending proposals through
`/v1/tools/suggest-alias`. Runtime snapshot publishing remains part of the
reviewed governance workflow, not the agent runner.

### Patch 40J — OpenRouter execution / LangGraph-ready workflow

Patch 40J adds the first live OpenRouter execution path for the alias scout. Use
`--print-llm-review-plan` to preview the LangGraph-ready state-machine workflow
without network calls, then set `OPENROUTER_API_KEY` and run `--llm-review` to
call OpenRouter `/chat/completions` for strict `propose`, `reject`, or
`needs_evidence` judgments. The output schema is
`skeinrank.agent_llm_review_report.v1`. Proposal submission remains disabled by
default, so the workflow prepares proposal payloads but does not mutate SkeinRank
state.

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py --print-llm-review-plan
OPENROUTER_API_KEY=... python examples/agents/openrouter_alias_scout/run_alias_scout.py --llm-review --model openai/gpt-4o-mini --max-candidates 3
```
