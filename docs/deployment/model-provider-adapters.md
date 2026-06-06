# Model provider adapters

The alias scout supports three provider modes:

```text
openrouter
local_endpoint
mock
```

`openrouter` remains the default hosted adapter. `local_endpoint` targets a
self-hosted OpenAI-compatible `/chat/completions` endpoint, such as a vLLM, LM
Studio, Ollama-compatible gateway, or company-hosted model proxy. `mock` is for
deterministic tests and offline examples.

## Preview provider configuration

Preview the configured provider without network calls:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --print-model-provider-plan
```

The output uses:

```text
skeinrank.model_provider_plan.v1
```

The command does not call any model provider and does not print secret values.

## OpenRouter adapter

Default config:

```json
{
  "model_provider": {
    "provider_type": "openrouter",
    "provider_name": "openrouter",
    "model": "openai/gpt-4o-mini",
    "api_key_env": "OPENROUTER_API_KEY",
    "base_url": "https://openrouter.ai/api/v1",
    "require_api_key": true
  }
}
```

Live calls still require explicit live flags such as `--llm-review` or the live
pilot commands. The provider plan command remains offline.

## Local endpoint adapter

Example config:

```json
{
  "model_provider": {
    "provider_type": "local_endpoint",
    "provider_name": "local-vllm",
    "model": "local-model",
    "api_key_env": "SKEINRANK_LOCAL_MODEL_API_KEY",
    "base_url": "http://127.0.0.1:8000/v1",
    "require_api_key": false
  }
}
```

Equivalent environment override:

```bash
export SKEINRANK_MODEL_PROVIDER_TYPE=local_endpoint
export SKEINRANK_MODEL_PROVIDER_BASE_URL=http://127.0.0.1:8000/v1
export SKEINRANK_MODEL_PROVIDER_MODEL=local-model
```

Then preview:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --print-model-provider-plan
```

For endpoints that require a token:

```bash
export SKEINRANK_LOCAL_MODEL_API_KEY=...
```

and set `require_api_key` to `true` in config.

## Safety model

- Tests use mock providers or local transports and do not call external providers.
- Provider plans do not make network calls.
- Secret values are redacted from plan output.
- Local endpoint calls only happen behind the same explicit live model flags as
  the OpenRouter path.
- Proposal apply, snapshot publishing, and runtime mutation stay in the
  Governance API workflow.

## Compatibility

OpenRouter report fields remain for backward compatibility. Report metadata also
includes `model_provider` entries so operators can see whether a run used
OpenRouter, a local endpoint, or the mock provider.

## Company integration

Use [`company-model-integration.md`](company-model-integration.md) when connecting
a private model server to the alias scout. It documents the offline integration
plan, the one-call smoke path, and the validated pilot sequence for
`local_endpoint` providers.
