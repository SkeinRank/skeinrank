import { useMutation, useQuery } from "@tanstack/react-query";
import { type FormEvent, useEffect, useMemo, useState } from "react";

import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { buildRuntimeQueryPlan, listElasticsearchBindings, searchRuntimeDocuments } from "../lib/api";
import type { ElasticsearchBinding, RuntimeQueryPlanResponse, RuntimeSearchResponse } from "../types";

const defaultQuery = "k8s pg timeout";

export function SearchPlaygroundPage() {
  const bindingsQuery = useQuery({
    queryKey: ["elasticsearch-bindings", "all"],
    queryFn: () => listElasticsearchBindings(),
  });
  const [selectedBindingId, setSelectedBindingId] = useState<number | null>(null);
  const [queryText, setQueryText] = useState(defaultQuery);
  const [size, setSize] = useState("10");
  const [canonicalBoost, setCanonicalBoost] = useState("3");
  const [activeResult, setActiveResult] = useState<RuntimeQueryPlanResponse | RuntimeSearchResponse | null>(null);
  const [activeMode, setActiveMode] = useState<"plan" | "search" | null>(null);

  const bindings = useMemo(() => bindingsQuery.data ?? [], [bindingsQuery.data]);
  const effectiveBindingId = selectedBindingId ?? bindings[0]?.id ?? null;

  useEffect(() => {
    if (bindings.length === 0) {
      setSelectedBindingId(null);
      return;
    }
    if (!selectedBindingId || !bindings.some((binding) => binding.id === selectedBindingId)) {
      setSelectedBindingId(bindings[0].id);
    }
  }, [bindings, selectedBindingId]);

  const selectedBinding = useMemo(
    () => bindings.find((binding) => binding.id === effectiveBindingId) ?? null,
    [bindings, effectiveBindingId],
  );

  const queryPlanMutation = useMutation({
    mutationFn: () =>
      buildRuntimeQueryPlan({
        binding_id: effectiveBindingId,
        query: queryText.trim(),
        size: parseInteger(size, 10),
        canonical_boost: parseFloatOrDefault(canonicalBoost, 3),
        include_evidence: true,
      }),
    onSuccess: (result) => {
      setActiveMode("plan");
      setActiveResult(result);
    },
  });

  const searchMutation = useMutation({
    mutationFn: () =>
      searchRuntimeDocuments({
        binding_id: effectiveBindingId,
        query: queryText.trim(),
        size: parseInteger(size, 10),
        canonical_boost: parseFloatOrDefault(canonicalBoost, 3),
        include_evidence: true,
        include_source: true,
      }),
    onSuccess: (result) => {
      setActiveMode("search");
      setActiveResult(result);
    },
  });

  const canSubmit = Boolean(effectiveBindingId) && queryText.trim().length > 0;
  const isSubmitting = queryPlanMutation.isPending || searchMutation.isPending;
  const errorMessage = errorText(queryPlanMutation.error) ?? errorText(searchMutation.error);

  async function handlePlanSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }
    await queryPlanMutation.mutateAsync();
  }

  async function handleSearchClick() {
    if (!canSubmit) {
      return;
    }
    await searchMutation.mutateAsync();
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>Runtime search playground</CardTitle>
              <CardDescription>Test a binding with a real query and see the canonicalized result first.</CardDescription>
            </div>
            <Badge>{selectedBinding ? selectedBinding.snapshot_status ?? "uninitialized" : "no binding"}</Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <form className="space-y-4" onSubmit={handlePlanSubmit}>
            <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_120px_150px]">
              <label className="space-y-1 text-sm font-medium text-slate-700 dark:text-slate-200">
                Binding
                <select
                  className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:focus:border-slate-500 dark:focus:ring-slate-800"
                  disabled={bindingsQuery.isLoading || bindings.length === 0}
                  onChange={(event) => {
                    setSelectedBindingId(Number(event.target.value));
                    setActiveResult(null);
                    setActiveMode(null);
                  }}
                  value={effectiveBindingId ?? ""}
                >
                  {bindings.length === 0 ? <option value="">No bindings available</option> : null}
                  {bindings.map((binding) => (
                    <option key={binding.id} value={binding.id}>
                      {bindingOptionLabel(binding)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="space-y-1 text-sm font-medium text-slate-700 dark:text-slate-200">
                Size
                <Input
                  aria-label="Search size"
                  inputMode="numeric"
                  max="100"
                  min="1"
                  onChange={(event) => setSize(event.target.value)}
                  type="number"
                  value={size}
                />
              </label>
              <label className="space-y-1 text-sm font-medium text-slate-700 dark:text-slate-200">
                Canonical boost
                <Input
                  aria-label="Canonical boost"
                  inputMode="decimal"
                  max="100"
                  min="0"
                  onChange={(event) => setCanonicalBoost(event.target.value)}
                  step="0.5"
                  type="number"
                  value={canonicalBoost}
                />
              </label>
            </div>

            <label className="space-y-1 text-sm font-medium text-slate-700 dark:text-slate-200">
              Query
              <textarea
                className="min-h-24 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-slate-400 focus:ring-2 focus:ring-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:border-slate-500 dark:focus:ring-slate-800"
                onChange={(event) => setQueryText(event.target.value)}
                placeholder="k8s pg timeout"
                value={queryText}
              />
            </label>

            {selectedBinding ? <SelectedBindingChips binding={selectedBinding} /> : null}

            {bindings.length === 0 ? (
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
                Create an Elasticsearch binding first. Search Playground needs a binding to resolve profile, fields, index, and runtime snapshot.
              </div>
            ) : null}

            {errorMessage ? (
              <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200">
                {errorMessage}
              </div>
            ) : null}

            <div className="flex flex-wrap gap-2">
              <Button disabled={!canSubmit || isSubmitting} type="submit">
                Preview query plan
              </Button>
              <Button disabled={!canSubmit || isSubmitting} onClick={handleSearchClick} type="button" variant="secondary">
                Run search
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="space-y-5">
          <ResultPanel mode={activeMode} result={activeResult} />
        </div>
        <aside className="space-y-5">
          <BindingContextCard binding={selectedBinding} isLoading={bindingsQuery.isLoading} />
          <QuickChecksCard />
        </aside>
      </div>
    </div>
  );
}

function bindingOptionLabel(binding: ElasticsearchBinding) {
  const discriminator = binding.filter_field ? ` · Scope: ${binding.filter_field}=${binding.filter_value ?? "*"}` : "";
  return `Binding: ${binding.name} · Profile: ${binding.profile_name} · Index: ${binding.index_name}${discriminator}`;
}

function SelectedBindingChips({ binding }: { binding: ElasticsearchBinding }) {
  return (
    <div className="flex flex-wrap gap-2 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs dark:border-slate-800 dark:bg-slate-950/60">
      <ContextChip label="Binding" value={binding.name} className="bg-indigo-50 text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-200" />
      <ContextChip label="Profile" value={binding.profile_name} className="bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-200" />
      <ContextChip label="Index" value={binding.index_name} className="bg-sky-50 text-sky-700 dark:bg-sky-950/60 dark:text-sky-200" />
      <ContextChip
        label="Scope"
        value={binding.filter_field ? `${binding.filter_field}=${binding.filter_value ?? "*"}` : "all docs"}
        className="bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-200"
      />
      <ContextChip
        label="Snapshot"
        value={binding.last_successful_snapshot_version ?? binding.snapshot_status ?? "uninitialized"}
        className="bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200"
      />
    </div>
  );
}

function ContextChip({ className, label, value }: { className?: string; label: string; value: string }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 font-medium ${className ?? ""}`}>
      <span className="uppercase tracking-wide opacity-70">{label}</span>
      <span>{value || "-"}</span>
    </span>
  );
}

function BindingContextCard({ binding, isLoading }: { binding: ElasticsearchBinding | null; isLoading: boolean }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Binding context</CardTitle>
        <CardDescription>Runtime search should use binding context, not a loose profile.</CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="text-sm text-slate-500 dark:text-slate-400">Loading bindings...</div>
        ) : binding ? (
          <div className="space-y-4">
            <div>
              <div className="flex items-center gap-2">
                <div className="text-base font-semibold text-slate-950 dark:text-slate-50">{binding.name}</div>
                <Badge>{binding.snapshot_status ?? "uninitialized"}</Badge>
              </div>
              <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                {binding.profile_name} → {binding.index_name}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <InfoBox label="Binding ID" value={`#${binding.id}`} />
              <InfoBox label="Target field" value={binding.target_field} />
              <InfoBox label="Text fields" value={binding.text_fields.join(", ")} />
              <InfoBox label="Discriminator" value={binding.filter_field ? `${binding.filter_field}=${binding.filter_value ?? ""}` : "None"} />
              <InfoBox label="Runtime snapshot" value={binding.last_successful_snapshot_version ?? "latest profile fallback"} />
              <InfoBox label="Mode" value={binding.mode} />
            </div>
          </div>
        ) : (
          <div className="text-sm text-slate-500 dark:text-slate-400">No binding selected.</div>
        )}
      </CardContent>
    </Card>
  );
}

function QuickChecksCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Quick checks</CardTitle>
        <CardDescription>Use this page after enrichment to verify the final user-facing behavior.</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2 text-sm text-slate-600 dark:text-slate-300">
          <li>• user wording resolves to canonical terms</li>
          <li>• the selected binding snapshot is used</li>
          <li>• results come from the expected index</li>
          <li>• raw DSL stays available under advanced details</li>
        </ul>
      </CardContent>
    </Card>
  );
}

function ResultPanel({ mode, result }: { mode: "plan" | "search" | null; result: RuntimeQueryPlanResponse | RuntimeSearchResponse | null }) {
  if (!result) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Result preview</CardTitle>
          <CardDescription>Run a preview or search to see the canonicalized query before debug details.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-950/60 dark:text-slate-400">
            Try <span className="font-medium text-slate-700 dark:text-slate-200">k8s pg timeout</span> to see alias canonicalization.
          </div>
        </CardContent>
      </Card>
    );
  }

  const searchResult = isSearchResult(result) ? result : null;

  return (
    <div className="space-y-5">
      <ResultSummaryCard mode={mode} result={result} />
      {searchResult ? <SearchHitsPanel result={searchResult} /> : null}
      <AdvancedDetails result={result} />
    </div>
  );
}

function ResultSummaryCard({ mode, result }: { mode: "plan" | "search" | null; result: RuntimeQueryPlanResponse | RuntimeSearchResponse }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>{mode === "search" ? "Search result" : "Query plan"}</CardTitle>
            <CardDescription>Result-first view of how SkeinRank rewrites the query for this binding.</CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge>{result.snapshot_source}</Badge>
            <Badge>{result.changed ? "canonicalized" : "unchanged"}</Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] lg:items-center">
          <QueryBox label="Original query" value={result.query} />
          <div className="hidden text-center text-2xl font-semibold text-slate-300 dark:text-slate-700 lg:block">→</div>
          <QueryBox emphasis label="Canonical query" value={result.canonical_query} />
        </div>

        <div className="grid gap-3 lg:grid-cols-3">
          <CompactList title="Matched aliases" values={result.matched_aliases} empty="No aliases matched." />
          <CompactList title="Canonical values" values={result.canonical_values} empty="No canonical values." />
          <SnapshotBox result={result} />
        </div>

        {result.replacements.length > 0 ? <ReplacementChips replacements={result.replacements} /> : null}
        {result.warnings.length > 0 ? <WarningsBox warnings={result.warnings} /> : null}
      </CardContent>
    </Card>
  );
}

