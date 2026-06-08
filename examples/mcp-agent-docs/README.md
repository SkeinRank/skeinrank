# MCP client docs examples

These examples provide client-specific MCP templates for Claude Desktop, Cursor, and LangGraph-style agents.

The files are safe templates only. They do not contain real tokens and they do not add new MCP tools.

## Related docs

```text
docs/deployment/mcp-claude-desktop.md
docs/deployment/mcp-cursor-agents.md
docs/deployment/mcp-langgraph-agents.md
```

## Example files

```text
claude-desktop-config.example.json
cursor-mcp-config.example.json
langgraph-tool-flow.example.json
claude-desktop-system-prompt.md
cursor-agent-rules.md
langgraph-agent-policy.md
smoke-checklist.md
```

## Expected tools

```text
skeinrank_list_bindings
skeinrank_explain_query
skeinrank_validate_alias
skeinrank_submit_alias_proposal
skeinrank_get_proposal_status
```

## Safety boundary

The MCP flow is proposal-first:

```text
agent -> inspect/validate/propose -> human review -> snapshot -> runtime
```

Agents can inspect governed terminology and submit reviewable proposals. They should not publish snapshots, mutate production bindings, run search-delivery jobs, or read secrets.
