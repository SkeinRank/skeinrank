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

  const isSubmitting = queryPlanMutation.isPending || searchMutation.isPending;
  const errorMessage = errorText(queryPlanMutation.error) ?? errorText(searchMutation.error);

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <CardTitle>Runtime search playground</CardTitle>
          <CardDescription>
            Test how a binding canonicalizes a user query, builds the Elasticsearch DSL, and optionally runs runtime search.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 lg:grid-cols-4">
            <StepCard title="1. Choose binding" description="Select the runtime context and pinned snapshot." />
            <StepCard title="2. Enter query" description="Use raw user wording like k8s, pg, kube, or product aliases." />
            <StepCard title="3. Preview plan" description="Review canonicalization, aliases, slots, and DSL before execution." />
            <StepCard title="4. Run search" description="Execute Elasticsearch search when the connection is configured." />
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle>Runtime query</CardTitle>
              <CardDescription>Use binding_id for production-like behavior. The playground uses the binding runtime snapshot when available.</CardDescription>
            </CardHeader>
            <CardContent>
              <form className="space-y-4" onSubmit={handlePlanSubmit}>
                <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_160px_160px]">
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
                          {binding.name} · {binding.profile_name} · {binding.index_name}
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
                    className="min-h-28 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-slate-400 focus:ring-2 focus:ring-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:border-slate-500 dark:focus:ring-slate-800"
                    onChange={(event) => setQueryText(event.target.value)}
                    placeholder="k8s pg timeout"
                    value={queryText}
                  />
                </label>

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

          <ResultPanel mode={activeMode} result={activeResult} />
        </div>

        <aside className="space-y-5">
          <BindingContextCard binding={selectedBinding} isLoading={bindingsQuery.isLoading} />
          <HintsCard />
        </aside>
      </div>
    </div>
  );
}

function StepCard({ description, title }: { description: string; title: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 dark:border-slate-800 dark:bg-slate-950/60">
      <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</div>
      <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">{description}</div>
    </div>
  );
}

function BindingContextCard({ binding, isLoading }: { binding: ElasticsearchBinding | null; isLoading: boolean }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Binding context</CardTitle>
        <CardDescription>Production runtime should search by binding, not just by profile.</CardDescription>
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

function HintsCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>What to verify</CardTitle>
        <CardDescription>Use this page as the final check after Terms, Integrations, and Snapshots.</CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2 text-sm text-slate-600 dark:text-slate-300">
          <li>• aliases become canonical values</li>
          <li>• the query uses the selected binding snapshot</li>
          <li>• Elasticsearch DSL targets the expected fields</li>
          <li>• search hits include enriched SkeinRank attributes</li>
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
          <CardTitle>Query output</CardTitle>
          <CardDescription>Preview a plan or run search to see canonicalization, DSL, and results.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-950/60 dark:text-slate-400">
            Enter a query and click Preview query plan.
          </div>
        </CardContent>
      </Card>
    );
  }

  const searchResult = isSearchResult(result) ? result : null;

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>{mode === "search" ? "Search result" : "Query plan"}</CardTitle>
              <CardDescription>Binding-aware canonicalization and Elasticsearch query preview.</CardDescription>
            </div>
            <Badge>{result.snapshot_source}</Badge>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 lg:grid-cols-2">
            <InfoBox label="Original query" value={result.query} />
            <InfoBox label="Canonical query" value={result.canonical_query} emphasis={result.changed} />
            <InfoBox label="Profile" value={result.profile_name} />
            <InfoBox label="Snapshot" value={result.snapshot_version ?? "latest profile"} />
            <InfoBox label="Text fields" value={displayTextFields(result)} />
            <InfoBox label="Target field" value={displayTargetField(result)} />
          </div>

          <div className="mt-5 grid gap-4 lg:grid-cols-3">
            <ListBox title="Matched aliases" values={result.matched_aliases} empty="No aliases matched." />
            <ListBox title="Canonical values" values={result.canonical_values} empty="No canonical values." />
            <SlotsBox slots={result.slots} />
          </div>

          {result.replacements.length > 0 ? (
            <div className="mt-5">
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Replacements</div>
              <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800">
                <table className="w-full text-left text-sm">
                  <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-950 dark:text-slate-400">
                    <tr>
                      <th className="px-3 py-2">Alias</th>
                      <th className="px-3 py-2">Canonical</th>
                      <th className="px-3 py-2">Slot</th>
                      <th className="px-3 py-2">Confidence</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                    {result.replacements.map((replacement, index) => (
                      <tr key={`${replacement.alias_value}-${index}`}>
                        <td className="px-3 py-2 font-medium text-slate-900 dark:text-slate-100">{replacement.alias_value}</td>
                        <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{replacement.canonical_value}</td>
                        <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{replacement.slot}</td>
                        <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{replacement.confidence.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}

          {result.warnings.length > 0 ? (
            <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
              <div className="font-medium">Warnings</div>
              <ul className="mt-1 list-disc space-y-1 pl-4">
                {result.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {searchResult ? <SearchHitsPanel result={searchResult} /> : null}

      <Card>
        <CardHeader>
          <CardTitle>Elasticsearch DSL</CardTitle>
          <CardDescription>Generated request body used by runtime search.</CardDescription>
        </CardHeader>
        <CardContent>
          <pre className="max-h-96 overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-100">{JSON.stringify(result.elasticsearch, null, 2)}</pre>
        </CardContent>
      </Card>
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
                  <pre className="mt-3 max-h-48 overflow-auto rounded-xl bg-slate-50 p-3 text-xs text-slate-700 dark:bg-slate-950 dark:text-slate-200">
                    {JSON.stringify(hit.skeinrank, null, 2)}
                  </pre>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </CardContent>
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

function ListBox({ empty, title, values }: { empty: string; title: string; values: string[] }) {
  return (
    <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{title}</div>
      <div className="mt-2 flex flex-wrap gap-2">
        {values.length === 0 ? <span className="text-sm text-slate-500 dark:text-slate-400">{empty}</span> : values.map((value) => <Badge key={value}>{value}</Badge>)}
      </div>
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
