# Model provider abstraction

Patch 57A introduces the first model-provider seam for the OpenRouter alias scout.

The goal is not to replace OpenRouter yet. The goal is to stop hard-wiring the
agent workflow to one concrete client class. The workflow now accepts a minimal
chat-completion provider interface while preserving the existing OpenRouter
adapter and report fields for backward compatibility.

## What changed

New file:

```text
examples/agents/openrouter_alias_scout/model_provider.py
```

New offline CLI preview:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --print-model-provider-plan
```

The plan returns schema:

```text
skeinrank.model_provider_plan.v1
```

It does not call a model provider and does not include secret values.

## Provider interface

A provider only needs to implement an OpenAI-compatible method:

```python
create_chat_completion(
    *,
    model,
    messages,
    temperature=0.0,
    max_tokens=700,
    tools=None,
    response_format=None,
)
```

The current production adapter is:

```text
OpenRouterChatProvider
```

It wraps the existing dependency-light `OpenRouterClient`, so existing live pilot
behavior remains unchanged.

The test/offline adapter is:

```text
MockChatProvider
```

It returns deterministic OpenAI-compatible responses and is used by tests instead
of making network calls.

## Configuration

The alias scout example config now includes a provider block:

```json
{
  "model_provider": {
    "provider_type": "openrouter",
    "provider_name": "openrouter",
    "model": "openai/gpt-4o-mini",
    "api_key_env": "OPENROUTER_API_KEY",
    "base_url": "https://openrouter.ai/api/v1"
  }
}
```

For Patch 57A, supported runtime provider types are:

```text
openrouter
openai-compatible
mock
```

`openai-compatible` currently uses the same OpenAI-compatible adapter surface as
OpenRouter. Dedicated OpenAI-compatible and local endpoint adapters can be added
in the next patch without changing the alias-scout workflow.

## Safety

Patch 57A is intentionally behavior-preserving:

- no OpenRouter calls are made by the provider plan command;
- tests use `MockChatProvider` and do not call external providers;
- existing `--llm-review` / live pilot commands keep the same explicit live flags;
- secret values are not printed in provider plans;
- proposal approval/apply and snapshot publishing are unchanged.

## Why this matters

This prepares SkeinRank for company environments where OpenRouter may not be the
final provider. Later adapters can target an OpenAI-compatible endpoint or a local
model server while keeping the same governed agent workflow:

```text
candidate evidence → model provider → structured judgment → validation → review
```
