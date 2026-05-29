# Blue/green alias-swap operator checklist

Use this checklist with `docs/deployment/blue-green-alias-swap-runbook.md`.

## Before start

- [ ] Application search reads from the serving alias, not a physical index.
- [ ] Binding is enabled and in `write` mode.
- [ ] Binding uses `write_strategy = reindex_alias_swap`.
- [ ] Source index, alias name, and target index are different where required.
- [ ] Target index name is unique for this rollout.
- [ ] Dry-run payloads look correct.
- [ ] Preflight returns `ready = true` and no `blocking_issues`.
- [ ] Warnings are accepted by the operator.

## During rollout

- [ ] Job status is monitored through `GET /v1/governance/elasticsearch/jobs/{job_id}`.
- [ ] `documents_seen`, `documents_enriched`, and `documents_failed` are reviewed.
- [ ] Cancellation is used instead of starting a second job for the same binding.

## After success

- [ ] Job status is `succeeded`.
- [ ] `result_json.rollout.alias_swap_completed` is `true`.
- [ ] `result_json.rollout.new_alias_indices` contains the green index.
- [ ] Search validation passes against the serving alias.
- [ ] Rollback availability is recorded before old-index cleanup.
