# skeinrank-core

`skeinrank-core` is the lightweight Python SDK and CLI for deterministic local terminology canonicalization.

It is the zero-friction entrypoint for SkeinRank: no Governance API, Elasticsearch, RabbitMQ, Celery, Docker, OpenRouter token, or ML dependencies are required.

## 30-second demo

```python
import skeinrank

print(skeinrank.canonicalize("k8s pg timeout"))
# kubernetes postgresql timeout

print(skeinrank.extract("sev1 on kube after rollout"))
# ['critical incident', 'kubernetes', 'deployment']
```

The module-level helpers use a built-in `platform_ops_demo` dictionary so the first call works without a file. The demo dictionary is small enough to inspect, but expressive enough to show infrastructure, incidents, CI/CD, search, RAG, and context-shaped company language.

The same built-in dictionary also demonstrates why context matters:

```python
import skeinrank

print(skeinrank.canonicalize("pg timeout"))
# postgresql timeout

print(skeinrank.canonicalize("pg layout"))
# page layout

print(skeinrank.canonicalize("pg dashboard"))
# product group
```

CLI from a source checkout:

```bash
poetry run skeinrank canonicalize "k8s pg timeout" --text
poetry run skeinrank extract "sev1 on kube after rollout" --text --compact
```

## Install from a checkout

```bash
cd packages/skeinrank-core
poetry install
poetry run pytest -q
```

The local SDK facade, demo dictionary, CLI, document helpers, and built-in reranking contracts do not require ML dependencies.

## Resilient rerank batches

Candidate validation is strict by default. Empty candidate text, missing fields, invalid identifiers, and malformed payloads raise `ContractError` before scoring.

For ingestion pipelines where an otherwise valid batch can contain blank text, opt in to the narrow `skip_empty_text` policy:

```python
from skeinrank import rerank

result = rerank(
    "kubernetes incident",
    [
        {"id": "runbook", "text": "Kubernetes incident response runbook"},
        {"id": "empty-row", "text": "   "},
    ],
    invalid_candidate_policy="skip_empty_text",
    passport="off",
)

print(result.ranked[0].id)
print(result.candidate_validation.skipped_by_reason)
# {"empty_text": 1}
```

The policy skips only blank string values. A missing `text`, `None`, a non-string value, or an empty `id` still fails the request. If every candidate is skipped, the request also fails. `RerankResult` and `ScoreResult` return `candidate_validation` even when passports are disabled; when a passport is enabled, each skip is also recorded in `passport.warnings`. The same policy is available on `RerankEngine.rerank(...)`, `RerankEngine.score(...)`, `RerankEngine.rerank_many(...)`, and the module-level helpers.

## Public Python facade

Use `SkeinRank` when you want to pass a dictionary in code:

```python
from skeinrank import SkeinRank

sr = SkeinRank({
    "kubernetes": ["k8s", "kube", "kuber"],
    "postgresql": ["pg", "postgres", "psql"],
})

print(sr.canonicalize("kuber timeout on pg"))
# kubernetes timeout on postgresql

print(sr.extract("kuber timeout on pg"))
# ['kubernetes', 'postgresql']
```

Use `explain=True` when you need offsets, slots, and highlighted evidence:

```python
result = sr.extract("k8s rollout uses pg", explain=True)

print(result.canonical_values)
print(result.matches[0].alias)
print(result.matches[0].highlighted_fragment)
```

The same facade can load a full SkeinRank dictionary JSON/YAML file:

```python
from skeinrank import SkeinRank

sr = SkeinRank.from_file("company.dictionary.yaml")
print(sr.canonicalize("k8s rollout uses pg database"))
```


## Built-in demo dictionary and examples

The built-in `platform_ops_demo` dictionary contains more than 30 canonical terms and more than 80 aliases across platform operations, incidents, CI/CD, search, RAG, and SkeinRank concepts. It is intentionally not a production vocabulary; it is a compact first-touch dictionary for demos, tests, tutorials, and screenshots.

Useful demo phrases:

| Input | Output |
| --- | --- |
| `k8s pg timeout` | `kubernetes postgresql timeout` |
| `sev1 on kube after pg migration` | `critical incident on kubernetes after postgresql database migration` |
| `gha rollout hit rmq latency spike` | `github actions`, `deployment`, `message queue`, `latency` |
| `pg layout` | `page layout` |
| `pg dashboard` | `product group` |

