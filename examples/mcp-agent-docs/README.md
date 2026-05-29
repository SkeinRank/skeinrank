# MCP client docs examples

Patch 62C adds client-specific MCP examples for Claude Desktop, Cursor, and
LangGraph-style agents. These files are safe templates only; they do not contain
real tokens and they do not add new MCP tools.

Docs:

```text
docs/deployment/mcp-claude-desktop.md
docs/deployment/mcp-cursor-agents.md
docs/deployment/mcp-langgraph-agents.md
```

Examples:

```text
claude-desktop-config.example.json
cursor-mcp-config.example.json
langgraph-tool-flow.example.json
claude-desktop-system-prompt.md
cursor-agent-rules.md
langgraph-agent-policy.md
smoke-checklist.md
```

Expected tools:

```text
skeinrank_list_bindings
skeinrank_explain_query
skeinrank_validate_alias
skeinrank_submit_alias_proposal
skeinrank_get_proposal_status
```
