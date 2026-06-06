# MCP packaging and agent integration kit

The `skeinrank-mcp` stdio adapter packages the existing safe tool facade as a small agent integration kit. The goal is to make the MCP path discoverable and testable without adding a second business-logic layer.

## Boundary

```text
agent / MCP client
  -> skeinrank-mcp stdio adapter
  -> SkeinRank Governance API
  -> /v1/tools/* and proposal review APIs
  -> reviewed snapshot publish
```

The MCP adapter is intentionally thin:

- it does not write directly to runtime snapshots;
- it does not approve or apply terminology changes;
- it delegates validation and proposal submission to existing Governance API routes;
- it keeps `binding_id` available for production runtime context;
- it can be run from a local Poetry checkout or from a packaged console script.

## Install from the monorepo

From the package directory:

```bash
cd packages/skeinrank-governance-api
poetry install
```

Start the Governance API separately, then start the MCP stdio adapter:

```bash
poetry run skeinrank-mcp --api-url http://127.0.0.1:8010
```

For environment-driven launches:

```bash
export SKEINRANK_MCP_GOVERNANCE_API_URL=http://127.0.0.1:8010
export SKEINRANK_MCP_ROLE=admin
# Optional when auth is enabled:
export SKEINRANK_MCP_API_TOKEN=...
poetry run skeinrank-mcp
```

## Packaging helpers

The adapter exposes two metadata commands for agent clients and integration tests.
They exit without starting the stdio server.

Print the package/tool manifest:

```bash
poetry run skeinrank-mcp --print-tool-manifest
```

The manifest schema is:

```text
skeinrank.mcp_integration_manifest.v1
```

The manifest also includes `tool_policy` with schema `skeinrank.mcp_tool_safety_policy.v1`. The policy lists allowed tools, forbidden runtime actions, allowed REST surfaces, forbidden REST surfaces, and the top-level argument keys each tool may accept.

Print a shell-friendly env template:

```bash
poetry run skeinrank-mcp --print-env-template
```

Run the offline packaging smoke test:

```bash
poetry run skeinrank-mcp --smoke-test
```

These helpers are packaging-only. They do not call the Governance API, create
proposals, or mutate runtime terminology.

## Prompt injection and tool-injection boundary

MCP clients must treat user text, retrieved documents, evidence snippets, and model output as untrusted data. Text found inside a document can describe an instruction, but it must not change the MCP tool policy or cause runtime mutation.

The adapter exposes only read and proposal-oriented tools. It does not publish snapshots, approve terminology changes, mutate production bindings, run enrichment jobs, send email, read secrets, or call unrelated enterprise tools. If a model suggests one of those actions, the safe output is a proposal, validation report, or operator checklist.

The adapter also rejects unknown MCP tool names and top-level proxy-style arguments such as `endpoint`, `url`, `method`, `command`, `tool`, `tool_name`, `operation`, and `runtime_action`. This keeps the adapter from becoming a generic HTTP or tool proxy.

See [`../security/prompt-injection.md`](../security/prompt-injection.md), [`../security/rag-context-boundaries.md`](../security/rag-context-boundaries.md), [`../security/agent-tool-safety.md`](../security/agent-tool-safety.md), [`../security/mcp-tool-guardrails.md`](../security/mcp-tool-guardrails.md), [`../security/prompt-like-detector.md`](../security/prompt-like-detector.md), and [`../security/prompt-injection-regression-corpus.md`](../security/prompt-injection-regression-corpus.md).

## Scoped credentials

Auth-enabled MCP deployments should use service-account API tokens with explicit
agent scopes. The credential policy is exposed by the existing endpoint:

```http
GET /v1/auth/scoped-agent-credentials
```

The same policy is included in the `skeinrank-mcp --print-tool-manifest` output
under `credentials`. See
[`mcp-scoped-credentials-smoke-tests.md`](mcp-scoped-credentials-smoke-tests.md)
and `examples/mcp-scoped-credentials/` for request bodies and smoke-test examples.

## Tools exposed

The MCP adapter exposes the existing safe tool facade:

```text
skeinrank_list_bindings
skeinrank_explain_query
skeinrank_validate_alias
skeinrank_submit_alias_proposal
skeinrank_get_proposal_status
```

Tool behavior remains the same as the REST API:

| MCP tool | REST surface | Runtime mutation |
| --- | --- | --- |
| `skeinrank_list_bindings` | `GET /v1/tools/bindings` | No |
| `skeinrank_explain_query` | `POST /v1/tools/explain-query` | No |
| `skeinrank_validate_alias` | `POST /v1/tools/validate-alias` | No |
| `skeinrank_submit_alias_proposal` | `POST /v1/tools/suggest-alias` | Proposal only |
| `skeinrank_get_proposal_status` | `GET /v1/governance/profiles/{profile_name}/suggestions` | No |

## Recommended agent flow

```text
1. Call skeinrank_list_bindings to discover runtime contexts.
2. Call skeinrank_explain_query with binding_id when checking a production-like query.
3. Call skeinrank_validate_alias before submitting a candidate.
4. Call skeinrank_submit_alias_proposal only when validation is acceptable.
5. Let a human/reviewer approve, batch apply, and publish the next snapshot.
```

Agents should not invent profile names or direct index names when a `binding_id`
is available. In production-like flows, `binding_id` is the runtime context and
`profile_name` is mostly a preview/development fallback.

## Example kit

See `examples/mcp-integration-kit/` for:

- a generic stdio client config fragment;
- an env template;
- a tool contract fixture;
- a safety-focused agent system prompt;
- a simple integration workflow checklist.

Client-specific docs are available for Claude Desktop, Cursor/IDE agents, and
LangGraph-style agents:

```text
docs/deployment/mcp-claude-desktop.md
docs/deployment/mcp-cursor-agents.md
docs/deployment/mcp-langgraph-agents.md
examples/mcp-agent-docs/
```

They all use the same `skeinrank-mcp` stdio adapter, scoped credentials, offline
smoke test, and proposal-only safety boundary.
