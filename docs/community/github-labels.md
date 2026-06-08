# GitHub labels

SkeinRank uses a compact label taxonomy to keep Issues and PRs easy to triage across the control plane, SDK, runtime integrations, documentation, and CI.

The source label set lives in [`.github/labels.yml`](../../.github/labels.yml). Maintainers should keep repository labels aligned with that file through GitHub settings or their preferred repository administration tooling.

## Label groups

| Group | Purpose |
| --- | --- |
| `type:*` | What kind of work this is. |
| `area:*` | Which product or repository area is affected. |
| `status:*` | Current triage state. |
| `priority:*` | Maintainer-assigned urgency. |

## Current taxonomy

### Type

- `type: bug`
- `type: feature`
- `type: docs`
- `type: refactor`
- `type: question`
- `type: integration`

### Area

- `area: governance-api`
- `area: ui`
- `area: core`
- `area: elasticsearch`
- `area: mcp`
- `area: docs`
- `area: ci`
- `area: site`

### Status

- `status: needs-triage`
- `status: accepted`
- `status: blocked`
- `status: good-first-issue`

### Priority

- `priority: p0`
- `priority: p1`
- `priority: p2`

## Triage rules

- New issues start with `status: needs-triage`.
- Accepted work moves to `status: accepted`.
- Use exactly one `type:*` label when possible.
- Use one or more `area:*` labels for cross-cutting work.
- Use `priority:*` labels only after maintainer triage.
- Questions, architecture discussions, and open-ended integration ideas belong in GitHub Discussions before they become implementation issues.

## Maintainer notes

The label file is the source of truth. If labels change, update `.github/labels.yml`, this taxonomy page, and any issue templates that preselect labels.