Examples live in [`../../examples/sdk`](../../examples/sdk):

- [`zero_friction_demo.py`](../../examples/sdk/zero_friction_demo.py) runs the facade from Python.
- [`platform_ops_demo.dictionary.json`](../../examples/sdk/platform_ops_demo.dictionary.json) exports the built-in dictionary in the public dictionary shape.

## Dictionary-first SDK

The lower-level dictionary SDK remains available for callers that already use the governance export or `skeinrank-migrate` dictionary shape.

```python
from skeinrank import load_dictionary, extract_terms, canonicalize_text

dictionary = load_dictionary("../../examples/migration/console_dictionary.example.json")

result = extract_terms(
    "This instruction helps deploy 500 k8s servers backed by Postgres.",
    dictionary=dictionary,
)

print(result.canonical_values)  # ['kubernetes', 'postgresql']

canonicalized = canonicalize_text(
    "k8s rollout uses pg database",
    dictionary=dictionary,
)
print(canonicalized.text)  # kubernetes rollout uses postgresql database
```

### Extraction/annotation versus replacement

Use `extract_terms(...)` as the default path for prose, documentation, tickets, and other text where grammar must remain untouched. It returns canonical terms, offsets, slots, and highlighted fragments while preserving the original text. This is the extraction/annotation workflow.

Use `canonicalize_text(...)` when deterministic replacement is appropriate, such as search queries, tags, filters, identifiers, or controlled short text. Replacement is intentionally literal: an alias that is a verb while its canonical value is a noun can produce broken prose. `validate_dictionary(...)` reports a `replacement_form_mismatch` warning for conservative English nominalization cases so teams can keep those aliases out of replacement-oriented dictionaries.

Runtime matching applies NFKC compatibility normalization, normalizes common Unicode spaces and dash variants, checks a compact view for zero-width obfuscation such as `k\u200b8s`, and removes bidi controls from the matching view. Returned match offsets still point to the original input. `ExtractionResult` and `CanonicalizedText` expose `unicode_normalized`, `unicode_has_bidi_control`, and `unicode_findings` so callers can surface or block suspicious input.

Stable dictionary exports include:

- `SkeinRank`, `canonicalize(...)`, `extract(...)`, `demo_dictionary(...)`, `demo_dictionary_payload(...)`
- `Dictionary`, `DictionaryTerm`, `DictionaryAlias`, `DictionaryStopListEntry`
- `load_dictionary(...)`, `validate_dictionary(...)`
- `extract_terms(...)`, `canonicalize_text(...)`
- `ExtractionResult`, `TermMatch`, `CanonicalizedText`
- `UnicodeFindingKind`, `UnicodeTextFinding`, `UnicodeNormalizationResult`, `normalize_text_for_matching(...)`
- `DictionaryDraft`, `DraftCandidate`, `DraftFinding`, `EvidenceSnippet`
- `CandidateDiscoveryConfig`, `CandidateDiscoveryReport`, `CandidateScoreBreakdown`, `CandidateTokenizerSignal`, `TokenizerSignalProvider`, `discover_candidates(...)`, `discover_candidates_from_documents(...)`
- `DictionarySuggestionConfig`, `DictionarySuggestionResult`, `suggest_dictionary(...)`, `suggest_dictionary_from_documents(...)`
- `TerminologyDriftReport`, `DriftFinding`, `DriftEvidence`, `DriftSeverity`, `DriftFindingType`
- `DriftDraftConfig`, `DriftDraftConversionSummary`, `DriftDraftResult`, `drift_report_to_dictionary_draft(...)`
- `InvalidCandidatePolicy`, `SkippedCandidate`, `CandidateValidationSummary`

The matcher is deterministic and local. It honors active/deprecated term and alias statuses, profile/global stop lists, applies Unicode-safe matching with original offset mapping, returns offsets, and includes evidence snippets with `<mark>...</mark>` highlights.

## Document text extraction utilities

Local document helpers can extract text before running the SDK matcher. They do not require the Governance API, Elasticsearch, Celery, or a database.

