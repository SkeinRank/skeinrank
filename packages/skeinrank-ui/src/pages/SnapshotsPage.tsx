import { useQuery } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, FileJson, GitBranch, History, Plug, RotateCcw, TriangleAlert } from "lucide-react";

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
    <div className="space-y-6">
      <section className="grid gap-4 xl:grid-cols-[1.25fr_0.75fr]">
        <Card>
          <CardHeader>
            <CardTitle>Runtime snapshot control</CardTitle>
            <CardDescription>
              See which immutable terminology versions are active for search, which bindings are stale, and which updates can be rolled back.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <SnapshotCounters summary={summary} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Snapshot model</CardTitle>
            <CardDescription>How SkeinRank separates dictionary editing from runtime search.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-slate-600 dark:text-slate-300">
            <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
              <div className="font-medium text-slate-950 dark:text-slate-50">Profile</div>
              <div className="mt-1">The editable terminology dictionary.</div>
            </div>
            <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
              <div className="font-medium text-slate-950 dark:text-slate-50">Binding</div>
              <div className="mt-1">Where and how that dictionary is applied.</div>
            </div>
            <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
              <div className="font-medium text-slate-950 dark:text-slate-50">Snapshot</div>
              <div className="mt-1">The immutable version currently safe for runtime search.</div>
            </div>
          </CardContent>
        </Card>
      </section>

      <ActiveSnapshots bindings={summary.bindings} onNavigate={onNavigate} />
      <SnapshotHistory history={summary.history} onNavigate={onNavigate} />
    </div>
  );
}

function SnapshotCounters({ summary }: { summary: SnapshotSummary }) {
  const counters = [
    { label: "Active snapshots", value: summary.counts.active_snapshots, helper: `${summary.counts.bindings} bindings tracked` },
    { label: "Stale snapshots", value: summary.counts.stale_snapshots, helper: "profile changed after runtime snapshot" },
    { label: "Pending snapshots", value: summary.counts.pending_snapshots, helper: "new snapshot waiting for activation" },
    { label: "Rollback available", value: summary.counts.rollback_available, helper: "last successful alias-swap jobs" },
  ];

  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      {counters.map((counter) => (
        <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-800" key={counter.label}>
          <div className="text-sm text-slate-500 dark:text-slate-400">{counter.label}</div>
          <div className="mt-2 text-3xl font-semibold tracking-tight text-slate-950 dark:text-slate-50">{counter.value}</div>
          <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{counter.helper}</div>
        </div>
      ))}
    </div>
  );
}

