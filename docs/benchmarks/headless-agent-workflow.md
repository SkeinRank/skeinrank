# Headless agent workflow benchmark

The headless agent workflow benchmark is the stable offline quality gate for
SkeinRank's governed proposal lifecycle. It answers a question that ordinary
unit tests cannot answer on their own:

```text
Did the headless agent workflow become better, worse, or noisier over time?
```

The benchmark is deterministic and offline. It does not call OpenRouter, does
not require Elasticsearch, and does not depend on the UI. It uses a dry-run
binding as the runtime context and exercises the database-backed governance
workflow end to end.

## What it covers

The default fixture lives in `examples/benchmarks/platform_ops_v1` and includes:

- a seed dictionary for `platform_ops_benchmark`;
- synthetic platform operations documents;
- incidents, runbooks, support tickets, and noisy docs;
- previously seen unchanged documents;
- changed documents that must be revisited;
- new aliases such as `rmq`, `otel`, `pg`, `prom`, `lk`, `ns`, `svc`, `redis-sentinel`, `redis-cluster`, `slo`, and `es`;
- idempotent existing alias cases for `kube`, `k8s`, `postgres`, and `elastic`;
- stop-list blocked noisy aliases such as `app`, `error`, `job`, and `api`;
- golden runtime queries after proposals are applied;
- quality thresholds for precision-like, recall-like, noise, skipped documents, blocked aliases, and snapshot creation.

The workflow is:

```text
seed dictionary
→ create dry-run binding
→ create prior run visits
→ create current benchmark run
→ record document visits
→ record candidate observations and evidence windows
→ record deterministic LLM reviews
→ record proposal attempts
→ create governed suggestions
→ approve/apply safe proposals
→ publish binding runtime snapshot
→ evaluate golden runtime queries
→ write JSON report
```

## Commands

Run from the repository root:

```bash
make benchmark-reset
make benchmark-seed
make benchmark-eval
make benchmark-report
make benchmark-clean
```

The default benchmark DB is the package-local SQLite database used by the
governance API CLI. Override it when you want an isolated run:

```bash
make benchmark-seed BENCHMARK_DATABASE_URL=sqlite:////tmp/skeinrank-benchmark.db
make benchmark-eval BENCHMARK_DATABASE_URL=sqlite:////tmp/skeinrank-benchmark.db
```

Direct CLI usage is also available:

```bash
cd packages/skeinrank-governance-api
poetry run python -m skeinrank_governance_api.benchmark seed --reset
poetry run python -m skeinrank_governance_api.benchmark eval \
  --out ../../examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-report.json
poetry run python -m skeinrank_governance_api.benchmark report \
  --file ../../examples/benchmarks/platform_ops_v1/reports/platform_ops_v1-report.json
```

The Poetry script name is:

```bash
poetry run skeinrank-governance-benchmark seed --reset
```

## Report signals

The report schema is `skeinrank.benchmark_report.v1`. Important fields:

- `status` — `passed` or `failed`;
- `scores.expected_alias_recall` — whether expected aliases reached runtime;
- `scores.runtime_canonicalization_accuracy` — golden query match accuracy;
- `scores.unexpected_proposals` — number of unexpected proposal aliases;
- `scores.proposal_precision_like` — expected proposals divided by created proposal aliases;
- `scores.proposal_recall_like` / `scores.alias_coverage` — expected aliases that reached runtime;
- `scores.noise_rate` — unexpected proposal aliases divided by created proposal aliases;
- `counts.visit_statuses` — document visit decisions such as `unchanged_seen`;
- `counts.idempotent_noops` — existing aliases correctly treated as no-ops;
- `quality` — quality report with proposal counts, warnings, blocked aliases, snapshot status, and quality gates;
- `checks[]` — named pass/fail checks with details.

A successful report should show:

```text
expected_alias_recall = 1.0
runtime_canonicalization_accuracy = 1.0
proposal_precision_like = 1.0
unexpected_proposals = 0
noise_rate = 0.0
```

## Quality report

The quality report turns the fixture into an operator-facing regression signal.
It compares proposal counts, validator outcomes, candidate-filter behavior,
expected alias coverage, blocked noisy aliases, idempotent no-ops, runtime
canonicalization, and snapshot publication.

The report includes:

```text
proposal_precision_like
proposal_recall_like
accepted_expected_proposals
missed_expected_proposals
unexpected_created_proposals
blocked_proposals_count
blocked_alias_recall
warning_proposals_count
expected_warning_aliases_count
missing_warning_aliases
idempotent_noops_count
agent_revisited_documents_count
agent_skipped_unchanged_documents_count
runtime_canonicalization_accuracy
snapshot_created
query_plan_matches_expected
alias_coverage
noise_rate
quality_gates[]
proposal_quality.rates.evidence_window_coverage
proposal_quality.rates.submission_rate
proposal_quality.rates.approval_rate
proposal_quality.breakdowns.by_alias_class
proposal_quality.breakdowns.by_outcome
proposal_quality.alias_outcomes[]
agent_decision_diagnostics.document_decisions[]
agent_decision_diagnostics.candidate_decisions[]
agent_decision_diagnostics.skipped_candidate_decisions[]
agent_decision_diagnostics.missing_alias_diagnostics[]
```

