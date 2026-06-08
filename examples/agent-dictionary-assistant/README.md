# Agent-assisted dictionary draft

This example shows the optional OpenRouter-assisted workflow for teams that do not yet have a clean dictionary.

The workflow keeps runtime deterministic:

1. SkeinRank scans local documents with the deterministic candidate discovery engine.
2. OpenRouter groups and names only those evidence-backed candidates.
3. The output is a reviewable dictionary draft, not a production dictionary.
4. A human reviews the draft before converting accepted candidates into runtime terminology.

## CLI

Set your OpenRouter key and model explicitly:

```bash
export OPENROUTER_API_KEY="..."
export OPENROUTER_MODEL="provider/model"
```

Generate a reviewable draft:

```bash
cd packages/skeinrank-core
poetry run skeinrank assist-dictionary ../../examples/agent-dictionary-assistant/docs \
  --model "$OPENROUTER_MODEL" \
  --profile-name platform_assisted_terms \
  --out ../../examples/agent-dictionary-assistant/platform_assisted.dictionary-draft.json \
  --review ../../examples/agent-dictionary-assistant/platform_assisted.review.md
```

The command never publishes snapshots, mutates bindings, or changes governance state.

## Python

```python
import os
from skeinrank import build_dictionary_from_docs

result = build_dictionary_from_docs(
    ["../../examples/agent-dictionary-assistant/docs"],
    model=os.environ["OPENROUTER_MODEL"],
)

print(result.review_markdown())
result.save("platform_assisted.dictionary-draft.json")
```

To preview locally after review:

```python
dictionary = result.draft.accept_all().to_dictionary()
```

Use `accept_all()` only for local preview. In production, review candidates and promote approved terminology through the governance workflow.
