import { useMutation, useQuery } from "@tanstack/react-query";
import { Code2, Database, GitBranch, Search, Sparkles } from "lucide-react";
import { type FormEvent, useEffect, useMemo, useState } from "react";

import {
  ConsolePage,
  EntityDetailPanel,
  MasterDetailLayout,
  MetricPill,
  SectionCard,
  WorkspaceHeader,
  getConsoleToneForStatus,
} from "../components/layout/ConsolePrimitives";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { buildRuntimeQueryPlan, listElasticsearchBindings, searchRuntimeDocuments } from "../lib/api";
import type { ElasticsearchBinding, RuntimeQueryPlanResponse, RuntimeSearchResponse } from "../types";

const defaultQuery = "k8s pg timeout";

type PlaygroundMode = "single" | "compare";

type SnapshotCompareResult = {
  left: RuntimeQueryPlanResponse;
  right: RuntimeQueryPlanResponse;
  leftBinding: ElasticsearchBinding | null;
  rightBinding: ElasticsearchBinding | null;
};

export function SearchPlaygroundPage() {
  const bindingsQuery = useQuery({
    queryKey: ["elasticsearch-bindings", "all"],
    queryFn: () => listElasticsearchBindings(),
  });
  const [selectedBindingId, setSelectedBindingId] = useState<number | null>(null);
  const [compareBindingId, setCompareBindingId] = useState<number | null>(null);
  const [queryText, setQueryText] = useState(defaultQuery);
  const [size, setSize] = useState("10");
  const [canonicalBoost, setCanonicalBoost] = useState("3");
  const [playgroundMode, setPlaygroundMode] = useState<PlaygroundMode>("single");
  const [activeResult, setActiveResult] = useState<RuntimeQueryPlanResponse | RuntimeSearchResponse | null>(null);
  const [activeMode, setActiveMode] = useState<"plan" | "search" | null>(null);
  const [compareResult, setCompareResult] = useState<SnapshotCompareResult | null>(null);

  const bindings = useMemo(() => bindingsQuery.data ?? [], [bindingsQuery.data]);
  const effectiveBindingId = selectedBindingId ?? bindings[0]?.id ?? null;
  const effectiveCompareBindingId =
    compareBindingId ?? bindings.find((binding) => binding.id !== effectiveBindingId)?.id ?? effectiveBindingId;

  useEffect(() => {
    if (bindings.length === 0) {
      setSelectedBindingId(null);
      setCompareBindingId(null);
      return;
    }
    if (!selectedBindingId || !bindings.some((binding) => binding.id === selectedBindingId)) {
      setSelectedBindingId(bindings[0].id);
    }
  }, [bindings, selectedBindingId]);

  useEffect(() => {
    if (bindings.length === 0) {
      setCompareBindingId(null);
      return;
    }
    if (!compareBindingId || !bindings.some((binding) => binding.id === compareBindingId)) {
      const fallbackBinding = bindings.find((binding) => binding.id !== effectiveBindingId) ?? bindings[0];
      setCompareBindingId(fallbackBinding.id);
    }
  }, [bindings, compareBindingId, effectiveBindingId]);

  const selectedBinding = useMemo(
    () => bindings.find((binding) => binding.id === effectiveBindingId) ?? null,
    [bindings, effectiveBindingId],
  );

  const selectedCompareBinding = useMemo(
    () => bindings.find((binding) => binding.id === effectiveCompareBindingId) ?? null,
    [bindings, effectiveCompareBindingId],
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
      setCompareResult(null);
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
      setCompareResult(null);
    },
  });

  const compareMutation = useMutation({
    mutationFn: async () => {
      if (!effectiveBindingId || !effectiveCompareBindingId) {
        throw new Error("Select two runtime bindings before comparing snapshots.");
      }
      const basePayload = {
        query: queryText.trim(),
        size: parseInteger(size, 10),
        canonical_boost: parseFloatOrDefault(canonicalBoost, 3),
        include_evidence: true,
      };
      const [left, right] = await Promise.all([
        buildRuntimeQueryPlan({ ...basePayload, binding_id: effectiveBindingId }),
        buildRuntimeQueryPlan({ ...basePayload, binding_id: effectiveCompareBindingId }),
      ]);
      return { left, right };
    },
    onSuccess: ({ left, right }) => {
      setActiveMode(null);
      setActiveResult(null);
      setCompareResult({
        left,
        right,
        leftBinding: selectedBinding,
        rightBinding: selectedCompareBinding,
      });
    },
  });

  const canSubmit = Boolean(effectiveBindingId) && queryText.trim().length > 0;
  const canCompare = canSubmit && Boolean(effectiveCompareBindingId);
  const isSubmitting = queryPlanMutation.isPending || searchMutation.isPending || compareMutation.isPending;
  const errorMessage = errorText(queryPlanMutation.error) ?? errorText(searchMutation.error) ?? errorText(compareMutation.error);
  const resultStats = getResultStats(activeResult, compareResult);

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

  async function handleCompareClick() {
    if (!canCompare) {
      return;
    }
    setPlaygroundMode("compare");
    await compareMutation.mutateAsync();
  }

  return (
    <ConsolePage className="space-y-4">
      <WorkspaceHeader
        actions={
          <Badge className="shrink-0 whitespace-nowrap">
            {selectedBinding ? selectedBinding.snapshot_status ?? "uninitialized" : "no binding"}
          </Badge>
        }
        description="Run binding-aware query planning, compare snapshots side-by-side, and verify Elasticsearch output before shipping runtime search behavior."
        eyebrow="Runtime query lab"
        meta={
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <MetricPill
              helper={selectedBinding ? selectedBinding.index_name : "Create an Elasticsearch binding first"}
              icon={GitBranch}
              label="Active binding"
              tone={selectedBinding ? "cyan" : "amber"}
              value={selectedBinding ? selectedBinding.name : "None"}
            />
            <MetricPill
              helper={selectedBinding?.profile_name ?? "No profile selected"}
              icon={Database}
              label="Runtime snapshot"
              tone={getConsoleToneForStatus(selectedBinding?.snapshot_status ?? "unknown")}
              value={compactSnapshot(selectedBinding)}
            />
            <MetricPill
              helper={activeResult || compareResult ? "from latest preview" : "run a query plan"}
              icon={Sparkles}
              label="Canonical values"
              tone={activeResult || compareResult ? "emerald" : "slate"}
              value={resultStats.canonicalValues}
            />
            <MetricPill
              helper={playgroundMode === "compare" ? "snapshot compare mode" : activeMode === "search" ? "Elasticsearch results" : "query-plan mode"}
              icon={Search}
              label="Runtime output"
              tone={activeResult || compareResult ? "violet" : "slate"}
              value={resultStats.output}
            />
          </div>
        }
        title="Runtime search playground"
      />

      <MasterDetailLayout asideWidthClassName="xl:grid-cols-[minmax(0,1fr)_400px] 2xl:grid-cols-[minmax(0,1fr)_430px]">
        <div className="min-w-0 space-y-4">
          <SectionCard
            actions={<Badge className="shrink-0 whitespace-nowrap">binding-aware</Badge>}
            description="Choose runtime bindings, enter real user wording, then inspect canonical context or compare two binding-backed snapshots."
            title="Binding-aware query lab"
          >
            <form className="space-y-4" onSubmit={handlePlanSubmit}>
              <div className="flex flex-wrap gap-2">
                <ModeButton active={playgroundMode === "single"} label="Single mode" onClick={() => setPlaygroundMode("single")} />
                <ModeButton active={playgroundMode === "compare"} label="Compare snapshots" onClick={() => setPlaygroundMode("compare")} />
              </div>

              <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_120px_150px]">
                <BindingSelect
                  bindings={bindings}
                  disabled={bindingsQuery.isLoading || bindings.length === 0}
                  label={playgroundMode === "compare" ? "Column A binding" : "Binding"}
                  onChange={(bindingId) => {
                    setSelectedBindingId(bindingId);
                    setActiveResult(null);
                    setActiveMode(null);
                    setCompareResult(null);
                  }}
                  value={effectiveBindingId}
                />
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

              {playgroundMode === "compare" ? (
                <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                  <BindingSelect
                    bindings={bindings}
                    disabled={bindingsQuery.isLoading || bindings.length === 0}
                    label="Column B binding"
                    onChange={(bindingId) => {
                      setCompareBindingId(bindingId);
                      setCompareResult(null);
                    }}
                    value={effectiveCompareBindingId}
                  />
                  <div className="rounded-2xl border border-indigo-100 bg-indigo-50/70 px-4 py-3 text-sm text-indigo-800 dark:border-indigo-500/20 dark:bg-indigo-500/10 dark:text-indigo-200">
                    Compare mode uses the existing query-plan endpoint twice. Column A can be active prod, while Column B can be a staging or draft binding.
                  </div>
                </div>
              ) : null}

              <label className="space-y-1 text-sm font-medium text-slate-700 dark:text-slate-200">
                Query
                <textarea
                  className="min-h-28 w-full rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-3 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-slate-400 focus:bg-white focus:ring-2 focus:ring-slate-100 dark:border-slate-700 dark:bg-slate-950/80 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:border-slate-500 dark:focus:bg-slate-950 dark:focus:ring-slate-800"
                  onChange={(event) => {
                    setQueryText(event.target.value);
                    setCompareResult(null);
                  }}
                  placeholder="k8s pg timeout during phoenix rollout"
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
                <Button disabled={!canCompare || isSubmitting} onClick={handleCompareClick} type="button" variant="secondary">
                  Compare snapshots
                </Button>
              </div>
            </form>
          </SectionCard>

          {compareResult ? <SnapshotComparePanel compare={compareResult} /> : <ResultPanel mode={activeMode} result={activeResult} />}
        </div>

        <aside className="min-w-0 space-y-4">
          <BindingContextPanel binding={selectedBinding} isLoading={bindingsQuery.isLoading} />
          {playgroundMode === "compare" ? <CompareContextPanel binding={selectedCompareBinding} /> : null}
          <RuntimeChecksPanel />
        </aside>
      </MasterDetailLayout>
    </ConsolePage>
  );
}

