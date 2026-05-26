# Headless agent workflow benchmark

Patch 48A adds a deterministic benchmark for the governed agent proposal workflow.
It is designed to answer a different question than ordinary unit tests:

```text
Did the headless agent workflow become better, worse, or noisier over time?
```

The benchmark is intentionally offline. It does not call OpenRouter and it does
not require Elasticsearch. It uses a dry-run binding as the runtime context and
exercises the database-backed governance workflow end to end.

## What it covers

The default fixture lives in `examples/benchmarks/platform_ops_v1` and includes:

- a seed dictionary for `platform_ops_benchmark`;
- 50 synthetic platform operations documents;
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
- `quality` — expanded 49A quality report with proposal counts, warnings, blocked aliases, snapshot status, and quality gates;
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

Patch 49A expands the benchmark from a small happy-path fixture into a 50-document quality benchmark. Patch 49B adds proposal-level quality metrics so prompt, validator, and candidate-filter changes can be compared by alias class, source type, expected action, and outcome. Patch 49C adds agent decision diagnostics that explain why each document/candidate was scanned, skipped, blocked, submitted, or treated as idempotent. The report includes:

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

These signals are intended to make prompt/rule/validator changes measurable: a patch should not increase unexpected aliases, reduce skipped unchanged documents, or reduce runtime canonicalization accuracy.

## Proposal quality metrics

Patch 49B adds a top-level `proposal_quality` section with schema `skeinrank.proposal_quality_metrics.v1`. It is designed for tuning agent behavior, not just checking whether the benchmark passed. The section includes:

- `totals` — candidate observations, LLM reviews, proposal attempts, submitted proposals, approved suggestions, and idempotent no-ops;
- `rates` — precision-like, recall-like, submission, approval, blocked, warning, idempotent, evidence-window, LLM-review, and proposal-attempt coverage;
- `coverage` — expected, missed, blocked, warning, and idempotent alias coverage;
- `breakdowns` — attempts by status, validation status, slot, expected action, source type, alias class, and outcome;
- `aliases` — accepted, missed, unexpected, blocked, warning, and idempotent alias lists;
- `alias_outcomes[]` — per-alias rows with source id, slot, validation status, outcome, confidence, submission state, and evidence window count;
- `quality_gates[]` — proposal-quality gates that are also included in the report-level `checks[]` list.

Useful 49B metrics for regression tracking:

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

These metrics answer questions like: did a prompt change create more unexpected aliases, did validators block the intended noisy candidates, did idempotent aliases stay no-op, and did every candidate retain evidence for reviewer inspection?


## Agent decision diagnostics

Patch 49C adds a top-level `agent_decision_diagnostics` section with schema `skeinrank.agent_decision_diagnostics.v1`. It is designed for the next tuning loop: when proposal quality changes, operators can inspect *why* the deterministic agent made each decision.

The section includes:

- `summary` — document/candidate decision counts and decision-reason coverage;
- `document_decisions[]` — per-source scan/skip/revisit decision, expected state, visit status, declared candidates, observed candidates, and proposal attempts;
- `candidate_decisions[]` — per-alias decision rows with source id, expected action, model action, validator reason, compact validation checks, confidence, submission state, and evidence summary;
- `skipped_candidate_decisions[]` — candidates skipped before review because their source document was unchanged;
- `missing_alias_diagnostics[]` — explanations for expected/idempotent aliases missing from proposal-quality coverage, for example `elastic` being intentionally absent because `runbook-elastic-unchanged` was skipped as unchanged;
- `quality_gates[]` — diagnostic gates for decision-reason coverage and explained missing aliases.

Useful 49C fields:

```text
agent_decision_diagnostics.summary.decision_reason_coverage
agent_decision_diagnostics.summary.skipped_reason_coverage
agent_decision_diagnostics.document_decisions[]
agent_decision_diagnostics.candidate_decisions[].decision_reason
agent_decision_diagnostics.candidate_decisions[].validator_reason
agent_decision_diagnostics.missing_alias_diagnostics[]
```

This makes benchmark failures actionable: instead of seeing only that an alias was missed, the report can say whether it was skipped due to unchanged content, blocked by a validator, treated as an existing alias, or never observed.


## Retrieval evaluation baseline

Patch 50A adds `retrieval_queries.jsonl` and `qrels.jsonl` for the same 50-document fixture. The retrieval evaluator compares a literal lexical baseline with a SkeinRank-expanded run and reports `NDCG@10`, `MRR@10`, `Recall@10`, `Precision@10`, and per-query deltas.

```bash
make benchmark-retrieval-plan
make benchmark-retrieval-eval
make benchmark-retrieval-report
make benchmark-retrieval-clean
```

This is the first quality layer that checks whether canonicalization/alias expansion improves ranking, not only whether proposals and snapshots are correct. See `docs/benchmarks/retrieval-eval-baseline.md`.

## Why OpenRouter is not used here

48A is the stable CI/local layer. It proves the backend contract and lifecycle
without external latency, cost, or nondeterministic model output.

Live OpenRouter execution belongs in the next layer:

```text
48B — OpenRouter live agent pilot mode
```

That mode should stay opt-in, cost-bounded, and dry-run by default.

## Full-stack integration layer

The next layer is the 48C containerized stack benchmark. It uses the same `platform_ops_v1` fixture, but runs against Docker Compose PostgreSQL, Governance API, and Elasticsearch evidence endpoints:

```bash
make benchmark-stack-run
```

See `docs/benchmarks/containerized-benchmark-integration.md`.
