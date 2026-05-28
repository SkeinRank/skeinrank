# Token rotation and scoped agent credentials

Patch 55C adds a safe rotation path for service-account tokens and documents the
least-privilege credential shapes recommended for agent workflows.

The goal is to keep agents proposal-only by default:

```text
agent -> validate/propose/track
reviewer -> approve/reject
admin -> apply/publish/rotate credentials
```

No auto-apply is introduced by this patch.

## Read the scoped-agent credential policy

Admins can inspect the recommended service-account profiles:

```bash
curl http://127.0.0.1:8010/v1/auth/scoped-agent-credentials \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  | python -m json.tool
```

Response schema:

```text
skeinrank.scoped_agent_credentials.v1
```

Recommended profiles:

| Profile | Role | Purpose |
| --- | --- | --- |
| `agent-readonly-validator` | `contributor` | Read runs/reports and validate aliases without submitting proposals. |
| `agent-proposal-writer` | `contributor` | Validate candidates and submit pending suggestions. |
| `agent-tracking-writer` | `contributor` | Register runs and persist tracking metadata. |

All recommended agent credentials use the `contributor` role. They cannot
approve, batch-apply, publish snapshots, or mutate runtime state.

## Create a scoped agent service account

```bash
curl -X POST http://127.0.0.1:8010/v1/auth/service-accounts \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "agent-proposal-writer",
    "display_name": "Agent Proposal Writer",
    "role": "contributor",
    "description": "Validates candidates and creates pending proposals."
  }' \
  | python -m json.tool
```

Then create a scoped token:

```bash
curl -X POST http://127.0.0.1:8010/v1/auth/service-accounts/agent-proposal-writer/tokens \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "agent token v1",
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
  }' \
  | python -m json.tool
```

The plaintext `access_token` is returned once. Store it in a secret manager or a
local uncommitted `.env` file and do not log it.

## Rotate a service-account token

Patch 55C adds:

```http
POST /v1/auth/service-accounts/{account_name}/tokens/{token_id}/rotate
```

Example:

```bash
curl -X POST http://127.0.0.1:8010/v1/auth/service-accounts/agent-proposal-writer/tokens/1/rotate \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "agent token v2",
    "expires_in_days": 90
  }' \
  | python -m json.tool
```

Rotation behavior:

- creates a replacement service-account token;
- copies the old token scopes unless `scopes` is explicitly provided;
- returns the replacement plaintext token once;
- revokes the old token in the same transaction;
- rejects rotation of already revoked tokens;
- rejects rotation through the wrong service-account owner path.

This gives a simple verified rotation path for emergency token replacement and
scheduled credential rotation.

## Safety notes

- Admin role is required to read the scoped credential policy and rotate service
  account tokens.
- The old plaintext token is never returned.
- List endpoints continue to return only token metadata and token prefixes.
- Recommended agent credentials use `contributor`, not `admin`.
- Runtime mutation, batch apply, and snapshot publishing remain outside agent
  credentials.
