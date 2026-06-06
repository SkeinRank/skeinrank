# Role boundaries for agent, reviewer, and admin workflows

SkeinRank keeps production terminology changes human-in-the-loop. Agents and contributors can inspect context, validate aliases, and create proposals. Reviewers decide whether proposals are acceptable. Admins perform production apply and snapshot publishing operations.

The existing governance roles remain stable:

| Governance role | Operational boundary | Main purpose |
| --- | --- | --- |
| `contributor` | `agent` | Read context, validate candidates, and submit pending proposals. |
| `moderator` | `reviewer` | Review evidence and approve or reject pending proposals. |
| `admin` | `admin` | Apply reviewed batches, publish runtime snapshots, and manage users/tokens. |

## Boundary rules

Agent/contributor boundary:

- may read governance/tool context;
- may validate alias candidates;
- may submit pending proposals;
- must not approve proposals;
- must not reject proposals on behalf of a reviewer;
- must not apply batches or publish snapshots.

Reviewer/moderator boundary:

- may review pending proposals;
- may approve or reject proposals;
- may preview apply batches;
- must not batch-apply proposals;
- must not publish runtime snapshots.

Admin boundary:

- may apply reviewed proposal batches;
- may publish runtime snapshots through apply-batch;
- may start write-mode enrichment jobs and rollback alias-swap jobs;
- may manage users, service accounts, and API tokens.

## API surface

The read-only endpoint below exposes the effective policy and the current caller boundary:

```http
GET /v1/governance/role-boundaries
```

```bash
curl http://127.0.0.1:8010/v1/governance/role-boundaries \
  -H "Authorization: Bearer <token>" \
  | python -m json.tool
```

Response schema:

```text
skeinrank.role_boundaries.v1
```

## Proposal workflow

The intended production path is:

```text
agent/contributor -> suggest pending proposal
reviewer/moderator -> approve or reject proposal
admin -> apply batch and optionally publish snapshot
```

`apply-batch/preview` remains available to reviewers so they can inspect policy, validation status, warnings, blocked items, and risk levels before an admin applies the batch.

## Service tokens

API tokens require explicit scopes. For example:

```text
agent:tools:read
agent:tools:validate
agent:tools:suggest
agent:tools:explain
```

A service token with only `agent:tools:validate` can validate candidates but cannot submit proposals. A token with `agent:tools:suggest` can submit pending proposals, but it still cannot approve, apply, or publish unless the owner role is `admin` and the endpoint allows admin access.

## Safety guarantees

- Agents remain proposal-first by default.
- No auto-apply is enabled by role-boundary metadata.
- Existing role values are unchanged.
- Local development with auth disabled still behaves as `admin` for developer convenience.
- Production deployments should keep auth enabled and use scoped service-account tokens for agents.

## Related docs

- [`apply-policy-risk-levels.md`](apply-policy-risk-levels.md)
- [`token-rotation-scoped-agent-credentials.md`](token-rotation-scoped-agent-credentials.md)
- [`../security/agent-tool-safety.md`](../security/agent-tool-safety.md)
- [`../deployment/security.md`](../deployment/security.md)