function QueryBox({ emphasis = false, label, value }: { emphasis?: boolean; label: string; value: string }) {
  return (
    <div
      className={
        emphasis
          ? "rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-4 dark:border-emerald-900/60 dark:bg-emerald-950/30"
          : "rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4 dark:border-slate-800 dark:bg-slate-950/60"
      }
    >
      <div className={emphasis ? "text-xs font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-300" : "text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400"}>{label}</div>
      <div className={emphasis ? "mt-1 text-lg font-semibold text-emerald-900 dark:text-emerald-100" : "mt-1 text-lg font-semibold text-slate-950 dark:text-slate-50"}>{value || "-"}</div>
    </div>
  );
}

function SnapshotBox({ result }: { result: RuntimeQueryPlanResponse | RuntimeSearchResponse }) {
  return (
    <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Runtime snapshot</div>
      <div className="mt-2 text-sm font-medium text-slate-900 dark:text-slate-100">{result.snapshot_version ?? "latest profile"}</div>
      <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{result.profile_name}</div>
    </div>
  );
}

function CompactList({ empty, title, values }: { empty: string; title: string; values: string[] }) {
  return (
    <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{title}</div>
      <div className="mt-2 flex flex-wrap gap-2">
        {values.length === 0 ? <span className="text-sm text-slate-500 dark:text-slate-400">{empty}</span> : values.map((value) => <Badge key={value}>{value}</Badge>)}
      </div>
    </div>
  );
}

