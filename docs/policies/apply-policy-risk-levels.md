# Apply policy and proposal risk levels

SkeinRank classifies terminology proposals before they can be applied to runtime snapshots. The apply-policy layer gives reviewers, admins, UI tables, agent tools, and operator reports the same risk vocabulary without changing the proposal data model or bypassing existing validation gates.

The policy is intentionally conservative: it helps humans decide what can move through batch approval, what needs explicit review, and what should be handled by an admin or rejected.

## Policy contract

Policy payloads use this schema version:

```text
skeinrank.apply_policy.v1
```

A proposal response exposes the policy at `apply_policy` and mirrors the same payload inside `validation_summary` for compatibility with existing review flows:

```json
{
  "risk_level": "low",
  "apply_policy": {
    "schema_version": "skeinrank.apply_policy.v1",
    "risk_level": "low",
    "decision": "batch_approve_allowed",
    "can_batch_apply": true,
    "requires_reviewer": true,
    "requires_admin": false,
    "requires_warning_override": false,
    "auto_apply_allowed": false,
    "reasons": ["validation_passed_low_risk_thresholds"],
    "signals": {}
  },
  "validation_summary": {
    "risk_level": "low",
    "apply_policy_decision": "batch_approve_allowed",
    "apply_policy": {
      "schema_version": "skeinrank.apply_policy.v1"
    }
  }
}
```

`auto_apply_allowed` is always `false`. SkeinRank can classify and preview risk, but production terminology changes still require the configured human review/apply workflow.

## Risk levels

| Risk level | Meaning | Default decision |
| --- | --- | --- |
| `low` | Validation passed, confidence is high enough, and no risk flags were observed. | `batch_approve_allowed` |
| `medium` | Validation produced warnings, confidence is lower, alias text is short, or non-blocking risk flags were observed. | `review_required` |
| `high` | Validation is blocked, high-risk flags are present, alias text is very short, or confidence is too low. | `admin_or_reject` |

## Decision semantics

| Decision | Meaning |
| --- | --- |
| `batch_approve_allowed` | The item can be included in a reviewer-approved batch when other validation gates pass. |
| `review_required` | A reviewer should inspect evidence, warnings, and risk reasons before the item moves forward. |
| `admin_or_reject` | The item is unsafe for normal batch approval and should be handled by an admin or rejected. |

The decision is advisory for workflow routing. Existing apply gates still enforce blocked checks, warning overrides, reviewer approval, and admin-only operations.

## API surfaces

These responses include `risk_level` and `apply_policy`:

- `POST /v1/governance/profiles/{profile_name}/suggestions`
- `GET /v1/governance/profiles/{profile_name}/suggestions`
- `POST /v1/tools/validate-alias`
- `POST /v1/tools/suggest-alias`

Batch preview items additionally include:

- `risk_level`
- `apply_policy`
- `policy_can_batch_apply`
- `policy_requires_admin`
- `policy_reasons`

## Safe review flow

A typical governed flow is:

```text
agent or contributor -> create proposal
reviewer -> inspect validation summary and apply policy
reviewer -> approve low-risk items or request more evidence
admin -> apply reviewed batch and publish runtime snapshot when ready
```

High-risk proposals should not be normalized away automatically. Keep the evidence and risk reasons visible so reviewers can understand whether the alias is ambiguous, unsafe, conflicting, or unsupported.

## Safety guarantees

- The policy layer does not apply proposals by itself.
- The policy layer does not publish snapshots.
- The policy layer does not call model providers or search providers.
- Blocked proposals remain blocked.
- Warning proposals still require explicit warning override where applicable.
- Existing validation gates remain the source of truth for apply behavior.

## Related docs

- [`role-boundaries.md`](role-boundaries.md)
- [`token-rotation-scoped-agent-credentials.md`](token-rotation-scoped-agent-credentials.md)
- [`../security/agent-tool-safety.md`](../security/agent-tool-safety.md)
- [`../security/prompt-like-detector.md`](../security/prompt-like-detector.md)