function BindingSelect({ bindings, disabled, label, onChange, value }: { bindings: ElasticsearchBinding[]; disabled: boolean; label: string; onChange: (bindingId: number) => void; value: number | null }) {
  return (
    <label className="space-y-1 text-sm font-medium text-slate-700 dark:text-slate-200">
      {label}
      <select
        className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:focus:border-slate-500 dark:focus:ring-slate-800"
        disabled={disabled}
        onChange={(event) => onChange(Number(event.target.value))}
        value={value ?? ""}
      >
        {bindings.length === 0 ? <option value="">No bindings available</option> : null}
        {bindings.map((binding) => (
          <option key={binding.id} value={binding.id}>
            {bindingOptionLabel(binding)}
          </option>
        ))}
      </select>
    </label>
  );
}

function ModeButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      className={
        active
          ? "rounded-full bg-slate-950 px-3 py-1.5 text-sm font-semibold text-white dark:bg-slate-100 dark:text-slate-950"
          : "rounded-full border border-slate-200 bg-white px-3 py-1.5 text-sm font-semibold text-slate-600 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300 dark:hover:bg-slate-900"
      }
      onClick={onClick}
      type="button"
    >
      {label}
    </button>
  );
}

function bindingOptionLabel(binding: ElasticsearchBinding) {
  const discriminator = binding.filter_field ? ` · Scope: ${binding.filter_field}=${binding.filter_value ?? "*"}` : "";
  return `Binding: ${binding.name} · Profile: ${binding.profile_name} · Index: ${binding.index_name}${discriminator}`;
}