```python
from skeinrank import load_document_text, extract_terms_from_document

text = load_document_text("incident-runbook.md")
result = extract_terms_from_document(
    "incident-runbook.md",
    dictionary="../../examples/migration/console_dictionary.example.json",
)

print(result.document.file_name)
print(result.extraction.canonical_values)
```

Supported formats without extra dependencies:

- text-like files: `.txt`, `.md`, `.rst`, `.log`, `.csv`, `.tsv`, `.json`, `.jsonl`, `.yaml`, `.yml`
- `.html` / `.htm` with scripts/styles ignored
- `.docx` via a small stdlib ZIP/XML reader

PDF extraction is supported when the caller installs `pypdf` in the environment. The core package does not require it by default.

## Local terminology drift reports

Compare a dictionary with local documents to see which significant terms are not covered yet. This is a report-only workflow: it does not create proposals, publish snapshots, change bindings, or mutate runtime state.

```bash
poetry run skeinrank drift scan \
  --dictionary ../../examples/drift-scan/company.dictionary.json \
  --docs ../../examples/drift-scan/docs \
  --stale-min-documents 1 \
  --out ../../examples/drift-scan/drift-report.json \
  --markdown ../../examples/drift-scan/drift-report.md
```

The report uses the versioned `TerminologyDriftReport` schema and includes `alias_drift` findings for uncovered terminology, optional corpus-level `stale_term` findings, optional `binding_lag` findings for pinned-vs-latest snapshot metadata, and conservative `ambiguity_signal` findings when an existing short alias appears in unfamiliar contexts. Stale analysis runs only when the corpus contains at least 20 documents by default; smaller scans record `stale_analysis_status="skipped"` and explain the corpus threshold in JSON and markdown. It also includes evidence snippets and `unknown_alias_rate`. It is intentionally a local terminology drift report, not a real-time monitor or search observability system.

Ambiguity signals are review hints, not automatic meaning changes. Disable them with `--no-ambiguity-signals` when you only want uncovered aliases, stale terms, and binding lag.

Add optional binding metadata when you want the report to show snapshot lag without connecting to the Governance API:

```bash
poetry run skeinrank drift scan \
  --dictionary ../../examples/drift-scan/company.dictionary.json \
  --docs ../../examples/drift-scan/docs \
  --binding-metadata ../../examples/drift-scan/binding-metadata.json
```

```python
from skeinrank import DriftScanConfig, scan_dictionary_drift

report = scan_dictionary_drift(
    dictionary="company.dictionary.json",
    docs=["./docs"],
    config=DriftScanConfig(
        binding_id="infra_incidents_prod",
        pinned_snapshot_version="S42",
        latest_snapshot_version="S47",
        discovery={"min_frequency": 2},
    ),
)

print(report.to_markdown())
```

After review, turn alias-drift findings into a local dictionary draft without mutating production state:

```bash
poetry run skeinrank drift export-draft ../../examples/drift-scan/drift-report.json \
  --out ../../examples/drift-scan/drift.dictionary-draft.json \
  --review ../../examples/drift-scan/drift.dictionary-draft.md \
  --summary ../../examples/drift-scan/drift.conversion-summary.json
```

```python
from skeinrank import drift_report_to_dictionary_draft

result = drift_report_to_dictionary_draft("drift-report.json")
print(result.summary.status)
print(result.summary.skipped_findings_by_type)
print(result.review_markdown())
result.save("drift.dictionary-draft.json")
result.save_summary("drift.conversion-summary.json")
```

Only `alias_drift` findings become draft candidates. Stale terms, binding lag, and ambiguity signals are preserved as review findings so a human can decide whether to create dictionary proposals, context rules, or rollout tasks later. When a report has findings but no `alias_drift` findings, the conversion summary explicitly reports `no_convertible_findings`, the draft remains valid with zero candidates, and the source findings remain visible for review.

See [`../../docs/guides/terminology-drift-report.md`](../../docs/guides/terminology-drift-report.md) and [`../../examples/drift-scan`](../../examples/drift-scan) for the complete local workflow, Python examples, report fields, and safety boundary.

## Local CLI

Validate a dictionary exported from the governance API or used by `skeinrank-migrate`:

