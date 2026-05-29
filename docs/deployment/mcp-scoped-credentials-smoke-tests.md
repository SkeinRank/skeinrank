# MCP scoped credentials and smoke tests

Patch 62B documents the least-privilege credential path for `skeinrank-mcp` and
adds an offline smoke-test command for agent integration packaging.

The MCP adapter remains a thin stdio bridge over the Governance API. It does not
own proposal business logic, approve suggestions, publish snapshots, or mutate
runtime terminology directly.

## Credential model

Use service-account API tokens for deployed agents instead of long-lived human
personal tokens. The recommended policy is exposed by the existing admin-only
endpoint:

```http
GET /v1/auth/scoped-agent-credentials
```

Response schema:

```text
skeinrank.scoped_agent_credentials.v1
```

The MCP integration manifest also embeds the same credential policy so agent
client packaging can discover recommended profiles without inventing scope names:

```bash
poetry run skeinrank-mcp --print-tool-manifest
```

Look for:

```text
credentials.recommended_credentials
```

Recommended MCP deployments should use a `contributor` service account with the
`agent-proposal-writer` profile when the agent may submit proposals. That profile
can validate aliases and create pending suggestions, but it cannot approve,
apply, publish snapshots, or mutate runtime state.

## Create a proposal-writer service account

Create the service account with the existing auth API:

```http
POST /v1/auth/service-accounts
Content-Type: application/json
Authorization: Bearer <admin-token>
```

Request body:

```json
{
  "name": "mcp-agent-proposal-writer",
  "display_name": "MCP proposal writer",
  "description": "Least-privilege service account for skeinrank-mcp proposal workflows.",
  "role": "contributor",
  "is_active": true
}
```

Then create a copy-once token:

```http
POST /v1/auth/service-accounts/mcp-agent-proposal-writer/tokens
Content-Type: application/json
Authorization: Bearer <admin-token>
```

Request body:

```json
{
  "name": "mcp proposal writer token",
  "scopes": [
    "agent:runs:read",
    "agent:runs:write",
    "agent:tracking:read",
    "agent:tracking:write",
    "agent:tools:read",
    "agent:tools:validate",
    "agent:tools:suggest",
    "agent:tools:explain",
    "ops:reports:read"
  ],
  "expires_in_days": 90
}
```

Store the returned `access_token` in the deployment secret store. The plaintext
token is returned once.

## Configure `skeinrank-mcp` with a scoped token

```bash
export SKEINRANK_MCP_GOVERNANCE_API_URL=http://127.0.0.1:8010
export SKEINRANK_MCP_ROLE=contributor
export SKEINRANK_MCP_API_TOKEN=sk_sat_...
export SKEINRANK_MCP_TIMEOUT_SECONDS=10.0
poetry run skeinrank-mcp
```

`SKEINRANK_MCP_ROLE` is still useful for local no-auth deployments. When auth is
enabled, the Bearer token determines the authenticated service account and the
API enforces scopes through existing `require_scopes(...)` checks.

## Rotate a service-account token

Use the existing token rotation endpoint:

```http
POST /v1/auth/service-accounts/{account_name}/tokens/{token_id}/rotate
Content-Type: application/json
Authorization: Bearer <admin-token>
```

Example body:

```json
{
  "name": "mcp proposal writer token rotated",
  "scopes": [
    "agent:runs:read",
    "agent:runs:write",
    "agent:tracking:read",
    "agent:tracking:write",
    "agent:tools:read",
    "agent:tools:validate",
    "agent:tools:suggest",
    "agent:tools:explain",
    "ops:reports:read"
  ],
  "expires_in_days": 90
}
```

When `scopes` is omitted, the replacement token inherits the old token scopes.
The old token is revoked by default.

## Offline smoke test

Patch 62B adds an offline smoke-test helper:

```bash
poetry run skeinrank-mcp --smoke-test
```

Output schema:

```text
skeinrank.mcp_smoke_report.v1
```

The smoke test intentionally avoids network access. It checks that the adapter can
initialize, expose the packaged MCP tools, emit the integration manifest, and
include the scoped credential policy. It does not call the Governance API, create
service accounts, create proposals, or mutate runtime terminology.

Expected status:

```json
{
  "schema": "skeinrank.mcp_smoke_report.v1",
  "status": "passed",
  "requires_governance_api": false
}
```

## Live smoke path

After the Governance API is running and the scoped token is configured, use a
client to call the real MCP tools in this order:

```text
skeinrank_list_bindings
skeinrank_explain_query
skeinrank_validate_alias
skeinrank_submit_alias_proposal
skeinrank_get_proposal_status
```

This live path exercises existing API routes:

```text
GET  /v1/tools/bindings
POST /v1/tools/explain-query
POST /v1/tools/validate-alias
POST /v1/tools/suggest-alias
GET  /v1/governance/profiles/{profile_name}/suggestions
```

A proposal submitted by MCP is still pending review. Runtime changes require the
normal governance flow: review, apply, snapshot publication, and deployment.


Client-specific setup docs for Claude Desktop, Cursor/IDE agents, and
LangGraph-style agents live in:

```text
docs/deployment/mcp-claude-desktop.md
docs/deployment/mcp-cursor-agents.md
docs/deployment/mcp-langgraph-agents.md
examples/mcp-agent-docs/
```

## Safety checklist

- Use service-account tokens, not human personal tokens, for deployed agents.
- Prefer `role: contributor` for MCP agents.
- Use `agent-proposal-writer` scopes only when proposal submission is needed.
- Use a read-only profile when the agent only explains queries or validates aliases.
- Rotate tokens on a schedule and after any suspected exposure.
- Never store `SKEINRANK_MCP_API_TOKEN` in Git.
- Run `skeinrank-mcp --smoke-test` in CI before publishing an agent image.
