# LangGraph-style MCP agents for SkeinRank

Patch 62C documents a LangGraph-style integration pattern for the existing
`skeinrank-mcp` stdio adapter. It does not add a new Python agent package or a
new MCP tool list.

LangChain documents `langchain-mcp-adapters` as a way for agents to use tools
from MCP servers, including stdio servers launched as subprocesses:

```text
https://docs.langchain.com/oss/python/langchain/mcp
```

## Boundary

```text
LangGraph-style agent
  -> MCP client adapter
  -> skeinrank-mcp stdio process
  -> SkeinRank Governance API
  -> proposal workflow
```

The agent can reason over failed-search logs, tickets, docs, or code, but it
should only submit proposals. Runtime mutation remains outside the MCP path.

## Suggested graph

```text
Input: query / failed-search log / document excerpt
  -> choose known binding context
  -> skeinrank_explain_query
  -> candidate alias extraction in agent logic
  -> skeinrank_validate_alias
  -> if validation acceptable: skeinrank_submit_alias_proposal
  -> skeinrank_get_proposal_status
  -> human review in SkeinRank UI
  -> snapshot/GitOps delivery later
```

## MCP client configuration

Use the same stdio server shape as the generic kit:

```json
{
  "skeinrank": {
    "transport": "stdio",
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
```

This repository intentionally does not ship runnable LangGraph code in 62C. The
stable contract is the MCP stdio server plus the tool manifest:

```bash
skeinrank-mcp --print-tool-manifest
skeinrank-mcp --smoke-test
```

Use your chosen LangGraph/LangChain MCP adapter to load the MCP tools and attach
policy around them.

## Tool policy

Allow the agent to call:

```text
skeinrank_list_bindings
skeinrank_explain_query
skeinrank_validate_alias
skeinrank_submit_alias_proposal
skeinrank_get_proposal_status
```

Do not give the agent direct apply/publish capabilities through MCP. If a future
workflow needs that, create a separate reviewed design with stronger scopes,
operator approvals, and audit gates.

## Error handling

Recommended behavior:

```text
- if no binding matches, ask for a binding/workspace instead of guessing;
- if validate_alias returns blocking issues, do not submit a proposal;
- if an alias is ambiguous, include context/evidence and route to human review;
- if the Governance API is unavailable, stop and report the failed dependency;
- never fabricate a proposal id or claim that runtime changed.
```

See `examples/mcp-agent-docs/langgraph-agent-policy.md` and
`examples/mcp-agent-docs/langgraph-tool-flow.example.json`.
