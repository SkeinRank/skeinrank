# Claude Desktop MCP setup for SkeinRank

Claude Desktop can launch SkeinRank's local MCP stdio adapter and expose the
same proposal-first governance tools that are available through the Governance
API. This setup is intended for review-assist workflows: Claude can inspect
bindings, explain query behavior, validate aliases, and submit pending proposals,
but production terminology changes still require the normal human review and
snapshot workflow.

Official MCP local-server docs:

```text
https://modelcontextprotocol.io/docs/develop/connect-local-servers
```

## Runtime boundary

```text
Claude Desktop
  -> local skeinrank-mcp stdio process
  -> SkeinRank Governance API
  -> /v1/tools/* validation and proposal APIs
  -> human review, apply, snapshot, and deployment workflow
```

The Claude agent must not approve proposals, publish snapshots, apply
dictionaries, mutate production bindings, or reload runtime terminology. It can
inspect, validate, and submit proposals for review.

## Prerequisites

Install the Governance API package from the monorepo:

```bash
cd packages/skeinrank-governance-api
poetry install
```

Verify the adapter without opening a Claude session:

```bash
poetry run skeinrank-mcp --smoke-test
poetry run skeinrank-mcp --print-tool-manifest
poetry run skeinrank-mcp --print-env-template
```

Start the Governance API separately before live tool calls.

## Claude Desktop config

Claude Desktop stores MCP server configuration in `claude_desktop_config.json`.
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

When using a Poetry checkout instead of an installed console script, point the
client to a wrapper that runs `poetry run skeinrank-mcp` from
`packages/skeinrank-governance-api`. Keep real API tokens in local secret
storage and restart Claude Desktop after editing the config.

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

```text
1. Call skeinrank_list_bindings to discover available runtime contexts.
2. Call skeinrank_explain_query with binding_id for production-like checks.
3. Call skeinrank_validate_alias before proposing a new alias.
4. Call skeinrank_submit_alias_proposal only when validation is acceptable.
5. Call skeinrank_get_proposal_status to check review state.
6. Let a human reviewer approve, apply, and publish later in SkeinRank UI or GitOps.
```

For ambiguous aliases, Claude should submit context-rich proposals instead of
claiming that live runtime changed. For blocked validation results, Claude should
return the warning to the user and avoid submitting a proposal.

## Recommended prompt

Use `examples/mcp-agent-docs/claude-desktop-system-prompt.md` as the base system
prompt for Claude Desktop. It keeps the agent inside the proposal workflow,
requires `binding_id` when available, and prevents the model from treating
retrieved enterprise text as instructions.
