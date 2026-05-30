# GitHub labels

SkeinRank uses labels to make Issues and PRs triageable across product, runtime, docs, site, MCP, and CI work.

The source label set lives in [`.github/labels.yml`](../../.github/labels.yml). GitHub does not automatically apply labels from that file; maintainers should sync them with GitHub CLI or create them manually in repository settings.

## Label groups

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

## Sync with GitHub CLI

Install and authenticate GitHub CLI first:

```bash
gh auth status
```

Then create or update labels. GitHub CLI does not currently provide a first-party bulk sync command, so the safest portable approach is to run explicit `gh label create ... --force` commands:

```bash
gh label create "type: bug" --color d73a4a --description "Something is broken or behaving incorrectly." --force
gh label create "type: feature" --color a2eeef --description "A new capability, API, UI flow, or product feature." --force
gh label create "type: docs" --color 0075ca --description "Documentation, examples, diagrams, or README changes." --force
gh label create "type: refactor" --color cfd3d7 --description "Internal cleanup without intended behavior change." --force
gh label create "type: question" --color d876e3 --description "A concrete question that belongs in Issues rather than Discussions." --force
gh label create "type: integration" --color 0e8a16 --description "Integration work for search backends, agents, MCP, GitOps, or external tools." --force

gh label create "area: governance-api" --color 1d76db --description "FastAPI governance/control-plane API." --force
gh label create "area: ui" --color 5319e7 --description "React governance console and product UI." --force
gh label create "area: core" --color 0052cc --description "Core SDK, dictionary logic, canonicalization, and extraction." --force
gh label create "area: elasticsearch" --color fbca04 --description "Elasticsearch/OpenSearch evidence, enrichment, and alias swap flows." --force
gh label create "area: mcp" --color 8b5cf6 --description "MCP server, agent tools, and client integration docs." --force
gh label create "area: docs" --color 0ea5e9 --description "Docs site, README, guides, diagrams, and examples." --force
gh label create "area: ci" --color f9d0c4 --description "GitHub Actions, tests, linting, release, and packaging automation." --force
gh label create "area: site" --color 22d3ee --description "Public website, landing page, and visual positioning." --force

gh label create "status: needs-triage" --color ededed --description "Needs maintainer review before implementation." --force
gh label create "status: accepted" --color 0e8a16 --description "Accepted for implementation or documentation work." --force
gh label create "status: blocked" --color b60205 --description "Blocked by another decision, dependency, or missing information." --force
gh label create "status: good-first-issue" --color 7057ff --description "Good for first-time contributors." --force

gh label create "priority: p0" --color b60205 --description "Critical: breaks releases, data safety, or core runtime behavior." --force
gh label create "priority: p1" --color d93f0b --description "High priority: important public beta, runtime, or operator issue." --force
gh label create "priority: p2" --color fbca04 --description "Normal priority: useful but not immediately blocking." --force
```

## Triage rules

- New issues should start with `status: needs-triage`.
- A maintainer moves accepted work to `status: accepted`.
- Use exactly one `type:*` label when possible.
- Use one or more `area:*` labels for cross-cutting work.
- Use priority labels only after triage.
- Questions that are not concrete bugs or tasks should be moved to Discussions.
