# Cursor / IDE agent MCP setup for SkeinRank

Cursor is primarily an AI IDE, but MCP makes it useful for SkeinRank as a
developer integration workspace. A Search Engineer can keep code, docs, and the
SkeinRank control-plane tools in one place while integrating canonicalization or
proposal workflows into an application.

Cursor MCP docs:

```text
https://cursor.com/docs/mcp
```

## Boundary

```text
Cursor agent in repository
  -> local skeinrank-mcp stdio process
  -> SkeinRank Governance API
  -> safe tools: list, explain, validate, propose, status
```

Cursor is not the business-user admin UI. It is a developer/agent workspace for
engineers who are wiring SkeinRank into code or debugging a search/RAG backend.

## Prerequisites

```bash
cd packages/skeinrank-governance-api
poetry install
poetry run skeinrank-mcp --smoke-test
```

For an installed package, `skeinrank-mcp` can be used directly from `PATH`.

## Cursor MCP config

Use a project-level config when you want the server attached only to one codebase
or a user-level config when the server should be available across projects.

Example `.cursor/mcp.json` style config:

```json
{
  "mcpServers": {
    "skeinrank": {
      "command": "skeinrank-mcp",
      "args": [],
      "env": {
        "SKEINRANK_MCP_GOVERNANCE_API_URL": "http://127.0.0.1:8010",
        "SKEINRANK_MCP_ROLE": "contributor",
        "SKEINRANK_MCP_TIMEOUT_SECONDS": "10.0",
        "SKEINRANK_MCP_API_TOKEN": "REPLACE_WITH_SCOPED_SERVICE_ACCOUNT_TOKEN"
      }
    }
  }
}
```

Keep tokens out of Git. For shared repositories, commit only
`examples/mcp-agent-docs/cursor-mcp-config.example.json` and let developers keep
real tokens in local secret storage.

## What Cursor agents should do

Good IDE-agent tasks:

```text
- inspect available bindings before writing integration code;
- explain a query with the binding_id used by the current backend route;
- validate an alias candidate found in tests, docs, or failed-search logs;
- submit a pending proposal with evidence/context;
- check proposal status before updating docs or TODOs.
```

Bad IDE-agent tasks:

```text
- invent a profile_name when binding_id is available;
- claim that a proposal changed production runtime;
- approve suggestions;
- publish snapshots;
- apply dictionaries;
- call non-existent runtime reload endpoints.
```

## Safe Cursor workflow

```text
Developer asks Cursor to integrate SkeinRank with a search route.
  -> Cursor reads the code.
  -> Cursor calls skeinrank_list_bindings.
  -> Cursor updates code to pass binding_id to the app's SkeinRank integration.
  -> Cursor calls skeinrank_explain_query for a sample query.
  -> Cursor proposes tests/docs updates.
```

If Cursor finds a new alias while reading a project, it should run
`skeinrank_validate_alias` first and only then `skeinrank_submit_alias_proposal`.
A human still reviews the proposal in SkeinRank.

## Recommended rules

See `examples/mcp-agent-docs/cursor-agent-rules.md` for copy-pasteable IDE agent
rules.
