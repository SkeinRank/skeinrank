# LangGraph-style agent policy for SkeinRank MCP

The agent may discover terminology candidates, but SkeinRank remains the control
plane and humans remain in the review loop.

Allowed tool chain:

```text
skeinrank_list_bindings
skeinrank_explain_query
skeinrank_validate_alias
skeinrank_submit_alias_proposal
skeinrank_get_proposal_status
```

Policy:

- Resolve binding context first.
- Treat `profile_name` as a preview fallback when no binding is known.
- Validate before proposing.
- Do not submit proposals when validation returns blocking issues.
- Include context/evidence for every proposal.
- Stop when the Governance API is unavailable.
- Never fabricate proposal ids, approval state, snapshot ids, or runtime status.
- Runtime mutation happens later through review, snapshot publication, and GitOps.
