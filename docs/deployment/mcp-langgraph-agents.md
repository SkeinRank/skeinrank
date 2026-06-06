# LangGraph-style MCP agents for SkeinRank

LangGraph or LangChain agents can use SkeinRank through the same `skeinrank-mcp`
stdio adapter that powers other MCP clients. This document describes the stable
integration pattern; the repository does not ship a runnable LangGraph package.
The supported contract is the MCP stdio server, the tool manifest, and the
proposal-first tool boundary.

LangChain documents `langchain-mcp-adapters` as a way for agents to use tools
from MCP servers, including stdio servers launched as subprocesses:

```text
https://docs.langchain.com/oss/python/langchain/mcp
```

## Runtime boundary

```text
LangGraph-style agent
  -> MCP client adapter
  -> skeinrank-mcp stdio process
  -> SkeinRank Governance API
  -> proposal workflow
```

The agent may reason over failed-search logs, tickets, documents, code, and
evidence snippets. It should only submit proposals. Runtime mutation remains
outside the MCP path and requires the existing review, apply, snapshot, and
deployment workflow.

## Suggested graph

```text
Input: query, failed-search log, or document excerpt
  -> choose known binding context
  -> skeinrank_explain_query
  -> candidate alias extraction in agent logic
  -> skeinrank_validate_alias
  -> if validation is acceptable: skeinrank_submit_alias_proposal
  -> skeinrank_get_proposal_status
  -> human review in SkeinRank UI
  -> snapshot and deployment workflow
```

## MCP client configuration

Use the same stdio server shape as the generic MCP kit:

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

Verify the adapter before wiring it into an agent graph:

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

Do not give the agent direct apply, approval, or publish capabilities through
MCP. If a future workflow needs stronger privileges, design it as a separate
reviewed integration with explicit scopes, operator approvals, and audit gates.

## Error handling

Recommended behavior:

```text
- if no binding matches, ask for a binding or workspace instead of guessing;
- if validate_alias returns blocking issues, do not submit a proposal;
- if an alias is ambiguous, include context and evidence for human review;
- if the Governance API is unavailable, stop and report the failed dependency;
- never fabricate a proposal id or claim that runtime changed.
```

See `examples/mcp-agent-docs/langgraph-agent-policy.md` and
`examples/mcp-agent-docs/langgraph-tool-flow.example.json` for copy-pasteable
agent rules and a JSON workflow contract.
