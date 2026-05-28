# OpenRouter live agent pilot mode

Patch 48B adds a guarded live pilot mode for the reference OpenRouter alias scout.
It is the live counterpart to the deterministic 48A headless benchmark.

The pilot is intentionally opt-in:

- it requires `OPENROUTER_API_KEY` in your local environment;
- it uses hard limits for candidates, LLM calls, proposals, and run cost;
- it does not approve/apply proposals;
- it does not publish snapshots;
- it does not mutate runtime state;
- SkeinRank proposal validation/submission is disabled unless explicitly requested.

## Environment

Do not commit a real OpenRouter key. Export it in your shell or keep it in a local
ignored `.env` file:

```bash
export OPENROUTER_API_KEY="sk-or-..."
export OPENROUTER_MODEL="openai/gpt-4o-mini"
```

The default env var name is configured in
`examples/agents/openrouter_alias_scout/agent_config.example.json`:

```json
{
  "openrouter_api_key_env": "OPENROUTER_API_KEY"
}
```

## Offline plan

Use this first. It prints the live run plan without network calls:

```bash
make agent-openrouter-pilot-plan
```

Or directly:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --print-openrouter-live-pilot-plan \
  --max-candidates 1 \
  --max-llm-calls 1
```

## Live OpenRouter run

This calls OpenRouter and writes a report under the ignored `reports/` folder:

```bash
OPENROUTER_API_KEY="sk-or-..." make agent-openrouter-pilot-report
```

Direct command:

```bash
OPENROUTER_API_KEY="sk-or-..." \
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --run-openrouter-live-pilot \
  --write-openrouter-live-pilot-report \
  examples/agents/openrouter_alias_scout/reports/live-pilot/openrouter-live-pilot-report.json \
  --max-candidates 1 \
  --max-llm-calls 1 \
  --max-run-cost-usd 0.01
```

The command prints a short operator summary to stdout and writes the full report to disk.
The report schema is:

```text
skeinrank.openrouter_live_pilot_report.v1
```

Expected useful fields:

```text
summary.candidates_sent_to_model
summary.proposals_prepared
summary.eligible_proposals
summary.live_openrouter_calls
summary.estimated_cost_usd
safety.agent_may_mutate_runtime = false
```

## Optional SkeinRank validation

Once the Governance API is running, the pilot can validate ready proposals through
`/v1/tools/validate-alias`. The validation target preflights `/livez` before any
OpenRouter call, so a stopped API fails fast without spending model budget:

```bash
OPENROUTER_API_KEY="sk-or-..." \
SKEINRANK_AGENT_API_TOKEN="..." \
make agent-openrouter-pilot-validate
```

When auth is enabled, the token needs the scope required by the tools API, such
as `agent:tools:validate`. Validation does not approve/apply proposals and does
not publish snapshots.

## Optional proposal submission

Proposal submission is intentionally not exposed through a Makefile target. It
can be tested manually with an explicit CLI flag:

```bash
OPENROUTER_API_KEY="sk-or-..." \
SKEINRANK_AGENT_API_TOKEN="..." \
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --run-openrouter-live-pilot \
  --pilot-validate-proposals \
  --pilot-submit-proposals \
  --max-candidates 1 \
  --max-llm-calls 1 \
  --max-proposals 1
```

This creates pending suggestions only when the agent security profile and scoped
credentials allow it. It still does not approve/apply proposals and does not
publish snapshots.

## Relationship to 48A

- 48A proves the headless workflow deterministically without external services.
- 48B checks whether a real OpenRouter model can produce useful, contract-safe
  proposal payloads under explicit cost and mutation guardrails.

## Benchmark-style live aliases

Patch 48B.2 adds Makefile aliases so the live pilot sits next to the offline and
containerized benchmark commands:

```bash
make benchmark-agent-live-plan
make benchmark-agent-live-check
make benchmark-agent-live
make benchmark-agent-live-validate
make benchmark-agent-live-full
```

These are wrappers around the lower-level `agent-openrouter-pilot-*` commands.
`benchmark-agent-live` performs a guarded OpenRouter call and writes a report.
`benchmark-agent-live-validate` also requires the Governance API to be running so
that proposed aliases can be validated through SkeinRank before the report is
written. Neither command approves/applies proposals or publishes snapshots.

## 49D validated pilot flow

Patch 49D makes the live validation path explicit. It is still safe by default:
OpenRouter may prepare proposal payloads, SkeinRank validates those payloads, but
no pending suggestions are submitted unless `--pilot-submit-proposals` is passed
manually.

Plan the validated pilot without network calls:

```bash
make benchmark-agent-live-validated-pilot-plan
```

Run it against an already running Governance API:

```bash
OPENROUTER_API_KEY="sk-or-..." \
make benchmark-agent-live-validated-pilot-report
```

Run it after starting and seeding the isolated benchmark stack:

```bash
make benchmark-stack-down
make benchmark-stack-prune-containers
OPENROUTER_API_KEY="sk-or-..." \
make benchmark-agent-live-validated-pilot-stack
```

The stack target bootstraps a temporary benchmark-stack admin login token and
passes it to the agent as `SKEINRANK_AGENT_API_TOKEN`, so validation checks run
against the authenticated Governance API before any optional proposal submission.


The default validation target is the benchmark profile:

```text
OPENROUTER_VALIDATED_PILOT_PROFILE=platform_ops_benchmark
```

The generated report keeps the existing live-pilot schema and adds:

```text
validated_pilot.schema_version = skeinrank.openrouter_validated_pilot.v1
validated_pilot.mode = validate_only
validated_pilot.metrics.validation_coverage
validated_pilot.metrics.validation_pass_rate
validated_pilot.quality_gates[]
validated_pilot.safety.runtime_mutation_enabled = false
```

Use CLI overrides when testing another profile or binding:

```bash
OPENROUTER_API_KEY="sk-or-..." \
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-openrouter-validated-pilot-report \
  examples/agents/openrouter_alias_scout/reports/live-pilot/openrouter-validated-pilot-report.json \
  --profile-name platform_ops_benchmark \
  --max-candidates 2 \
  --max-llm-calls 1 \
  --max-proposals 2
```

## Auth preflight

The validated pilot preflight checks authenticated tools before spending
OpenRouter budget. It verifies `/livez`, `GET /v1/tools/bindings`, and the
read-only `POST /v1/tools/validate-alias` tool with a synthetic validation
payload. If the selected profile or binding context is missing, the CLI fails
before calling OpenRouter and tells the operator to seed the benchmark stack or
pass an existing `--profile-name` / `--binding-id`. If the Governance API is
running with auth enabled and no valid `SKEINRANK_AGENT_API_TOKEN` is provided,
the CLI also fails before calling OpenRouter.
