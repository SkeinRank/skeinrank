# Apply policy and proposal risk levels

Patch 55A adds an additive, read-only apply-policy layer for proposal review.
It does not add database columns or change how proposals are applied. Instead,
new proposals and tool validations include a policy payload inside the existing
`validation_summary` JSON and expose the same information on proposal responses.

## Schema

Policy payloads use:

```text
skeinrank.apply_policy.v1
```

The policy is stored at:

```json
{
  "validation_summary": {
    "risk_level": "low",
    "apply_policy_decision": "batch_approve_allowed",
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
    }
  }
}
```

The same payload is also exposed as `SuggestionResponse.apply_policy`, with a
shortcut `risk_level` field for UI tables and operator reports.

## Risk levels

| Risk level | Meaning | Default decision |
|---|---|---|
| `low` | Validation passed, confidence is high enough, and no risk flags were observed. | `batch_approve_allowed` |
| `medium` | Validation warning/unknown, lower confidence, short alias, or non-blocking risk flags. | `review_required` |
| `high` | Validation blocked, blocked checks, high-risk flags, very short alias, or very low confidence. | `admin_or_reject` |

`auto_apply_allowed` is always `false` in 55A. This patch prepares the policy
surface for later role-boundary and safe-apply work; it does not enable fully
autonomous apply.

## API surfaces

The following responses now include `risk_level` and `apply_policy`:

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

## Safety

55A is intentionally conservative:

- no migrations;
- no DB model changes;
- no UI changes;
- no OpenRouter calls;
- no Elasticsearch calls;
- no proposal submit/apply behavior changes;
- no snapshot publishing behavior changes.

Existing validation gates still control actual apply behavior. Blocked proposals
remain blocked. Warning proposals still require explicit `allow_warnings: true`.
The policy layer gives reviewers and future UI/API consumers a stable risk
classification before later production-safety patches add stricter role
boundaries.
