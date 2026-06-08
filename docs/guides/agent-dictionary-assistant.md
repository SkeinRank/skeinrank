# Agent dictionary assistant

The agent dictionary assistant helps with cold-start terminology onboarding. It is designed for teams that do not yet have a clean SkeinRank dictionary, or that want to improve a draft created from local documents.

The runtime path remains deterministic. Models are used only before review, while building a local dictionary draft from evidence-backed candidates.

## Two modes

| Mode | Command | Requires model token | Use when |
| --- | --- | --- | --- |
| Deterministic suggestions | `skeinrank suggest-dictionary` | No | You want a local draft from documents. |
| OpenRouter-assisted grouping | `skeinrank assist-dictionary` | Yes | You want a model to group and name deterministic candidates. |

Both modes return a reviewable `DictionaryDraft`. Neither mode creates a production dictionary automatically.

## Deterministic suggestions

Use this first when there is no dictionary yet:

```bash
cd packages/skeinrank-core

poetry run skeinrank suggest-dictionary ../../examples/suggest-dictionary/docs \
  --profile-name platform_candidates \
  --min-frequency 2 \
  --out ../../examples/suggest-dictionary/platform_candidates.dictionary-draft.json \
  --review ../../examples/suggest-dictionary/platform_candidates.review.md
```

The command scans local documents, finds significant unmatched terminology candidates, attaches evidence snippets, and keeps every candidate in `proposed` status.

If you already have a dictionary, pass it to filter known terms and aliases:

```bash
poetry run skeinrank suggest-dictionary ../../examples/suggest-dictionary/docs \
  --dictionary ../../examples/sdk/platform_ops_demo.dictionary.json \
  --profile-name platform_candidates \
  --out platform_candidates.dictionary-draft.json
```

## OpenRouter-assisted grouping

OpenRouter assistance is optional. It never replaces deterministic candidate discovery. The workflow is:

```text
local candidate discovery -> evidence-backed candidate summaries -> OpenRouter grouping -> reviewable draft
```

Run with an API key when you want model-assisted grouping:

```bash
export OPENROUTER_API_KEY="..."
export OPENROUTER_MODEL="provider/model"

poetry run skeinrank assist-dictionary ../../examples/agent-dictionary-assistant/docs \
  --model "$OPENROUTER_MODEL" \
  --profile-name platform_assisted_terms \
  --out ../../examples/agent-dictionary-assistant/platform_assisted.dictionary-draft.json \
  --review ../../examples/agent-dictionary-assistant/platform_assisted.review.md
```

The assistant is evidence-bound:

- it receives candidate summaries, not production credentials;
- evidence snippets are treated as untrusted data;
- aliases without deterministic evidence are dropped;
- the result is still a draft, not a runtime dictionary.

## Python API

Deterministic draft from documents:

```python
from skeinrank import suggest_dictionary_from_documents

result = suggest_dictionary_from_documents(
    ["../../examples/suggest-dictionary/docs"],
    config={
        "profile_name": "platform_candidates",
        "discovery": {"min_frequency": 2},
    },
)

result.save("platform_candidates.dictionary-draft.json")
print(result.review_markdown())
```

OpenRouter-assisted draft:

```python
from skeinrank import build_dictionary_from_docs

result = build_dictionary_from_docs(
    ["../../examples/agent-dictionary-assistant/docs"],
    model="provider/model",
)

result.save("platform_assisted.dictionary-draft.json")
print(result.review_markdown())
```

The model parameter can also be supplied through your CLI command, and the API key can be passed directly or read from `OPENROUTER_API_KEY`.

## Offline example for tests and demos

[`examples/agent-dictionary-assistant/offline_assisted_demo.py`](../../examples/agent-dictionary-assistant/offline_assisted_demo.py) uses a fake transport to demonstrate the assistant contract without calling OpenRouter. It is useful for CI, screenshots, and local explanation of the evidence boundary.

## Review flow

A draft is not a runtime dictionary. To preview locally after review:

```python
from skeinrank import DictionaryDraft, SkeinRank

draft = DictionaryDraft.from_file("platform_assisted.dictionary-draft.json")
runtime_dictionary = draft.accept_all().to_dictionary()

sr = SkeinRank(runtime_dictionary)
print(sr.canonicalize("KubeletOOM during EdgeGateway deploy"))
```

Use `accept_all()` only for local preview or controlled demos. In production workflows, candidates should be reviewed individually before snapshot rollout.

## Safety boundary

The assistant cannot:

- publish snapshots;
- update bindings;
- create production proposals by itself;
- read secrets from evidence;
- call enterprise tools;
- execute instructions found in documents.

The core rule is simple: agents can draft terminology; humans approve terminology; runtime serving stays deterministic.
