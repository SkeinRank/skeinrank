# Agent dictionary assistant

These examples show the optional assistant flow for cold-start dictionary creation. The assistant is not the runtime path. SkeinRank first discovers deterministic, evidence-backed candidates from local documents; OpenRouter can then group and name those candidates into a reviewable draft.

The output is still a `DictionaryDraft`. Reviewers decide what becomes a runtime dictionary.

## Deterministic first

Use the local suggestion command before adding a model provider:

```bash
cd packages/skeinrank-core

poetry run skeinrank suggest-dictionary ../../examples/agent-dictionary-assistant/docs \
  --profile-name platform_candidates \
  --min-frequency 2 \
  --out ../../examples/agent-dictionary-assistant/platform_candidates.dictionary-draft.json \
  --review ../../examples/agent-dictionary-assistant/platform_candidates.review.md
```

## OpenRouter-assisted grouping

```bash
export OPENROUTER_API_KEY="..."
export OPENROUTER_MODEL="provider/model"

poetry run skeinrank assist-dictionary ../../examples/agent-dictionary-assistant/docs \
  --model "$OPENROUTER_MODEL" \
  --profile-name platform_assisted_terms \
  --out ../../examples/agent-dictionary-assistant/platform_assisted.dictionary-draft.json \
  --review ../../examples/agent-dictionary-assistant/platform_assisted.review.md
```

The assistant receives candidate summaries and evidence snippets, not production credentials or runtime state. Aliases that do not match deterministic evidence are dropped.

## Offline assistant demo

```bash
cd packages/skeinrank-core
poetry run python ../../examples/agent-dictionary-assistant/offline_assisted_demo.py
```

The offline demo uses a fake transport and makes no network request. It demonstrates the same evidence-bound contract that the OpenRouter transport uses.

## Review before runtime

```python
from skeinrank import DictionaryDraft, SkeinRank

draft = DictionaryDraft.from_file("platform_assisted.dictionary-draft.json")
runtime_dictionary = draft.accept_all().to_dictionary()
sr = SkeinRank(runtime_dictionary)

print(sr.canonicalize("KubeletOOM on EdgeGateway"))
```

Use `accept_all()` only for local preview or controlled demos. Production flows should review individual candidates, publish an immutable snapshot, and roll that snapshot out through a binding.
