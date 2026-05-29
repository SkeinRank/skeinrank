# MCP agent workflow checklist

Use this checklist when connecting an MCP-capable agent to SkeinRank.

## 1. Discover context

Call:

```text
skeinrank_list_bindings
```

Select the correct `binding_id` for the user workspace, search surface, or index
alias. Use `profile_name` only for preview/development flows.

## 2. Explain before proposing

Call:

```text
skeinrank_explain_query
```

Use this to understand whether the current snapshot already canonicalizes the
candidate surface form.

## 3. Validate candidate

Call:

```text
skeinrank_validate_alias
```

Stop if validation returns blocking issues, low confidence, or ambiguity that
requires a human reviewer.

## 4. Submit proposal

Call:

```text
skeinrank_submit_alias_proposal
```

Include:

- `binding_id` when available;
- `canonical_value`;
- `alias_value`;
- `slot`;
- `confidence`;
- evidence in `context` or `source_payload`;
- a stable `idempotency_key`.

## 5. Track review status

Call:

```text
skeinrank_get_proposal_status
```

A submitted proposal is not live. Runtime changes require review, apply, and
snapshot publication through the existing SkeinRank governance flow.
