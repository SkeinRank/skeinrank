# Terminology-as-Code examples

This directory contains small dictionary files used by
`docs/guides/terminology-as-code.md`.

- `platform_ops.dictionary.yaml` is the human-editable Git format with comments.
- `platform_ops.dictionary.json` is the equivalent canonical JSON API shape.

Validate either file through the current migration CLI:

```bash
cd packages/skeinrank-governance-api
poetry run skeinrank-migrate validate \
  ../../examples/terminology-as-code/platform_ops.dictionary.yaml

poetry run skeinrank-migrate validate \
  ../../examples/terminology-as-code/platform_ops.dictionary.json
```