function SelectedBindingChips({ binding }: { binding: ElasticsearchBinding }) {
  return (
    <div className="flex flex-wrap gap-2 rounded-2xl border border-slate-200 bg-white p-3 text-xs shadow-sm shadow-slate-200/40 dark:border-slate-800 dark:bg-slate-950 dark:shadow-black/20">
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
    <span className={`inline-flex max-w-full items-center gap-1 rounded-full px-2.5 py-1 font-medium ${className ?? ""}`}>
      <span className="shrink-0 uppercase tracking-wide opacity-70">{label}</span>
      <span className="truncate">{value || "-"}</span>
    </span>
  );
}

function BindingContextPanel({ binding, isLoading }: { binding: ElasticsearchBinding | null; isLoading: boolean }) {
  return (
    <EntityDetailPanel
      badge={<Badge className="shrink-0 whitespace-nowrap">{binding?.snapshot_status ?? "no binding"}</Badge>}
      description="Runtime search should use binding context, not a loose profile."
      title="Binding context"
    >
      {isLoading ? (
        <div className="text-sm text-slate-500 dark:text-slate-400">Loading bindings...</div>
      ) : binding ? (
        <BindingContextBody binding={binding} />
      ) : (
        <div className="text-sm text-slate-500 dark:text-slate-400">No binding selected.</div>
      )}
    </EntityDetailPanel>
  );
}

