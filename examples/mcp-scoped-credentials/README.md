# MCP scoped credentials examples

These examples show how to wire `skeinrank-mcp` to a least-privilege service
account token.

The examples use only existing Governance API endpoints:

```text
GET  /v1/auth/scoped-agent-credentials
POST /v1/auth/service-accounts
POST /v1/auth/service-accounts/{account_name}/tokens
POST /v1/auth/service-accounts/{account_name}/tokens/{token_id}/rotate
```

## Files

| File | Purpose |
| --- | --- |
| `create-proposal-writer-service-account.json` | Request body for the MCP proposal-writer service account. |
| `create-proposal-writer-token.json` | Request body for a scoped proposal-writer token. |
| `create-readonly-validator-token.json` | Request body for a read-only validator token. |
| `rotate-proposal-writer-token.json` | Request body for service-account token rotation. |
| `mcp-client.scoped-token.example.json` | Generic stdio client config using token env vars. |
| `smoke-test.expected.json` | Minimal expected shape from `skeinrank-mcp --smoke-test`. |

## Offline smoke

From `packages/skeinrank-governance-api`:

```bash
poetry run skeinrank-mcp --smoke-test
```

The command does not contact the Governance API and does not create proposals.

## Runtime launch

```bash
export SKEINRANK_MCP_GOVERNANCE_API_URL=http://127.0.0.1:8010
export SKEINRANK_MCP_ROLE=contributor
export SKEINRANK_MCP_API_TOKEN=sk_sat_...
poetry run skeinrank-mcp
```
