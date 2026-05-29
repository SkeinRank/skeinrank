# SkeinRank MCP integration kit

This directory contains generic MCP packaging examples for the existing
`skeinrank-mcp` stdio adapter.

The examples are intentionally client-neutral. They do not require Claude
Desktop, Cursor, LangGraph, or any third-party MCP Python package.

## Files

| File | Purpose |
| --- | --- |
| `skeinrank-mcp.env.example` | Environment variables for the stdio adapter. |
| `mcp-client.stdio.example.json` | Generic stdio client config fragment. |
| `agent-tool-contract.json` | Tool names and safe sample arguments. |
| `agent-system-prompt.md` | Safety-focused prompt for agents using SkeinRank tools. |
| `agent-workflow.md` | Human-in-the-loop proposal workflow checklist. |

## Local preview

From `packages/skeinrank-governance-api`:

```bash
poetry run skeinrank-mcp --print-tool-manifest
poetry run skeinrank-mcp --print-env-template
```

Start the stdio adapter only after the Governance API is running:

```bash
poetry run skeinrank-governance-api --reload
poetry run skeinrank-mcp --api-url http://127.0.0.1:8010
```

Agents can validate aliases and submit proposals, but they cannot directly mutate
active runtime terminology.