function ReplacementChips({ replacements }: { replacements: RuntimeQueryPlanResponse["replacements"] }) {
  return (
    <div>
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Alias replacements</div>
      <div className="flex flex-wrap gap-2">
        {replacements.map((replacement, index) => (
          <span key={`${replacement.alias_value}-${index}`} className="inline-flex items-center gap-1 rounded-full border border-slate-200 px-3 py-1 text-xs text-slate-700 dark:border-slate-800 dark:text-slate-200">
            <span className="font-medium">{replacement.alias_value}</span>
            <span className="text-slate-400">→</span>
            <span className="font-medium">{replacement.canonical_value}</span>
            <span className="text-slate-400">·</span>
            <span>{replacement.slot}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function WarningsBox({ warnings }: { warnings: string[] }) {
  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
      <div className="font-medium">Warnings</div>
      <ul className="mt-1 list-disc space-y-1 pl-4">
        {warnings.map((warning) => (
          <li key={warning}>{warning}</li>
        ))}
      </ul>
    </div>
  );
}

function SearchHitsPanel({ result }: { result: RuntimeSearchResponse }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>Search hits</CardTitle>
            <CardDescription>Documents returned by Elasticsearch for this binding-aware query.</CardDescription>
          </div>
          <Badge>{formatTotal(result.total)} total</Badge>
        </div>
      </CardHeader>
      <CardContent>
        {result.hits.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-950/60 dark:text-slate-400">
            No hits returned.
          </div>
        ) : (
          <div className="space-y-3">
            {result.hits.map((hit) => (
              <div key={`${hit.index}-${hit.id}`} className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
                <div className="flex flex-wrap items-center gap-2">
                  <div className="font-medium text-slate-950 dark:text-slate-50">{hit.id || "untitled document"}</div>
                  <Badge>{hit.index}</Badge>
                  {hit.score !== null ? <Badge>score {hit.score.toFixed(2)}</Badge> : null}
                </div>
                <div className="mt-2 text-sm text-slate-600 dark:text-slate-300">{hitSummary(hit.source)}</div>
                {hit.skeinrank ? (
                  <details className="mt-3 rounded-xl bg-slate-50 p-3 text-xs text-slate-700 dark:bg-slate-950 dark:text-slate-200">
                    <summary className="cursor-pointer font-medium">SkeinRank attributes</summary>
                    <pre className="mt-3 max-h-48 overflow-auto">{JSON.stringify(hit.skeinrank, null, 2)}</pre>
                  </details>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function AdvancedDetails({ result }: { result: RuntimeQueryPlanResponse | RuntimeSearchResponse }) {
  return (
    <Card>
      <details>
        <summary className="cursor-pointer list-none border-b border-slate-100 px-5 py-4 dark:border-slate-800">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <CardTitle>Advanced details</CardTitle>
              <CardDescription>Open debug output when you need DSL, fields, slots, or replacement confidence.</CardDescription>
            </div>
            <Badge>debug</Badge>
          </div>
        </summary>
        <CardContent className="space-y-5">
          <div className="grid gap-3 lg:grid-cols-2">
            <InfoBox label="Profile" value={result.profile_name} />
            <InfoBox label="Snapshot source" value={result.snapshot_source} />
            <InfoBox label="Text fields" value={displayTextFields(result)} />
            <InfoBox label="Target field" value={displayTargetField(result)} />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <SlotsBox slots={result.slots} />
            <ReplacementTable replacements={result.replacements} />
          </div>
          <div>
            <div className="mb-2 text-sm font-semibold text-slate-950 dark:text-slate-50">Elasticsearch DSL</div>
            <pre className="max-h-96 overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-100">{JSON.stringify(result.elasticsearch, null, 2)}</pre>
          </div>
        </CardContent>
      </details>
    </Card>
  );
}

function InfoBox({ emphasis = false, label, value }: { emphasis?: boolean; label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 dark:border-slate-800 dark:bg-slate-950/60">
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</div>
      <div className={emphasis ? "mt-1 font-semibold text-emerald-700 dark:text-emerald-300" : "mt-1 text-sm text-slate-900 dark:text-slate-100"}>{value || "-"}</div>
    </div>
  );
}

function SlotsBox({ slots }: { slots: Record<string, string[]> }) {
  const entries = Object.entries(slots);
  return (
    <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Slots</div>
      <div className="mt-2 space-y-2">
        {entries.length === 0 ? (
          <span className="text-sm text-slate-500 dark:text-slate-400">No slots matched.</span>
        ) : (
          entries.map(([slot, values]) => (
            <div key={slot} className="text-sm">
              <span className="font-medium text-slate-800 dark:text-slate-100">{slot}</span>
              <span className="text-slate-500 dark:text-slate-400"> · {values.join(", ")}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function ReplacementTable({ replacements }: { replacements: RuntimeQueryPlanResponse["replacements"] }) {
  return (
    <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Replacement confidence</div>
      {replacements.length === 0 ? (
        <div className="mt-2 text-sm text-slate-500 dark:text-slate-400">No replacements.</div>
      ) : (
        <div className="mt-2 max-h-56 overflow-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
              <tr>
                <th className="py-1 pr-2">Alias</th>
                <th className="py-1 pr-2">Canonical</th>
                <th className="py-1 pr-2">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {replacements.map((replacement, index) => (
                <tr key={`${replacement.alias_value}-${index}`}>
                  <td className="py-1 pr-2 font-medium text-slate-900 dark:text-slate-100">{replacement.alias_value}</td>
                  <td className="py-1 pr-2 text-slate-600 dark:text-slate-300">{replacement.canonical_value}</td>
                  <td className="py-1 pr-2 text-slate-600 dark:text-slate-300">{replacement.confidence.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function displayTextFields(result: RuntimeQueryPlanResponse | RuntimeSearchResponse) {
  return Array.isArray(result.text_fields) && result.text_fields.length > 0 ? result.text_fields.join(", ") : "from selected binding";
}

function displayTargetField(result: RuntimeQueryPlanResponse | RuntimeSearchResponse) {
  return typeof result.target_field === "string" && result.target_field ? result.target_field : "from selected binding";
}

function parseInteger(value: string, fallback: number) {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.min(Math.max(parsed, 1), 100);
}

function parseFloatOrDefault(value: string, fallback: number) {
  const parsed = Number.parseFloat(value);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return Math.min(Math.max(parsed, 0), 100);
}

function isSearchResult(result: RuntimeQueryPlanResponse | RuntimeSearchResponse): result is RuntimeSearchResponse {
  return "hits" in result;
}

function errorText(error: unknown) {
  return error instanceof Error ? error.message : null;
}

function formatTotal(total: RuntimeSearchResponse["total"]) {
  if (typeof total === "number") {
    return String(total);
  }
  if (total && typeof total === "object") {
    const value = total["value"];
    return typeof value === "number" || typeof value === "string" ? String(value) : "unknown";
  }
  return "unknown";
}

function hitSummary(source: Record<string, unknown>) {
  const candidates = [source["title"], source["summary"], source["body"], source["text"], source["content"]];
  for (const candidate of candidates) {
    if (typeof candidate === "string" && candidate.trim()) {
      return candidate;
    }
  }
  return JSON.stringify(source).slice(0, 240);
}