function ActiveSnapshots({ bindings, onNavigate }: { bindings: SnapshotBindingState[]; onNavigate: (section: AppSection) => void }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle>Active runtime snapshots</CardTitle>
            <CardDescription>Binding-level runtime state, profile drift, and active snapshot versions.</CardDescription>
          </div>
          <Button onClick={() => onNavigate("integrations")} variant="secondary">
            <Plug className="mr-2 h-4 w-4" />
            Open integrations
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {bindings.length === 0 ? (
          <EmptyState
            actionLabel="Create binding"
            description="No bindings exist yet. Create an Elasticsearch binding before runtime snapshots can be tracked."
            onAction={() => onNavigate("integrations")}
            title="No runtime contexts yet"
          />
        ) : (
          <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800">
            <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-950 dark:text-slate-400">
                <tr>
                  <th className="px-4 py-3 font-medium">Binding</th>
                  <th className="px-4 py-3 font-medium">Runtime snapshot</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Diff vs current profile</th>
                  <th className="px-4 py-3 font-medium">Latest job</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white dark:divide-slate-800 dark:bg-slate-900">
                {bindings.map((binding) => (
                  <tr key={binding.id}>
                    <td className="px-4 py-3 align-top">
                      <div className="font-medium text-slate-950 dark:text-slate-50">{binding.name}</div>
                      <div className="text-xs text-slate-500 dark:text-slate-400">{binding.profile_name} · {binding.index_name}</div>
                      {binding.filter_field && binding.filter_value ? (
                        <div className="mt-1 text-xs text-slate-400 dark:text-slate-500">
                          {binding.filter_field} = {binding.filter_value}
                        </div>
                      ) : null}
                    </td>
                    <td className="max-w-[260px] px-4 py-3 align-top text-xs text-slate-500 dark:text-slate-400">
                      <div className="font-mono text-slate-700 dark:text-slate-300">{binding.active_snapshot_version ?? "Not created"}</div>
                      {binding.pending_snapshot_version ? <div className="mt-1">Pending: {binding.pending_snapshot_version}</div> : null}
                      <div className="mt-1">Aliases: {binding.snapshot_aliases_total} active / {binding.current_aliases_total} current</div>
                    </td>
                    <td className="px-4 py-3 align-top">
                      <StatusBadge status={binding.status} />
                      {binding.rollback_available ? (
                        <div className="mt-2 flex items-center gap-1 text-xs text-slate-500 dark:text-slate-400">
                          <RotateCcw className="h-3 w-3" /> rollback available
                        </div>
                      ) : null}
                    </td>
                    <td className="px-4 py-3 align-top">
                      <DiffBadge binding={binding} />
                    </td>
                    <td className="px-4 py-3 align-top text-xs text-slate-500 dark:text-slate-400">
                      {binding.latest_job_id ? (
                        <>
                          <div>Job #{binding.latest_job_id}</div>
                          <StatusBadge status={binding.latest_job_status ?? "unknown"} />
                          {binding.latest_job_error ? <div className="mt-1 text-red-600 dark:text-red-300">{binding.latest_job_error}</div> : null}
                        </>
                      ) : (
                        "No jobs"
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

function DiffBadge({ binding }: { binding: SnapshotBindingState }) {
  if (!binding.active_snapshot_version) {
    return <span className="text-xs text-slate-500 dark:text-slate-400">No active snapshot</span>;
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
            <CardTitle>Snapshot history</CardTitle>
            <CardDescription>Recent enrichment jobs that created, activated, or failed runtime snapshots.</CardDescription>
          </div>
          <Button onClick={() => onNavigate("integrations")} variant="secondary">
            <History className="mr-2 h-4 w-4" />
            View enrichment jobs
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
          <div className="space-y-3">
            {history.map((item) => (
              <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-800" key={item.job_id}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="font-medium text-slate-950 dark:text-slate-50">Job #{item.job_id}</div>
                      <StatusBadge status={item.status} />
                      {item.rollback_available ? <Badge className="bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">rollback available</Badge> : null}
                    </div>
                    <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">{item.binding_name} · {item.profile_name}</div>
                  </div>
                  <div className="max-w-md text-right text-xs text-slate-500 dark:text-slate-400">
                    <div className="font-mono text-slate-700 dark:text-slate-300">{item.snapshot_version ?? "No snapshot version"}</div>
                    {item.checksum ? <div>checksum {item.checksum.slice(0, 12)}</div> : null}
                  </div>
                </div>
                <div className="mt-3 grid gap-2 text-xs text-slate-500 dark:text-slate-400 md:grid-cols-4">
                  <span>Aliases: {item.alias_entries_total}</span>
                  <span>Seen: {item.documents_seen}</span>
                  <span>Enriched: {item.documents_enriched}</span>
                  <span>Failed: {item.documents_failed}</span>
                </div>
                <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-500 dark:text-slate-400">
                  {item.alias_name ? <span>Alias: {item.alias_name}</span> : null}
                  {item.target_index ? <span>Target: {item.target_index}</span> : null}
                  {item.previous_snapshot_version ? <span>Previous: {item.previous_snapshot_version}</span> : null}
                </div>
                {item.error_message ? (
                  <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-950/40 dark:text-red-200">
                    {item.error_message}
                  </div>
                ) : null}
              </div>
            ))}
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

function StatusBadge({ status }: { status: string }) {
  const normalized = status.replace(/_/g, " ");
  const className =
    status === "ok" || status === "ready" || status === "succeeded" || status === "enabled"
      ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
      : status === "failed" || status === "degraded"
        ? "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300"
        : status === "stale" || status === "updating" || status === "running" || status === "queued" || status === "unknown"
          ? "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
          : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300";

  return <Badge className={className}>{normalized}</Badge>;
}
