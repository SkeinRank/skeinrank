# Claude Desktop MCP setup for SkeinRank

Patch 62C adds client-specific MCP documentation for Claude Desktop without
changing the `skeinrank-mcp` runtime surface.

Claude Desktop can launch local MCP stdio servers from a JSON configuration
file. The SkeinRank adapter follows that pattern: Claude starts
`skeinrank-mcp`, and the adapter delegates all work to the existing Governance
API.

Official MCP local-server docs:

```text
https://modelcontextprotocol.io/docs/develop/connect-local-servers
```

## Boundary

```text
Claude Desktop
  -> local skeinrank-mcp stdio process
  -> SkeinRank Governance API
  -> /v1/tools/* validation and proposal APIs
  -> human review / snapshot / GitOps later
```

The Claude agent must not approve proposals, publish snapshots, apply
dictionaries, or mutate runtime terminology directly. It can inspect, validate,
and submit pending proposals for review.

## Prerequisites

From the SkeinRank monorepo:

```bash
cd packages/skeinrank-governance-api
poetry install
```

Verify the package without opening a Claude session:

```bash
poetry run skeinrank-mcp --smoke-test
poetry run skeinrank-mcp --print-tool-manifest
poetry run skeinrank-mcp --print-env-template
```

Start the Governance API separately before live tool calls.

## Claude Desktop config

Claude Desktop stores the MCP server list in `claude_desktop_config.json`.
Common locations are:

```text
macOS:   ~/Library/Application Support/Claude/claude_desktop_config.json
Windows: %APPDATA%\Claude\claude_desktop_config.json
```

Example config:

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

When using a Poetry checkout instead of an installed console script, use the
absolute path to `poetry` and set the working directory through your launcher or
shell wrapper if your client requires it. The project examples keep the config
portable by assuming `skeinrank-mcp` is already on `PATH`.

Restart Claude Desktop after editing the config.

## Expected tools

After restart, Claude should see exactly these SkeinRank tools:

```text
skeinrank_list_bindings
skeinrank_explain_query
skeinrank_validate_alias
skeinrank_submit_alias_proposal
skeinrank_get_proposal_status
```

If the tools do not appear, run:

```bash
skeinrank-mcp --smoke-test
skeinrank-mcp --print-tool-manifest
```

Then check Claude Desktop MCP logs for the `skeinrank` server process.

## Safe Claude workflow

Use Claude Desktop for review-assist and proposal-assist workflows:

```text
1. Call skeinrank_list_bindings to discover available runtime contexts.
2. Call skeinrank_explain_query with binding_id for production-like checks.
3. Call skeinrank_validate_alias before proposing a new alias.
4. Call skeinrank_submit_alias_proposal only when validation is acceptable.
5. Call skeinrank_get_proposal_status to check review state.
6. Let a human reviewer approve/apply/publish later in SkeinRank UI or GitOps.
```

For ambiguous aliases, Claude should submit context-rich proposals rather than
claiming that a term has been changed in live runtime.

## Recommended prompt

See `examples/mcp-agent-docs/claude-desktop-system-prompt.md` for a prompt that
keeps Claude inside the proposal workflow.