function CompareContextPanel({ binding }: { binding: ElasticsearchBinding | null }) {
  return (
    <EntityDetailPanel
      badge={<Badge className="shrink-0 whitespace-nowrap">compare</Badge>}
      description="Column B should point at a staging, draft, or alternative snapshot-backed binding."
      title="Compare context"
    >
      {binding ? <BindingContextBody binding={binding} /> : <div className="text-sm text-slate-500 dark:text-slate-400">No comparison binding selected.</div>}
    </EntityDetailPanel>
  );
}

function BindingContextBody({ binding }: { binding: ElasticsearchBinding }) {
  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-cyan-100 bg-cyan-50/60 p-4 dark:border-cyan-500/20 dark:bg-cyan-500/5">
        <div className="text-base font-semibold text-slate-950 dark:text-slate-50">{binding.name}</div>
        <div className="mt-1 text-sm text-slate-600 dark:text-slate-300">
          {binding.profile_name} → {binding.index_name}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <InfoBox label="Binding ID" value={`#${binding.id}`} />
        <InfoBox label="Target field" value={binding.target_field} />
        <InfoBox label="Text fields" value={binding.text_fields.join(", ")} />
        <InfoBox label="Discriminator" value={binding.filter_field ? `${binding.filter_field}=${binding.filter_value ?? ""}` : "None"} />
        <InfoBox label="Runtime snapshot" value={binding.last_successful_snapshot_version ?? binding.pending_snapshot_version ?? "latest profile fallback"} />
        <InfoBox label="Mode" value={binding.mode} />
      </div>
    </div>
  );
}

function RuntimeChecksPanel() {
  return (
    <SectionCard
      description="A small checklist for validating user-facing behavior after each dictionary or enrichment change."
      title="Runtime checks"
    >
      <div className="space-y-3 text-sm text-slate-600 dark:text-slate-300">
        <CheckRow text="user wording resolves to canonical terms" />
        <CheckRow text="the selected binding snapshot is used" />
        <CheckRow text="compare mode highlights canonicalization differences" />
        <CheckRow text="results come from the expected index" />
        <CheckRow text="raw DSL stays available under advanced details" />
      </div>
    </SectionCard>
  );
}

function CheckRow({ text }: { text: string }) {
  return (
    <div className="flex items-start gap-2">
      <span className="mt-1 h-1.5 w-1.5 flex-none rounded-full bg-emerald-500" />
      <span>{text}</span>
    </div>
  );
}

function ResultPanel({ mode, result }: { mode: "plan" | "search" | null; result: RuntimeQueryPlanResponse | RuntimeSearchResponse | null }) {
  if (!result) {
    return (
      <SectionCard
        description="Run a preview, search, or snapshot compare to see the canonicalized query before debug details."
        title="Result preview"
      >
        <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-950/60 dark:text-slate-400">
          Try <span className="font-medium text-slate-700 dark:text-slate-200">k8s pg timeout</span> to see alias canonicalization.
        </div>
      </SectionCard>
    );
  }

  const searchResult = isSearchResult(result) ? result : null;

  return (
    <div className="space-y-4">
      <ResultSummaryCard mode={mode} result={result} />
      {searchResult ? <SearchHitsPanel result={searchResult} /> : null}
      <AdvancedDetails result={result} />
    </div>
  );
}

function SnapshotComparePanel({ compare }: { compare: SnapshotCompareResult }) {
  const diff = buildCanonicalDiff(compare.left, compare.right);
  return (
    <div className="space-y-4">
      <SectionCard
        actions={<Badge className="shrink-0 whitespace-nowrap">split-screen</Badge>}
        description="Compare how two binding-backed snapshots canonicalize the same query before release. This uses the existing query-plan API for each column."
        title="Snapshot compare result"
      >
        <div className="grid gap-4 xl:grid-cols-2">
          <CompareColumn binding={compare.leftBinding} label="Column A" result={compare.left} tone="slate" />
          <CompareColumn binding={compare.rightBinding} label="Column B" result={compare.right} tone="emerald" />
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <CompactList title="Added canonical values" values={diff.addedCanonicalValues} empty="No new values." />
          <CompactList title="Removed canonical values" values={diff.removedCanonicalValues} empty="No removed values." />
          <CompactList title="New matched aliases" values={diff.addedMatchedAliases} empty="No new aliases." />
        </div>
      </SectionCard>
      <div className="grid gap-4 xl:grid-cols-2">
        <AdvancedDetails result={compare.left} />
        <AdvancedDetails result={compare.right} />
      </div>
    </div>
  );
}

