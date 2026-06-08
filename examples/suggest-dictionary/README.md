# Suggest a dictionary draft from documents

This example shows the deterministic cold-start workflow for teams that do not yet have a SkeinRank dictionary.

The command scans local documents, finds significant unmatched terminology, and writes a reviewable dictionary draft. It does not call an LLM, connect to the Governance API, publish snapshots, mutate bindings, or change production runtime behavior.

```bash
cd packages/skeinrank-core
poetry run skeinrank suggest-dictionary ../../examples/suggest-dictionary/docs \
  --profile-name platform_candidates \
  --min-frequency 2 \
  --out ../../examples/suggest-dictionary/platform_candidates.dictionary-draft.json \
  --review ../../examples/suggest-dictionary/platform_candidates.review.md
```

The draft is intentionally review-first. Candidates stay in `proposed` status until a human accepts or rejects them.

```python
from skeinrank import DictionaryDraft

draft = DictionaryDraft.from_file("platform_candidates.dictionary-draft.json")
print(draft.review_markdown())

preview_dictionary = draft.accept_all().to_dictionary()
```

Use this flow for local exploration and onboarding. Production changes should still go through review, validation, snapshots, and rollout policy.
