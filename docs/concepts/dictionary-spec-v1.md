# Dictionary spec v1

SkeinRank dictionary files describe a terminology profile that can be validated,
imported, exported, and used by the local SDK/CLI.

The canonical interchange format is JSON. YAML is accepted by the CLI as a
human-editable convenience for GitOps-style repositories when PyYAML is available, but HTTP APIs continue
to receive and return JSON. For the complete Terminology-as-Code import/export
workflow, see [`../guides/terminology-as-code.md`](../guides/terminology-as-code.md).

## Schema version

Every new dictionary file should include:

```json
{
  "schema_version": "skeinrank.dictionary.v1"
}
```

Legacy dictionary files without `schema_version` are still accepted and treated
as `skeinrank.dictionary.v1` for backward compatibility.

Unknown schema versions must not be silently accepted. The governance API reports
`unsupported_schema_version`, and the local SDK raises a validation error.

## Minimal JSON shape

```json
{
  "schema_version": "skeinrank.dictionary.v1",
  "profile_name": "platform_ops",
  "profile_description": "Platform operations terminology",
  "create_profile": true,
  "mode": "upsert",
  "terms": [
    {
      "canonical_value": "kubernetes",
      "slot": "technology",
      "description": "Container orchestration platform",
      "tags": ["infra", "orchestration"],
      "aliases": [
        "k8s",
        {
          "value": "kube",
          "confidence": 0.95,
          "notes": "Common engineering shorthand"
        }
      ]
    }
  ],
  "profile_stop_list": [
    {
      "value": "tmp",
      "target": "alias",
      "reason": "Too generic for this profile"
    }
  ],
  "global_stop_list": []
}
```

## YAML input

The same shape can be written as YAML for CLI input:

```yaml
schema_version: skeinrank.dictionary.v1
profile_name: platform_ops
profile_description: Platform operations terminology
create_profile: true
mode: upsert
terms:
  - canonical_value: kubernetes
    slot: technology
    description: Container orchestration platform
    tags:
      - infra
      - orchestration
    aliases:
      - k8s
      - value: kube
        confidence: 0.95
        notes: Common engineering shorthand
profile_stop_list:
  - value: tmp
    target: alias
    reason: Too generic for this profile
global_stop_list: []
```

## Field notes

- `profile_name` identifies the terminology profile.
- `mode` is currently `upsert` or `strict`.
- `terms[].canonical_value` is the normalized target term used at runtime.
- `terms[].slot` is the extraction/search role for the canonical term.
- `terms[].tags` is an optional list of normalized facets such as `infra`,
  `backend`, or `storage`. Tags do not replace the primary slot.
- `terms[].aliases` may be strings or objects with `value`, `confidence`,
  `status`, and `notes`.
- `profile_stop_list` applies to one profile.
- `global_stop_list` applies across profiles.


## API surfaces

The dictionary spec is served through two API surfaces:

```text
POST /v1/headless/dictionaries/validate
POST /v1/headless/dictionaries/apply
GET  /v1/headless/dictionaries/export?profile_name=...

POST /v1/console/dictionary/validate
POST /v1/console/dictionary/import
GET  /v1/console/dictionary/export?profile_name=...
```

Use `/v1/headless/dictionaries/*` for CI/CD, service integrations, and agent
workflows. The `/v1/console/dictionary/*` routes remain as a compatibility layer
for the governance console and older scripts. Both surfaces use the same
validation and apply implementation.

## Compatibility policy

- `skeinrank.dictionary.v1` is the stable baseline for the current headless
  consolidation phase.
- New optional fields may be added to v1 only when old clients can safely ignore
  them. `terms[].tags` is the first additive v1 field for the coverage framework.
- Breaking field changes require a new `schema_version`.
- Exported dictionaries include `schema_version` so CI, bots, and agents can
  detect the expected contract.


## Alias context triggers

Object aliases may include optional `context_triggers` for deterministic runtime
disambiguation:

```json
{
  "value": "pg",
  "confidence": 0.95,
  "context_triggers": ["timeout", "replica", "migration"]
}
```

A trigger-gated alias matches only when the runtime query also contains at least
one configured trigger. String aliases and object aliases without triggers keep
the existing always-active behavior.