```bash
poetry run skeinrank validate-dictionary ../../examples/migration/console_dictionary.example.json
poetry run skeinrank validate-dictionary ../../examples/migration/console_dictionary.example.yaml --json
```

Run zero-config demo extraction/canonicalization:

```bash
poetry run skeinrank extract "k8s rollout uses pg database" --text --compact
poetry run skeinrank canonicalize "k8s rollout uses pg database" --text
```

Print or export the built-in demo dictionary:

```bash
poetry run skeinrank demo-dictionary --compact
poetry run skeinrank demo-dictionary --output ../../examples/sdk/platform_ops_demo.dictionary.json
```

Convert existing term lists into a SkeinRank dictionary candidate:

```bash
poetry run skeinrank import-dictionary ../../examples/import-dictionary/company_terms.csv \
  --name platform_ops_import \
  --out ../../examples/import-dictionary/company_terms.dictionary.json

poetry run skeinrank import-dictionary ../../examples/import-dictionary/es_synonyms.txt \
  --format es-synonyms \
  --name platform_ops_import \
  --out ../../examples/import-dictionary/es_synonyms.dictionary.json
```

The import path accepts simple JSON dictionaries, CSV files with canonical/alias columns, and Elasticsearch/OpenSearch synonym-list files. It writes a local candidate dictionary and prints a review report; it does not mutate governance state, snapshots, bindings, or runtime search.

The review report also runs the imported candidate through the same lightweight dictionary validator used by `validate-dictionary`. Validator findings are surfaced in the import report so risky aliases, runtime collisions, and short ambiguous forms can be reviewed before the candidate is used. Use `--no-validate` when you only want a raw conversion report, or `--strict-validate` when validator errors should block the generated file.

Write a reviewable draft when the imported file should go through an explicit human review step before becoming a runtime dictionary:

```bash
poetry run skeinrank import-dictionary ../../examples/import-dictionary/es_synonyms.txt \
  --format es-synonyms \
  --name platform_ops_import \
  --draft-out ../../examples/import-dictionary/es_synonyms.dictionary-draft.json
```

Drafts keep imported candidates in `proposed` status. In Python, reviewers can inspect the draft, accept candidates, and only then explicitly export a runtime dictionary:

```python
from skeinrank import DictionaryDraft

draft = DictionaryDraft.from_file("company.dictionary-draft.json")
print(draft.review_markdown())

runtime_dictionary = draft.accept_all().to_dictionary()
```

Suggest a reviewable draft directly from local documents when there is no dictionary yet:

```bash
poetry run skeinrank suggest-dictionary ../../examples/suggest-dictionary/docs \
  --profile-name platform_candidates \
  --min-frequency 2 \
  --out ../../examples/suggest-dictionary/platform_candidates.dictionary-draft.json \
  --review ../../examples/suggest-dictionary/platform_candidates.review.md
```

The suggestion path is deterministic and local. It uses the same candidate discovery engine described below, filters known dictionary terms when `--dictionary` is provided, and keeps all suggestions in `proposed` status for review.

Optionally ask OpenRouter to group and name the deterministic candidates. The assistant receives only evidence-backed candidate summaries, not production credentials or runtime state, and returns a reviewable draft. Runtime canonicalization remains deterministic after review:

```bash
export OPENROUTER_API_KEY="..."
export OPENROUTER_MODEL="provider/model"

poetry run skeinrank assist-dictionary ../../examples/agent-dictionary-assistant/docs \
  --model "$OPENROUTER_MODEL" \
  --profile-name platform_assisted_terms \
  --out ../../examples/agent-dictionary-assistant/platform_assisted.dictionary-draft.json \
  --review ../../examples/agent-dictionary-assistant/platform_assisted.review.md
```

The OpenRouter-assisted path does not publish snapshots, mutate bindings, or write runtime dictionaries automatically. It only improves a local draft for human review.

Detailed guides and runnable examples:

- [Import existing dictionaries](../../docs/guides/import-dictionary.md) and [examples/import-dictionary](../../examples/import-dictionary) for CSV, JSON, and Elasticsearch/OpenSearch synonym lists.
- [Agent dictionary assistant](../../docs/guides/agent-dictionary-assistant.md), [examples/suggest-dictionary](../../examples/suggest-dictionary), and [examples/agent-dictionary-assistant](../../examples/agent-dictionary-assistant) for deterministic and optional OpenRouter-assisted draft creation.

