import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  CircleDashed,
  Clock3,
  FileJson,
  GitBranch,
  History,
  Plug,
  RotateCcw,
  TriangleAlert,
} from "lucide-react";

import type { AppSection } from "../components/layout/AppShell";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../components/ui/card";
import { getSnapshotSummary } from "../lib/api";
import type { SnapshotBindingState, SnapshotHistoryItem, SnapshotSummary } from "../types";

type RuntimeAuditLevel = "ready" | "attention" | "empty";

export function SnapshotsPage({ onNavigate }: { onNavigate: (section: AppSection) => void }) {
  const summaryQuery = useQuery({
    queryKey: ["snapshots", "summary"],
    queryFn: getSnapshotSummary,
  });

  if (summaryQuery.isLoading) {
    return (
      <Card>
        <CardContent className="text-sm text-slate-500 dark:text-slate-400">
          Loading runtime snapshots...
        </CardContent>
      </Card>
    );
  }

  if (summaryQuery.isError) {
    return (
      <Card className="border-red-200 bg-red-50 dark:border-red-900/60 dark:bg-red-950/40">
        <CardContent className="flex items-start gap-3 text-sm text-red-700 dark:text-red-200">
          <AlertCircle className="mt-0.5 h-4 w-4 flex-none" />
          <div>
            <div className="font-medium">Unable to load runtime snapshots</div>
            <div className="mt-1">
              {summaryQuery.error instanceof Error ? summaryQuery.error.message : "Check the governance API and try again."}
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  const summary = summaryQuery.data;
  if (!summary) {
    return null;
  }

  return (
    <div className="space-y-4">
      <RuntimeAuditHeader summary={summary} onNavigate={onNavigate} />

      <section className="grid gap-4 2xl:grid-cols-[1fr_360px]">
        <ActiveSnapshots bindings={summary.bindings} onNavigate={onNavigate} />
        <RuntimeAttentionPanel summary={summary} onNavigate={onNavigate} />
      </section>

      <SnapshotHistory history={summary.history} onNavigate={onNavigate} />
    </div>
  );
}

function RuntimeAuditHeader({ summary, onNavigate }: { summary: SnapshotSummary; onNavigate: (section: AppSection) => void }) {
  const auditLevel = getAuditLevel(summary);
  const progress = summary.counts.bindings > 0
    ? Math.round((summary.counts.active_snapshots / summary.counts.bindings) * 100)
    : 0;

  const counters = [
    { label: "Tracked bindings", value: summary.counts.bindings, helper: "runtime contexts" },
    { label: "Ready", value: summary.counts.active_snapshots, helper: `${progress}% with snapshots` },
    { label: "Stale / pending", value: summary.counts.stale_snapshots + summary.counts.pending_snapshots, helper: "needs rollout" },
    { label: "Rollback", value: summary.counts.rollback_available, helper: "available jobs" },
  ];

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle>Runtime audit</CardTitle>
              <AuditBadge level={auditLevel} />
            </div>
            <CardDescription>Verify which immutable terminology version each binding serves to runtime search.</CardDescription>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => onNavigate("integrations")} variant="secondary">
              <Plug className="mr-2 h-4 w-4" />
              Manage bindings
            </Button>
            <Button onClick={() => onNavigate("search-playground")} variant="secondary">
              <GitBranch className="mr-2 h-4 w-4" />
              Test search
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-2 md:grid-cols-4">
          {counters.map((counter) => (
            <div className="rounded-xl border border-slate-200 px-3 py-2 dark:border-slate-800" key={counter.label}>
              <div className="text-[11px] font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">{counter.label}</div>
              <div className="mt-1 flex items-end justify-between gap-2">
                <span className="text-2xl font-semibold tracking-tight text-slate-950 dark:text-slate-50">{counter.value}</span>
                <span className="pb-1 text-xs text-slate-500 dark:text-slate-400">{counter.helper}</span>
              </div>
            </div>
          ))}
        </div>
        <div>
          <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
            <span>Runtime readiness</span>
            <span>{progress}%</span>
          </div>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
            <div className="h-full rounded-full bg-emerald-500 transition-[width]" style={{ width: `${progress}%` }} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function ActiveSnapshots({ bindings, onNavigate }: { bindings: SnapshotBindingState[]; onNavigate: (section: AppSection) => void }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle>Runtime bindings</CardTitle>
            <CardDescription>Active snapshot, drift, and latest job per search context.</CardDescription>
          </div>
          <Badge className="bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">{bindings.length} bindings</Badge>
        </div>
      </CardHeader>
      <CardContent>
        {bindings.length === 0 ? (
          <EmptyState
            actionLabel="Create binding"
            description="Create an Elasticsearch binding before runtime snapshots can be tracked."
            onAction={() => onNavigate("integrations")}
            title="No runtime contexts yet"
          />
        ) : (
          <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800">
            <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-950 dark:text-slate-400">
                <tr>
                  <th className="px-4 py-3 font-medium">Binding</th>
                  <th className="px-4 py-3 font-medium">Snapshot</th>
                  <th className="px-4 py-3 font-medium">Drift</th>
                  <th className="px-4 py-3 font-medium">Latest job</th>
                  <th className="px-4 py-3 font-medium">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white dark:divide-slate-800 dark:bg-slate-900">
                {bindings.map((binding) => (
                  <tr key={binding.id}>
                    <td className="px-4 py-3 align-top">
                      <div className="flex flex-wrap items-center gap-2">
                        <div className="font-medium text-slate-950 dark:text-slate-50">{binding.name}</div>
                        <StatusBadge status={binding.status} />
                      </div>
                      <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{binding.profile_name} → {binding.index_name}</div>
                      {binding.filter_field && binding.filter_value ? (
                        <div className="mt-1 text-xs text-slate-400 dark:text-slate-500">
                          scope: {binding.filter_field} = {binding.filter_value}
                        </div>
                      ) : null}
                    </td>
                    <td className="max-w-[280px] px-4 py-3 align-top text-xs text-slate-500 dark:text-slate-400">
                      <div className="font-mono text-slate-700 dark:text-slate-300">{binding.active_snapshot_version ?? "Not created"}</div>
                      {binding.pending_snapshot_version ? <div className="mt-1">Pending: {binding.pending_snapshot_version}</div> : null}
                      <div className="mt-1">Aliases: {binding.snapshot_aliases_total} active / {binding.current_aliases_total} current</div>
                    </td>
                    <td className="px-4 py-3 align-top">
                      <DiffBadge binding={binding} />
                    </td>
                    <td className="px-4 py-3 align-top text-xs text-slate-500 dark:text-slate-400">
                      {binding.latest_job_id ? (
                        <div className="space-y-1">
                          <div>Job #{binding.latest_job_id}</div>
                          <StatusBadge status={binding.latest_job_status ?? "unknown"} />
                          {binding.latest_job_error ? <div className="text-red-600 dark:text-red-300">{binding.latest_job_error}</div> : null}
                        </div>
                      ) : (
                        "No jobs"
                      )}
                    </td>
                    <td className="px-4 py-3 align-top">
                      {binding.rollback_available ? (
                        <Badge className="bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
                          <RotateCcw className="mr-1 h-3 w-3" /> rollback
                        </Badge>
                      ) : binding.status === "stale" || binding.pending_snapshot_version ? (
                        <Button onClick={() => onNavigate("integrations")} variant="secondary">
                          Roll out
                        </Button>
                      ) : (
                        <Button onClick={() => onNavigate("search-playground")} variant="ghost">
                          Test
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function RuntimeAttentionPanel({ summary, onNavigate }: { summary: SnapshotSummary; onNavigate: (section: AppSection) => void }) {
  const binding = getAttentionBinding(summary.bindings);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Needs attention</CardTitle>
          <CardDescription>Fast path from runtime audit to the next operator action.</CardDescription>
        </CardHeader>
        <CardContent>
          {binding ? (
            <div className="space-y-4">
              <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
                <div className="flex items-center gap-2 font-medium">
                  <TriangleAlert className="h-4 w-4" />
                  {binding.name} needs runtime attention
                </div>
                <div className="mt-2 text-xs">
                  Status: {binding.status.replace(/_/g, " ")}. Search keeps using the active snapshot until a successful enrichment job activates a new one.
                </div>
              </div>
              <div className="grid gap-2 text-xs text-slate-500 dark:text-slate-400">
                <Fact label="Profile" value={binding.profile_name} />
                <Fact label="Index" value={binding.index_name} />
                <Fact label="Active snapshot" value={binding.active_snapshot_version ?? "Not created"} />
                <Fact label="Pending snapshot" value={binding.pending_snapshot_version ?? "None"} />
              </div>
              <Button onClick={() => onNavigate("integrations")}>
                Open enrichment jobs
              </Button>
            </div>
          ) : summary.counts.bindings === 0 ? (
            <EmptyState
              actionLabel="Create binding"
              description="Snapshots start after a profile is bound to an Elasticsearch search context."
              onAction={() => onNavigate("integrations")}
              title="No bindings yet"
            />
          ) : (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/40 dark:text-emerald-200">
              <div className="flex items-center gap-2 font-medium">
                <CheckCircle2 className="h-4 w-4" />
                Runtime state looks clean
              </div>
              <div className="mt-2 text-xs">No stale, pending, or failed runtime snapshots require immediate action.</div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Audit shortcuts</CardTitle>
          <CardDescription>Move from audit to configuration or verification.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-2">
          <Button className="justify-start" onClick={() => onNavigate("integrations")} variant="secondary">
            <Plug className="mr-2 h-4 w-4" />
            Bindings and jobs
          </Button>
          <Button className="justify-start" onClick={() => onNavigate("search-playground")} variant="secondary">
            <GitBranch className="mr-2 h-4 w-4" />
            Search Playground
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

function DiffBadge({ binding }: { binding: SnapshotBindingState }) {
  if (!binding.active_snapshot_version) {
    return (
      <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
        <CircleDashed className="h-4 w-4" />
        no active snapshot
      </div>
    );
  }
  if (!binding.diff.changed) {
    return (
      <div className="flex items-center gap-2 text-xs text-emerald-700 dark:text-emerald-300">
        <CheckCircle2 className="h-4 w-4" />
        matches current profile
      </div>
    );
  }
  return (
    <div className="space-y-1 text-xs text-amber-700 dark:text-amber-300">
      <div className="flex items-center gap-2 font-medium">
        <TriangleAlert className="h-4 w-4" />
        profile changed
      </div>
      <div>+{binding.diff.added_aliases} / -{binding.diff.removed_aliases} / changed {binding.diff.changed_aliases}</div>
    </div>
  );
}

function SnapshotHistory({ history, onNavigate }: { history: SnapshotHistoryItem[]; onNavigate: (section: AppSection) => void }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle>Recent snapshot events</CardTitle>
            <CardDescription>Last enrichment jobs that produced, activated, or failed runtime versions.</CardDescription>
          </div>
          <Button onClick={() => onNavigate("integrations")} variant="secondary">
            <History className="mr-2 h-4 w-4" />
            View jobs
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {history.length === 0 ? (
          <EmptyState
            actionLabel="Run enrichment"
            description="No snapshot-producing enrichment jobs have run yet. Start a job from Integrations after switching a binding to write mode."
            onAction={() => onNavigate("integrations")}
            title="No snapshot history yet"
          />
        ) : (
          <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800">
            <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-950 dark:text-slate-400">
                <tr>
                  <th className="px-4 py-3 font-medium">Job</th>
                  <th className="px-4 py-3 font-medium">Binding</th>
                  <th className="px-4 py-3 font-medium">Snapshot</th>
                  <th className="px-4 py-3 font-medium">Docs</th>
                  <th className="px-4 py-3 font-medium">Rollout</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white dark:divide-slate-800 dark:bg-slate-900">
                {history.map((item) => (
                  <tr key={item.job_id}>
                    <td className="px-4 py-3 align-top">
                      <div className="font-medium text-slate-950 dark:text-slate-50">Job #{item.job_id}</div>
                      <div className="mt-1"><StatusBadge status={item.status} /></div>
                      {item.error_message ? <div className="mt-2 text-xs text-red-600 dark:text-red-300">{item.error_message}</div> : null}
                    </td>
                    <td className="px-4 py-3 align-top">
                      <div className="font-medium text-slate-950 dark:text-slate-50">{item.binding_name}</div>
                      <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{item.profile_name}</div>
                    </td>
                    <td className="max-w-[280px] px-4 py-3 align-top text-xs text-slate-500 dark:text-slate-400">
                      <div className="font-mono text-slate-700 dark:text-slate-300">{item.snapshot_version ?? "No snapshot version"}</div>
                      {item.previous_snapshot_version ? <div className="mt-1">Previous: {item.previous_snapshot_version}</div> : null}
                      {item.checksum ? <div className="mt-1">checksum {item.checksum.slice(0, 12)}</div> : null}
                    </td>
                    <td className="px-4 py-3 align-top text-xs text-slate-500 dark:text-slate-400">
                      <div>Seen: {item.documents_seen}</div>
                      <div>Enriched: {item.documents_enriched}</div>
                      <div>Failed: {item.documents_failed}</div>
                    </td>
                    <td className="px-4 py-3 align-top text-xs text-slate-500 dark:text-slate-400">
                      {item.rollback_available ? <StatusBadge status="rollback available" /> : null}
                      {item.alias_name ? <div className="mt-1">Alias: {item.alias_name}</div> : null}
                      {item.target_index ? <div>Target: {item.target_index}</div> : null}
                      <div className="mt-1">Aliases: {item.alias_entries_total}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function EmptyState({ actionLabel, description, onAction, title }: { actionLabel: string; description: string; onAction: () => void; title: string }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 p-6 text-center dark:border-slate-700">
      <FileJson className="mx-auto h-6 w-6 text-slate-400" />
      <div className="mt-2 text-sm font-medium text-slate-950 dark:text-slate-50">{title}</div>
      <p className="mx-auto mt-1 max-w-md text-sm text-slate-500 dark:text-slate-400">{description}</p>
      <Button className="mt-4" onClick={onAction} variant="secondary">
        {actionLabel}
      </Button>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 px-3 py-2 dark:border-slate-800">
      <span>{label}</span>
      <span className="font-mono text-slate-700 dark:text-slate-300">{value}</span>
    </div>
  );
}

function AuditBadge({ level }: { level: RuntimeAuditLevel }) {
  if (level === "ready") {
    return <Badge className="bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">clean</Badge>;
  }
  if (level === "attention") {
    return <Badge className="bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300">needs attention</Badge>;
  }
  return <Badge>not started</Badge>;
}

function StatusBadge({ status }: { status: string }) {
  const normalized = status.replace(/_/g, " ");
  const className =
    status === "ok" || status === "ready" || status === "succeeded" || status === "enabled"
      ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
      : status === "failed" || status === "degraded"
        ? "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300"
        : status === "stale" || status === "updating" || status === "running" || status === "queued" || status === "unknown" || status === "rollback available"
          ? "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
          : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300";

  return <Badge className={className}>{normalized}</Badge>;
}

function getAuditLevel(summary: SnapshotSummary): RuntimeAuditLevel {
  if (summary.counts.bindings === 0) {
    return "empty";
  }
  if (summary.counts.stale_snapshots > 0 || summary.counts.pending_snapshots > 0 || summary.counts.failed_updates > 0 || summary.counts.never_enriched > 0) {
    return "attention";
  }
  return "ready";
}

function getAttentionBinding(bindings: SnapshotBindingState[]) {
  return bindings.find((binding) =>
    binding.status === "failed" ||
    binding.status === "stale" ||
    binding.status === "updating" ||
    binding.status === "never_enriched" ||
    Boolean(binding.pending_snapshot_version),
  );
}
