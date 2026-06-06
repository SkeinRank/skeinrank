# Model provider abstraction

The OpenRouter alias scout uses a small model-provider interface instead of
hard-wiring the workflow to one concrete client. The default hosted adapter is
OpenRouter, while tests and offline planning use deterministic providers. The
same interface also supports private company endpoints through the local
endpoint adapter.

## Goals

- Keep the governed alias-scout workflow provider-agnostic.
- Preserve existing OpenRouter behavior and report fields for compatibility.
- Let operators inspect provider configuration without network calls.
- Keep live model calls behind explicit CLI flags.
- Avoid printing secret values in plans or reports.

## Implementation location

```text
examples/agents/openrouter_alias_scout/model_provider.py
```

Offline CLI preview:

```bash
python examples/agents/openrouter_alias_scout/run_alias_scout.py \
  --print-model-provider-plan
```

The plan returns:

```text
skeinrank.model_provider_plan.v1
```

It does not call a model provider and does not include secret values.

## Provider interface

A provider implements an OpenAI-compatible method:

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

The production hosted adapter is:

```text
OpenRouterChatProvider
```

It wraps the dependency-light `OpenRouterClient`, so existing live pilot behavior
remains unchanged.

The deterministic test/offline adapter is:

```text
MockChatProvider
```

It returns OpenAI-compatible responses without making network calls.

## Configuration

Default config shape:

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

Supported provider types:

```text
openrouter
mock
local_endpoint
```

Use [`model-provider-adapters.md`](model-provider-adapters.md) for adapter-specific
configuration and [`company-model-integration.md`](company-model-integration.md)
for private model endpoint rollout.

## Safety model

- The provider plan command is offline.
- Tests use `MockChatProvider` or local test transports.
- Live model calls require explicit live flags such as `--llm-review` or the live
  pilot commands.
- Secret values are not printed in provider plans.
- Proposal approval, apply, and snapshot publication are handled by the
  Governance API workflow, not by the model provider layer.

## Why this matters

Companies often start with a hosted model provider and later move some review
traffic to a private model endpoint. The provider interface keeps that migration
inside the same governed workflow:

```text
candidate evidence -> model provider -> structured judgment -> validation -> review
```
