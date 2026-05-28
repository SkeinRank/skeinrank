# Company model integration

Patch 57C adds a company-model integration plan for the alias scout.

The goal is to help a company connect an internal model endpoint without guessing
which commands are safe to run. The integration plan is offline: it does not call
OpenRouter, the local model endpoint, Elasticsearch, or the Governance API.

## Supported provider modes

The operator-facing provider modes remain intentionally small:

```text
openrouter
local_endpoint
mock
```

For company-owned models, use `local_endpoint`. The endpoint should expose an
OpenAI-compatible `/chat/completions` API shape. This covers private gateways
around vLLM, LM Studio, Ollama-compatible servers, or a company-hosted model
proxy.

## Print the integration plan

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --print-company-model-integration-plan
```

The output schema is:

```text
skeinrank.company_model_integration_plan.v1
```

The command is safe for CI and local checks:

- no network calls;
- no provider calls;
- no Governance API calls;
- no secret values printed;
- no proposal submission;
- no runtime mutation.

## Configure a local company endpoint

```bash
export SKEINRANK_MODEL_PROVIDER_TYPE=local_endpoint
export SKEINRANK_MODEL_PROVIDER_BASE_URL=http://127.0.0.1:8000/v1
export SKEINRANK_MODEL_PROVIDER_MODEL=company-model
```

If the company endpoint requires a token:

```bash
read -s SKEINRANK_LOCAL_MODEL_API_KEY
export SKEINRANK_LOCAL_MODEL_API_KEY
```

The provider plan still redacts the value.

## Preview provider config

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --print-model-provider-plan
```

Expected fields for a local endpoint:

```json
{
  "provider": {
    "provider_type": "local_endpoint",
    "base_url": "http://127.0.0.1:8000/v1",
    "requires_api_key": false
  },
  "safety": {
    "network_calls": false,
    "secrets_included": false
  }
}
```

## One-call smoke

After the local endpoint is actually running, use the existing live pilot command
with very small limits:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --run-openrouter-live-pilot \
  --write-openrouter-live-pilot-report \
  examples/agents/openrouter_alias_scout/reports/live-pilot/company-model-provider-smoke-report.json \
  --max-candidates 1 \
  --max-llm-calls 1 \
  --max-run-cost-usd 0.01
```

The flag name still contains `openrouter` for backward compatibility. When
`SKEINRANK_MODEL_PROVIDER_TYPE=local_endpoint` is set, the runner uses the local
endpoint provider.

Check the report for:

```text
model_provider.provider_type == local_endpoint
provider_calls == true
proposal_submission_enabled == false
proposals_submitted == 0
```

## Validated pilot

Before a validated pilot, seed or select a real SkeinRank profile/binding. Then
run:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --write-openrouter-validated-pilot-report \
  examples/agents/openrouter_alias_scout/reports/live-pilot/company-model-provider-validated-report.json \
  --profile-name <profile-name> \
  --max-candidates 1 \
  --max-llm-calls 1 \
  --max-proposals 1 \
  --max-run-cost-usd 0.01
```

Review:

```text
validation_passed
validation_warning
validation_blocked
```

## Troubleshooting

Common problems:

| Symptom | Likely cause | Check |
|---|---|---|
| provider plan says `openrouter` | env override not exported in the current shell | `echo $SKEINRANK_MODEL_PROVIDER_TYPE` |
| local endpoint call fails | model server is not running or base URL is wrong | confirm `/v1/chat/completions` route on the server |
| validated pilot fails before provider call | profile/binding not seeded | run the benchmark/pilot seed flow or pass existing `--profile-name` / `--binding-id` |
| output is not JSON | model endpoint ignored JSON response format | lower temperature, improve endpoint prompt policy, or use a stronger model |

## Safety

Patch 57C does not add auto-apply. Company model runs still prepare proposal
payloads only. Governance validation, reviewer approval, admin apply, and
snapshot publishing stay separate.