These signals make prompt, rule, and validator changes measurable. A change
should not increase unexpected aliases, reduce skipped unchanged documents, or
reduce runtime canonicalization accuracy.

## Proposal quality metrics

The top-level `proposal_quality` section uses schema
`skeinrank.proposal_quality_metrics.v1`. It is designed for tuning agent
behavior, not just checking whether the benchmark passed. The section includes:

- `totals` — candidate observations, LLM reviews, proposal attempts, submitted proposals, approved suggestions, and idempotent no-ops;
- `rates` — precision-like, recall-like, submission, approval, blocked, warning, idempotent, evidence-window, LLM-review, and proposal-attempt coverage;
- `coverage` — expected, missed, blocked, warning, and idempotent alias coverage;
- `breakdowns` — attempts by status, validation status, slot, expected action, source type, alias class, and outcome;
- `aliases` — accepted, missed, unexpected, blocked, warning, and idempotent alias lists;
- `alias_outcomes[]` — per-alias rows with source id, slot, validation status, outcome, confidence, submission state, and evidence window count;
- `quality_gates[]` — proposal-quality gates that are also included in the report-level `checks[]` list.

Useful metrics for regression tracking:

```text
proposal_quality.rates.proposal_precision_like
proposal_quality.rates.proposal_recall_like
proposal_quality.rates.evidence_window_coverage
proposal_quality.rates.proposal_attempt_coverage
proposal_quality.coverage.blocked_missing
proposal_quality.coverage.idempotent_missing
proposal_quality.breakdowns.by_outcome
proposal_quality.alias_outcomes[]
agent_decision_diagnostics.document_decisions[]
agent_decision_diagnostics.candidate_decisions[]
agent_decision_diagnostics.skipped_candidate_decisions[]
agent_decision_diagnostics.missing_alias_diagnostics[]
```

These metrics answer questions such as: did a prompt change create more
unexpected aliases, did validators block the intended noisy candidates, did
idempotent aliases stay no-op, and did every candidate retain evidence for
reviewer inspection?

## Agent decision diagnostics

The top-level `agent_decision_diagnostics` section uses schema
`skeinrank.agent_decision_diagnostics.v1`. It explains why the deterministic
agent scanned, skipped, blocked, submitted, or treated each candidate as
idempotent.

The section includes:

- `summary` — document/candidate decision counts and decision-reason coverage;
- `document_decisions[]` — per-source scan/skip/revisit decision, expected state, visit status, declared candidates, observed candidates, and proposal attempts;
- `candidate_decisions[]` — per-alias decision rows with source id, expected action, model action, validator reason, compact validation checks, confidence, submission state, and evidence summary;
- `skipped_candidate_decisions[]` — candidates skipped before review because their source document was unchanged;
- `missing_alias_diagnostics[]` — explanations for expected/idempotent aliases missing from proposal-quality coverage, for example `elastic` being intentionally absent because `runbook-elastic-unchanged` was skipped as unchanged;
- `quality_gates[]` — diagnostic gates for decision-reason coverage and explained missing aliases.

Useful fields:

```text
agent_decision_diagnostics.summary.decision_reason_coverage
agent_decision_diagnostics.summary.skipped_reason_coverage
agent_decision_diagnostics.document_decisions[]
agent_decision_diagnostics.candidate_decisions[].decision_reason
agent_decision_diagnostics.candidate_decisions[].validator_reason
agent_decision_diagnostics.missing_alias_diagnostics[]
```

This makes benchmark failures actionable: instead of seeing only that an alias
was missed, the report can say whether it was skipped due to unchanged content,
blocked by a validator, treated as an existing alias, or never observed.

## Retrieval evaluation baseline

The retrieval evaluator compares a literal lexical baseline with a
SkeinRank-expanded run. The fixture includes `retrieval_queries.jsonl`,
`qrels.jsonl`, `hard_negatives.jsonl`, query-hygiene scoring,
`generic_token_noise@10`, and `corpus_manifest.json` for the default
500-document corpus. The report includes `NDCG@10`, `MRR@10`, `Recall@10`,
`Precision@10`, `hard_negative_leakage@10`, `generic_token_noise@10`, and
per-query deltas.

```bash
make benchmark-retrieval-plan
make benchmark-retrieval-eval
make benchmark-retrieval-report
make benchmark-retrieval-clean
```

This quality layer checks whether canonicalization and alias expansion improve
ranking, not only whether proposals and snapshots are correct. See
[`retrieval-eval-baseline.md`](retrieval-eval-baseline.md).

## Why OpenRouter is not used here

This benchmark is the stable CI/local layer. It proves the backend contract and
lifecycle without external latency, cost, or nondeterministic model output.

Live OpenRouter execution belongs in the opt-in live pilot layer. That mode
should stay cost-bounded and dry-run by default. See
[`openrouter-live-pilot.md`](openrouter-live-pilot.md).

## Full-stack integration layer

The containerized stack benchmark uses the same `platform_ops_v1` fixture, but
runs against Docker Compose PostgreSQL, Governance API, and Elasticsearch
evidence endpoints:

```bash
make benchmark-stack-run
```

See [`containerized-benchmark-integration.md`](containerized-benchmark-integration.md).
