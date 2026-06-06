# Dictionary CLI lint and apply planning

`skeinrank-migrate` provides two safe planning steps for JSON/YAML
Terminology-as-Code files:

```text
lint  -> local file checks, no API call
plan  -> server-backed apply plan, no database write
apply --plan-output -> write reviewed plan before import
```

The commands do not introduce a new mutation path. `apply` still calls the
existing dictionary import API, and `plan` derives its output from the existing
validation API. For `lint` and `plan`, no state was written.

## Command map

| Command | Contacts API | Writes DB | Purpose |
| --- | --- | --- | --- |
| `skeinrank-migrate lint FILE` | No | No | Fast local checks for JSON/YAML shape, duplicate canonical terms, alias collisions inside one file, stop-list target mistakes, and repeated aliases. |
| `skeinrank-migrate validate FILE` | Yes | No | Existing server validation. Checks the file against current PostgreSQL state, existing aliases, stop lists, profile existence, RBAC, and scopes. |
| `skeinrank-migrate plan FILE` | Yes | No | Builds `skeinrank.dictionary_apply_plan.v1` from the validation report and lists the create/update operations that `apply` would attempt. |
| `skeinrank-migrate apply FILE --plan-output PLAN.json` | Yes | Yes, only when plan is safe | Validates first, writes a plan artifact, blocks if the plan is invalid, and only then calls import. |

## Local lint

Use `lint` as the cheapest CI step. It is intentionally local-only, so it can run
before the governance API, PostgreSQL, or credentials are available:

```bash
cd packages/skeinrank-governance-api
poetry run skeinrank-migrate lint \
  ../../examples/terminology-as-code/platform_ops.dictionary.yaml
```

The report uses `schema_version: skeinrank.dictionary_lint.v1` and includes a
safety marker:

```json
{
  "checks": {
    "local_only": true,
    "server_state_checked": false,
    "safe_for_apply_decision": false
  }
}
```

That marker is important: `lint` can catch file-level mistakes, but it cannot know
whether an alias already exists in PostgreSQL or whether the caller has the right
scopes. Use `plan` before applying.

## Server-backed apply plan

Use `plan` after the API is running and credentials are available:

```bash
cd packages/skeinrank-governance-api
poetry run skeinrank-migrate plan \
  ../../examples/terminology-as-code/platform_ops.dictionary.yaml \
  --output ../../examples/terminology-as-code/platform_ops.plan.json
```

The plan uses `schema_version: skeinrank.dictionary_apply_plan.v1` and contains:

- `status`: `ready` or `blocked`;
- `safe_to_apply`: boolean gate for CI;
- `operations`: summarized create/update actions;
- `validation`: the full validation report returned by the existing API.

A ready plan may include operations such as:

```json
{
  "operations": [
    {"action": "create_profile", "count": 1},
    {"action": "create_terms", "count": 4},
    {"action": "create_aliases", "count": 7}
  ]
}
```

A blocked plan exits with code `2` by default and does not write state. Pass
`--allow-invalid` only when a CI job needs to archive the blocked plan as an
artifact without failing immediately.

## Planned apply

For reviewed delivery pipelines, prefer:

```bash
cd packages/skeinrank-governance-api
poetry run skeinrank-migrate apply \
  ../../examples/terminology-as-code/platform_ops.dictionary.yaml \
  --plan-output ../../examples/terminology-as-code/platform_ops.apply-plan.json
```

With `--plan-output`, the CLI validates first, writes the apply plan, and blocks
before import when `safe_to_apply` is false. This keeps `apply` explicit and
auditable without inventing a new API endpoint.

## Recommended CI sequence

```text
pull request changes dictionary file
  -> skeinrank-migrate lint FILE
  -> skeinrank-migrate plan FILE --output plan.json
  -> human/code-owner review of FILE + plan.json
  -> skeinrank-migrate apply FILE --plan-output applied-plan.json
  -> skeinrank-migrate export --profile-name ...
  -> skeinrank-migrate snapshot-export --binding-id ...
```

`lint` is a local guardrail. `plan` is the server-backed apply decision. `apply`
remains the only write step in this part of the flow.

## Delivery after apply

After a reviewed apply, use the existing export commands and the GitOps
delivery runbook to deliver runtime artifacts:

```bash
poetry run skeinrank-migrate export --profile-name "$SKEINRANK_PROFILE_NAME" --output reports/governed-dictionary.json
poetry run skeinrank-migrate snapshot-export --binding-id "$SKEINRANK_BINDING_ID" --source latest --snapshot-version "$SKEINRANK_SNAPSHOT_VERSION" --output runtime/runtime-snapshot.json
```

See [`../deployment/gitops-delivery-runbook.md`](../deployment/gitops-delivery-runbook.md)
for GitLab CI, ArgoCD, and Flux examples. GitOps delivery is external to
SkeinRank: the CLI writes artifacts, while your delivery tool commits, syncs,
mounts, restarts, or reloads runtime workers.