Run the example script:

```bash
poetry run python ../../examples/sdk/zero_friction_demo.py
```

Run against a specific dictionary file:

```bash
poetry run skeinrank extract "k8s rollout uses pg database" \
  --text \
  --dictionary ../../examples/migration/console_dictionary.example.json

poetry run skeinrank canonicalize incident-runbook.md \
  --dictionary ../../examples/migration/console_dictionary.example.json \
  --output incident-runbook.canonicalized.txt
```

Extract plain text from a document before matching:

```bash
poetry run skeinrank document-text incident-runbook.docx --output incident-runbook.txt
```

The CLI returns JSON for `extract`, raw text by default for `canonicalize` and `document-text`, and supports `--output`, `--compact`, `--max-matches`, and `--context-chars` where relevant.


## Candidate discovery engine

The core package also includes a deterministic candidate discovery engine for cold-start dictionary suggestions and terminology drift reports. It scans local text, filters known dictionary terms, skips repeated cross-document boilerplate and documentation markup, ranks unmatched technical candidates, and returns evidence snippets for review. Surface extraction handles code-shaped names such as `PAY-1842`, `checkout-v2`, `payment_service`, `payments-core`, compact all-caps aliases, and multi-term phrases up to trigrams. Candidate ranking is explainable: each candidate carries frequency and document-frequency support, surface class, identifier/code-shape signals, lightweight tokenizer-risk signals, background-language penalties, and `context-v2` counts for prose, comments, docstrings, strings, decorators, directives, and code.

`context-v2` distinguishes Markdown fenced and indented code blocks, Markdown inline code, reStructuredText code directives, literal blocks, `literalinclude` directives, and reStructuredText inline literals without importing format parsers. A surface supported by both human-facing prose and code receives a confidence bonus. A surface found only in code remains reviewable but receives a configurable negative context adjustment, which lowers snippet idioms such as `catchup False` without deleting API names that may live mainly in examples. `context_weight=0` disables both the mixed-context bonus and code-only penalty. The tokenizer also preserves intraword ASCII and Unicode apostrophes, avoids contraction fragments such as `doesn t`, and does not build phrase candidates across sentence boundaries. The report groups related candidates into review clusters and records input, scanned, and skipped line counts with skip reasons.

```python
from skeinrank import CandidateDiscoveryConfig, discover_candidates, demo_dictionary

report = discover_candidates(
    [
        {"source": "incident-1.md", "text": "Kubelet OOM after pg migration"},
        {"source": "incident-2.md", "text": "Kubelet OOM returned during deploy"},
    ],
    dictionary=demo_dictionary(),
    config=CandidateDiscoveryConfig(min_frequency=2),
)

for candidate in report.top_candidates(5):
    print(candidate.value, candidate.mention_count, candidate.evidence[0].text)

for cluster in report.top_clusters(3):
    print(cluster.representative_value, cluster.surface_values)
    if candidate.score_breakdown:
        print(
            candidate.score_breakdown.jargon_score,
            candidate.score_breakdown.surface_class,
            candidate.score_breakdown.surface_risk_score,
            candidate.score_breakdown.tokenizer_signal_status,
            candidate.score_breakdown.context_counts,
            candidate.score_breakdown.context_adjustment,
            candidate.score_breakdown.reasons,
        )
```

`background_terms` can be customized when a team has its own baseline vocabulary. This lets discovery rank terms by how unusual they are against the expected background language, while still keeping frequency and evidence as review support.

Tokenizer-aware scoring is optional. Without a tokenizer provider, discovery still emits a real `surface_risk_score` for compact aliases and code-shaped names such as `PAY-1842`, `checkout-v2`, `payment_service`, or `payments-core`, while `oov_score` and `token_fragmentation_score` remain empty. Teams that want model-specific signals can pass a `TokenizerSignalProvider` through `CandidateDiscoveryConfig`; the provider returns `CandidateTokenizerSignal` values and the score breakdown records `tokenizer_signal_status="available"`. The core package does not import embedding tokenizers by default.

