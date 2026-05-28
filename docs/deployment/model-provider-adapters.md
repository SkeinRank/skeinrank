# Model provider adapters

Patch 57B adds concrete model-provider adapters for the alias scout workflow.

The production-facing provider modes are intentionally small:

```text
openrouter
local_endpoint
mock
```

`openrouter` remains the default hosted adapter. `local_endpoint` is for a
self-hosted OpenAI-compatible `/chat/completions` endpoint, for example a vLLM,
LM Studio, or Ollama-compatible gateway. The user-facing provider name is local
endpoint because the expected company use case is a local or private endpoint,
not a generic OpenAI-compatible SaaS provider.

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

## Safety

Patch 57B does not change proposal apply, snapshot publishing, or runtime
mutation behavior.

- Tests use mock/local transports and do not call external providers.
- Provider plans do not make network calls.
- Secret values are not printed.
- Local endpoint calls only happen behind the same explicit live model flags as
  the existing OpenRouter path.

## Compatibility

OpenRouter report fields remain for backward compatibility. New report metadata
also includes `model_provider` entries so operators can see whether a run used
OpenRouter, a local endpoint, or the mock provider.