function CompareColumn({ binding, label, result, tone }: { binding: ElasticsearchBinding | null; label: string; result: RuntimeQueryPlanResponse; tone: "emerald" | "slate" }) {
  const borderClass = tone === "emerald" ? "border-emerald-200 bg-emerald-50/50 dark:border-emerald-500/20 dark:bg-emerald-500/5" : "border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-950/60";
  return (
    <div className={`rounded-2xl border p-4 ${borderClass}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</div>
          <div className="mt-1 text-base font-semibold text-slate-950 dark:text-slate-50">{binding?.name ?? `Binding #${result.binding_id ?? "unknown"}`}</div>
          <div className="mt-1 text-sm text-slate-600 dark:text-slate-300">{binding ? `${binding.profile_name} → ${binding.index_name}` : result.profile_name}</div>
        </div>
        <Badge className="shrink-0 whitespace-nowrap">{result.snapshot_version ?? binding?.pending_snapshot_version ?? "latest profile"}</Badge>
      </div>
      <div className="mt-4 space-y-3">
        <QueryBox label="Original query" value={result.query} />
        <QueryBox emphasis label="Canonical query" value={result.canonical_query} />
        <div className="grid gap-3 md:grid-cols-2">
          <CompactList title="Matched aliases" values={result.matched_aliases} empty="No aliases matched." />
          <CompactList title="Canonical values" values={result.canonical_values} empty="No canonical values." />
        </div>
        {result.replacements.length > 0 ? <ReplacementChips replacements={result.replacements} /> : null}
        {result.warnings.length > 0 ? <WarningsBox warnings={result.warnings} /> : null}
      </div>
    </div>
  );
}

function ResultSummaryCard({ mode, result }: { mode: "plan" | "search" | null; result: RuntimeQueryPlanResponse | RuntimeSearchResponse }) {
  return (
    <SectionCard
      actions={
        <div className="flex flex-wrap gap-2">
          <Badge className="shrink-0 whitespace-nowrap">{result.snapshot_source}</Badge>
          <Badge className="shrink-0 whitespace-nowrap">{result.changed ? "canonicalized" : "unchanged"}</Badge>
        </div>
      }
      description="Result-first view of how SkeinRank rewrites the query for this binding."
      title={mode === "search" ? "Search result" : "Query plan"}
    >
      <div className="space-y-5">
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
      </div>
    </SectionCard>
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
      <div className={emphasis ? "mt-1 break-words text-lg font-semibold text-emerald-900 dark:text-emerald-100" : "mt-1 break-words text-lg font-semibold text-slate-950 dark:text-slate-50"}>{value || "-"}</div>
    </div>
  );
}

function SnapshotBox({ result }: { result: RuntimeQueryPlanResponse | RuntimeSearchResponse }) {
  return (
    <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Runtime snapshot</div>
      <div className="mt-2 break-words text-sm font-medium text-slate-900 dark:text-slate-100">{result.snapshot_version ?? "latest profile"}</div>
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
      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
        {replacements.map((replacement, index) => (
          <div key={`${replacement.alias_value}-${index}`} className="rounded-2xl border border-slate-200 bg-white p-3 text-xs text-slate-700 shadow-sm shadow-slate-200/40 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200 dark:shadow-black/20">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="font-semibold text-slate-950 dark:text-slate-50">{replacement.alias_value}</span>
              <span className="text-slate-400">→</span>
              <span className="font-semibold text-emerald-700 dark:text-emerald-300">{replacement.canonical_value}</span>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-slate-500 dark:text-slate-400">
              <span>{replacement.slot}</span>
              <span>confidence {replacement.confidence.toFixed(2)}</span>
            </div>
          </div>
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
    <SectionCard
      actions={<Badge className="shrink-0 whitespace-nowrap">{formatTotal(result.total)} total</Badge>}
      description="Documents returned by Elasticsearch for this binding-aware query."
      title="Search hits"
    >
      {result.hits.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-950/60 dark:text-slate-400">
          No hits returned.
        </div>
      ) : (
        <div className="max-h-[560px] space-y-3 overflow-auto pr-1">
          {result.hits.map((hit) => (
            <div key={`${hit.index}-${hit.id}`} className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm shadow-slate-200/40 dark:border-slate-800 dark:bg-slate-950 dark:shadow-black/20">
              <div className="flex flex-wrap items-center gap-2">
                <div className="font-medium text-slate-950 dark:text-slate-50">{hit.id || "untitled document"}</div>
                <Badge>{hit.index}</Badge>
                {hit.score !== null ? <Badge>score {hit.score.toFixed(2)}</Badge> : null}
              </div>
              <div className="mt-2 line-clamp-3 text-sm text-slate-600 dark:text-slate-300">{hitSummary(hit.source)}</div>
              {hit.skeinrank ? <SkeinRankAttributes attributes={hit.skeinrank} /> : null}
            </div>
          ))}
        </div>
      )}
    </SectionCard>
  );
}

function SkeinRankAttributes({ attributes }: { attributes: Record<string, unknown> }) {
  const canonicalValues = getStringArray(attributes["canonical_values"]);
  const matchedAliases = getStringArray(attributes["matched_aliases"]);

  return (
    <details className="mt-3 rounded-xl border border-slate-100 bg-slate-50 p-3 text-xs text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200">
      <summary className="cursor-pointer font-medium">SkeinRank attributes</summary>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <CompactList title="Canonical values" values={canonicalValues} empty="No canonical values." />
        <CompactList title="Matched aliases" values={matchedAliases} empty="No matched aliases." />
      </div>
      <pre className="mt-3 max-h-48 overflow-auto rounded-xl bg-slate-950 p-3 text-xs text-slate-100">{JSON.stringify(attributes, null, 2)}</pre>
    </details>
  );
}

function AdvancedDetails({ result }: { result: RuntimeQueryPlanResponse | RuntimeSearchResponse }) {
  return (
    <SectionCard
      actions={<Badge className="shrink-0 whitespace-nowrap">debug</Badge>}
      description="Open debug output when you need DSL, fields, slots, or replacement confidence."
      title="Advanced details"
    >
      <details>
        <summary className="cursor-pointer list-none text-sm font-medium text-slate-700 dark:text-slate-200">
          Show Elasticsearch DSL, slots, and replacement confidence
        </summary>
        <div className="mt-4 space-y-5">
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
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-950 dark:text-slate-50">
              <Code2 className="h-4 w-4 text-slate-400" />
              Elasticsearch DSL
            </div>
            <pre className="max-h-96 overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-100">{JSON.stringify(result.elasticsearch, null, 2)}</pre>
          </div>
        </div>
      </details>
    </SectionCard>
  );
}

function InfoBox({ emphasis = false, label, value }: { emphasis?: boolean; label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 dark:border-slate-800 dark:bg-slate-950/60">
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</div>
      <div className={emphasis ? "mt-1 break-words font-semibold text-emerald-700 dark:text-emerald-300" : "mt-1 break-words text-sm text-slate-900 dark:text-slate-100"}>{value || "-"}</div>
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

function getResultStats(result: RuntimeQueryPlanResponse | RuntimeSearchResponse | null, compare: SnapshotCompareResult | null) {
  if (compare) {
    const leftCount = compare.left.canonical_values.length;
    const rightCount = compare.right.canonical_values.length;
    return { canonicalValues: `${leftCount} → ${rightCount}`, output: "Compare ready" };
  }
  if (!result) {
    return { canonicalValues: "—", output: "Preview" };
  }
  if (isSearchResult(result)) {
    return { canonicalValues: String(result.canonical_values.length), output: `${formatTotal(result.total)} hits` };
  }
  return { canonicalValues: String(result.canonical_values.length), output: "Plan ready" };
}

function buildCanonicalDiff(left: RuntimeQueryPlanResponse, right: RuntimeQueryPlanResponse) {
  return {
    addedCanonicalValues: arrayDifference(right.canonical_values, left.canonical_values),
    removedCanonicalValues: arrayDifference(left.canonical_values, right.canonical_values),
    addedMatchedAliases: arrayDifference(right.matched_aliases, left.matched_aliases),
  };
}

function arrayDifference(a: string[], b: string[]) {
  const bSet = new Set(b);
  return [...new Set(a)].filter((value) => !bSet.has(value));
}

function compactSnapshot(binding: ElasticsearchBinding | null) {
  if (!binding) {
    return "No binding";
  }
  return binding.last_successful_snapshot_version ? "Pinned" : binding.snapshot_status ?? "Uninitialized";
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

function getStringArray(value: unknown) {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}