Candidate discovery does not create runtime terminology, mutate snapshots, or publish bindings. `CandidateDiscoveryReport.skipped_lines_by_reason` makes filtering visible, and `skip_boilerplate_lines=False` or `skip_rst_markup=False` can be used when a corpus intentionally treats those lines as terminology-bearing content.

Build a reviewable draft from documents in Python:

```python
from skeinrank import suggest_dictionary_from_documents

result = suggest_dictionary_from_documents(
    ["../../examples/suggest-dictionary/docs"],
    config={
        "profile_name": "platform_candidates",
        "discovery": {"min_frequency": 2},
    },
)

result.save("platform_candidates.dictionary-draft.json")
print(result.review_markdown())
```

The draft is a local review artifact, not a production dictionary. Reviewers can accept or reject candidates and explicitly convert accepted candidates for preview when needed.

Use OpenRouter as an optional grouping layer after deterministic discovery:

```python
import os
from skeinrank import build_dictionary_from_docs

result = build_dictionary_from_docs(
    ["../../examples/agent-dictionary-assistant/docs"],
    model=os.environ["OPENROUTER_MODEL"],
)

result.save("platform_assisted.dictionary-draft.json")
print(result.review_markdown())
```

Every assistant candidate must map back to deterministic local evidence. Aliases without evidence are dropped, and candidates without evidence are ignored.


## Terminology drift report schema

The core package exposes a versioned terminology drift report schema for future drift scans and governance review flows. It is intentionally data-only: creating or saving a report does not scan documents, create proposals, publish snapshots, update bindings, or mutate production runtime state.

```python
from skeinrank import (
    DriftEvidence,
    DriftFinding,
    DriftFindingType,
    DriftSeverity,
    TerminologyDriftReport,
)

report = TerminologyDriftReport(
    profile_name="infra_incidents",
    binding_id="infra_incidents_prod",
    pinned_snapshot_version="S42",
    latest_snapshot_version="S47",
    metrics={"unknown_alias_rate": 0.118},
    findings=[
        DriftFinding(
            finding_type=DriftFindingType.ALIAS_DRIFT,
            severity=DriftSeverity.WARN,
            title="New candidate alias detected",
            value="kubelet oom",
            evidence=[
                DriftEvidence(
                    source="incident-1.md",
                    line=7,
                    text="Kubelet OOM after the node pool upgrade.",
                )
            ],
        )
    ],
)

print(report.summary().unknown_alias_rate)
print(report.to_markdown())
report.save("terminology-drift-report.json")
```

The schema currently covers review signals for new unmatched aliases, stale terms, binding snapshot lag, and ambiguity signals. Later scanner commands can emit this report shape while keeping the same review-first principle: detect automatically, approve manually, serve deterministically.

## Attribute extraction and enrichment

The older attribute/profile API is still available for advanced local enrichment workflows.

```python
from skeinrank import build_attribute_profile, enrich_texts

profile = build_attribute_profile(
    profile_id="company_terms",
    aliases={
        "kubernetes": ["k8s", "kube", "kuber"],
        "postgresql": ["pg", "postgres", "psql"],
    },
    slots={
        "kubernetes": "TOOL",
        "postgresql": "DB",
    },
    snapshot_version="company_terms@v1",
)

rows = enrich_texts(
    [
        {"id": "doc-1", "text": "k8s timeout after upgrade"},
        {"id": "doc-2", "text": "pg latency spike"},
    ],
    profile=profile,
)

print(rows[0]["canonical_values"])
```

Use this layer when you need profile templates, fuzzy alias fallback, richer passport/debug traces, or JSONL enrichment helpers.

## Publishing checklist

The package is published through the manual `publish-skeinrank-core` GitHub Actions workflow. The recommended flow is:

1. Build and test locally.
2. Publish to TestPyPI.
3. Install from TestPyPI in a clean environment.
4. Publish to PyPI only after the TestPyPI smoke test passes.

Local packaging checks:

```bash
poetry install
poetry run pytest -q
poetry build
poetry run python -m pip install --upgrade twine
poetry run twine check dist/*
```

See [`docs/PUBLISHING.md`](docs/PUBLISHING.md) for the full release checklist.

## Public API policy

Only symbols re-exported from `skeinrank.__init__` should be treated as stable public API. Internal modules may change without notice.
