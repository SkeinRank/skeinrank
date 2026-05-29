# Blue/green alias-swap examples

These examples support the 61B operator runbook:

- `preflight-request.json` — read-only safety plan request for one binding;
- `start-job-request.json` — job start request with the same safe shape;
- `rollback-request.json` — conservative rollback request body;
- `operator-checklist.md` — short manual checklist for production rollouts.

Runbook: [`docs/deployment/blue-green-alias-swap-runbook.md`](../../docs/deployment/blue-green-alias-swap-runbook.md).

The examples use only existing governance API endpoints. There is no standalone
alias-swap endpoint; the swap happens inside a successful `reindex_alias_swap`
enrichment job.
