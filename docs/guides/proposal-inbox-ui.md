# Proposal Inbox UI

The Proposal Inbox is the review-first UI for agent-submitted terminology changes. It is intentionally separate from the legacy Suggestions/dev workflow and does not provide a broad manual CRUD editor.

## Purpose

Use the Inbox when a reviewer needs to decide whether an agent proposal should be approved or rejected. The screen focuses on the evidence and policy context needed for that decision:

- proposal lifecycle status;
- risk level and apply-policy decision;
- validation findings, warnings, and policy signals;
- saved evidence snapshot metadata and document snippets;
- proposal source and idempotency metadata;
- optional source payload JSON for audit/debugging;
- existing approve/reject actions.

The UI does not auto-apply proposals, publish snapshots, run enrichment jobs, or refresh evidence for every row.

## Detail panel scope

The `AI Inbox` route combines proposal cards with a detail panel so reviewers can inspect a selected proposal without jumping back to the legacy Suggestions screen.

The detail panel includes:

1. **Risk and apply policy** — mirrors backend `skeinrank.apply_policy.v1` output.
2. **Validation findings** — shows blockers, warnings, validation reasons, lifecycle state, and policy signals.
3. **Evidence snapshot** — shows binding/index/query metadata, warnings, matched text, and saved document snippets with safe highlighting.
4. **Source and audit metadata** — shows source name/type, idempotency key, timestamps, and optional source payload JSON.
5. **Review action** — uses the existing approve/reject endpoints and backend optimistic state checks.

## Role behavior

- `admin` and `moderator` users can approve or reject pending proposals.
- `contributor` users can inspect proposals in read-only mode.
- The UI depends on backend role boundaries; it does not grant extra permissions by hiding or showing buttons alone.

## Backend endpoints used

The Inbox uses existing governance API endpoints:

```text
GET  /v1/governance/profiles
GET  /v1/governance/profiles/{profile_name}/suggestions?status=pending
POST /v1/governance/profiles/{profile_name}/suggestions/{suggestion_id}/approve
POST /v1/governance/profiles/{profile_name}/suggestions/{suggestion_id}/reject
```

Evidence refresh remains in the legacy Suggestions/dev workflow for now:

```text
POST /v1/governance/profiles/{profile_name}/suggestions/{suggestion_id}/evidence/refresh
```

