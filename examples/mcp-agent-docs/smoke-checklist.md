# MCP client smoke checklist

Run locally before opening Claude Desktop, Cursor, or a LangGraph-style agent:

```bash
skeinrank-mcp --smoke-test
skeinrank-mcp --print-tool-manifest
skeinrank-mcp --print-env-template
```

Expected manifest schema:

```text
skeinrank.mcp_integration_manifest.v1
```

Expected smoke report schema:

```text
skeinrank.mcp_smoke_report.v1
```

Expected tools:

```text
skeinrank_list_bindings
skeinrank_explain_query
skeinrank_validate_alias
skeinrank_submit_alias_proposal
skeinrank_get_proposal_status
```

Live smoke path after the Governance API is running:

```text
1. list bindings
2. explain a sample query with binding_id
3. validate a harmless alias candidate
4. submit a low-risk proposal only in a demo/profile sandbox
5. check proposal status
```

Do not use a production token for local config experiments.

Remember: MCP proposals are pending review; snapshot publication happens later through the normal governance flow.
