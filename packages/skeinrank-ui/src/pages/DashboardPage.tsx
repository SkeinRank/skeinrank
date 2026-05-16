import { useQuery } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, Circle, Database, GitBranch, Plug, Search, Settings2 } from "lucide-react";

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
import { getDashboardSummary } from "../lib/api";
import type { DashboardBindingSummary, DashboardRecentJob, DashboardSetupChecklist, DashboardSummary } from "../types";

export function DashboardPage({
  onNavigate,
}: {
  onNavigate: (section: AppSection) => void;
}) {
  const summaryQuery = useQuery({
    queryKey: ["dashboard", "summary"],
    queryFn: getDashboardSummary,
  });

  if (summaryQuery.isLoading) {
    return (
      <Card>
        <CardContent className="text-sm text-slate-500 dark:text-slate-400">
          Loading dashboard summary...
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
            <div className="font-medium">Unable to load dashboard summary</div>
            <div className="mt-1">
              {summaryQuery.error instanceof Error
                ? summaryQuery.error.message
                : "Check the governance API and try again."}
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
      <section className="grid gap-4 xl:grid-cols-[1.35fr_0.65fr]">
        <Card>
          <CardHeader>
            <CardTitle>Welcome to SkeinRank</CardTitle>
            <CardDescription>
              Follow the setup checklist from an empty governance database to a ready runtime search context.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <SetupChecklist setup={summary.setup} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Quick actions</CardTitle>
            <CardDescription>Jump to the next control-plane step.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-2">
            <Button className="justify-start" onClick={() => onNavigate("terms")} variant="secondary">
              <Database className="mr-2 h-4 w-4" />
              Create or import terminology
            </Button>
            <Button className="justify-start" onClick={() => onNavigate("integrations")} variant="secondary">
              <Plug className="mr-2 h-4 w-4" />
              Configure Elasticsearch binding
            </Button>
            <Button className="justify-start" onClick={() => onNavigate("suggestions")} variant="secondary">
              <Search className="mr-2 h-4 w-4" />
              Review terminology suggestions
            </Button>
          </CardContent>
        </Card>
      </section>

      <RuntimeStatus summary={summary} />

      <section className="grid gap-4 xl:grid-cols-[1fr_0.85fr]">
        <BindingHealth bindings={summary.bindings} onNavigate={onNavigate} />
        <RecentJobs jobs={summary.recent_jobs} onNavigate={onNavigate} />
      </section>

      <SystemReadiness summary={summary} />
    </div>
  );
}

function SetupChecklist({ setup }: { setup: DashboardSetupChecklist }) {
  const items = [
    {
      done: setup.has_profile,
      label: "Create or import a terminology profile",
      description: "Define the domain vocabulary that SkeinRank will canonicalize.",
    },
    {
      done: setup.has_terms,
      label: "Add canonical terms and aliases",
      description: "Map noisy user language such as k8s or pg to canonical values.",
    },
    {
      done: setup.has_binding,
      label: "Create an Elasticsearch binding",
      description: "Connect a profile to an index, text fields, and target enrichment field.",
    },
    {
      done: setup.has_successful_enrichment,
      label: "Run enrichment successfully",
      description: "Build an immutable runtime snapshot and enrich the target index.",
    },
    {
      done: setup.has_runtime_snapshot,
      label: "Use a ready runtime snapshot",
      description: "Confirm at least one binding can serve pinned production terminology.",
    },
  ];

  return (
    <div className="space-y-3">
      {items.map((item, index) => (
        <div
          className="flex gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-950"
          key={item.label}
        >
          <div className="mt-0.5">
            {item.done ? (
              <CheckCircle2 className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
            ) : (
              <Circle className="h-5 w-5 text-slate-300 dark:text-slate-700" />
            )}
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium text-slate-950 dark:text-slate-50">
                {index + 1}. {item.label}
              </span>
              <Badge
                className={
                  item.done
                    ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
                    : "bg-slate-100 text-slate-500 dark:bg-slate-900 dark:text-slate-400"
                }
              >
                {item.done ? "Done" : "Not started"}
              </Badge>
            </div>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              {item.description}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

function RuntimeStatus({ summary }: { summary: DashboardSummary }) {
  const cards = [
    {
      label: "Profiles",
      value: summary.counts.profiles,
      helper: `${summary.counts.canonical_terms} canonical terms`,
    },
    {
      label: "Aliases",
      value: summary.counts.aliases,
      helper: "runtime dictionary entries",
    },
    {
      label: "Ready bindings",
      value: summary.counts.ready_bindings,
      helper: `${summary.counts.bindings} total bindings`,
    },
    {
      label: "Needs attention",
      value:
        summary.counts.stale_bindings +
        summary.counts.failed_bindings +
        summary.counts.running_jobs +
        summary.counts.failed_jobs,
      helper: "stale, failed, or active jobs",
    },
  ];

  return (
    <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {cards.map((card) => (
        <Card key={card.label}>
          <CardContent>
            <div className="text-sm text-slate-500 dark:text-slate-400">{card.label}</div>
            <div className="mt-2 text-3xl font-semibold tracking-tight text-slate-950 dark:text-slate-50">
              {card.value}
            </div>
            <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">{card.helper}</div>
          </CardContent>
        </Card>
      ))}
    </section>
  );
}

function BindingHealth({ bindings, onNavigate }: { bindings: DashboardBindingSummary[]; onNavigate: (section: AppSection) => void }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle>Binding health</CardTitle>
            <CardDescription>Product-state view of Elasticsearch runtime contexts.</CardDescription>
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
            description="No Elasticsearch bindings exist yet. Create one after you add a terminology profile."
            onAction={() => onNavigate("integrations")}
            title="No bindings configured"
          />
        ) : (
          <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800">
            <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-950 dark:text-slate-400">
                <tr>
                  <th className="px-4 py-3 font-medium">Binding</th>
                  <th className="px-4 py-3 font-medium">Index</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Snapshot</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white dark:divide-slate-800 dark:bg-slate-900">
                {bindings.map((binding) => (
                  <tr key={binding.id}>
                    <td className="px-4 py-3">
                      <div className="font-medium text-slate-950 dark:text-slate-50">{binding.name}</div>
                      <div className="text-xs text-slate-500 dark:text-slate-400">{binding.profile_name}</div>
                    </td>
                    <td className="px-4 py-3 text-slate-600 dark:text-slate-300">{binding.index_name}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={binding.status} />
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500 dark:text-slate-400">
                      {binding.snapshot_version ?? binding.pending_snapshot_version ?? "Not created"}
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

function RecentJobs({ jobs, onNavigate }: { jobs: DashboardRecentJob[]; onNavigate: (section: AppSection) => void }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle>Recent enrichment jobs</CardTitle>
            <CardDescription>Latest snapshot and index enrichment activity.</CardDescription>
          </div>
          <Button onClick={() => onNavigate("integrations")} variant="secondary">
            <GitBranch className="mr-2 h-4 w-4" />
            View jobs
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {jobs.length === 0 ? (
          <EmptyState
            actionLabel="Run enrichment"
            description="No enrichment jobs have run yet. Start from the Integrations page after creating a binding."
            onAction={() => onNavigate("integrations")}
            title="No enrichment jobs yet"
          />
        ) : (
          <div className="space-y-3">
            {jobs.map((job) => (
              <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800" key={job.id}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="font-medium text-slate-950 dark:text-slate-50">Job #{job.id}</div>
                  <StatusBadge status={job.status} />
                </div>
                <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                  {job.binding_name} · {job.source_index}
                </div>
                <div className="mt-2 grid gap-2 text-xs text-slate-500 dark:text-slate-400 sm:grid-cols-3">
                  <span>Seen: {job.documents_seen}</span>
                  <span>Enriched: {job.documents_enriched}</span>
                  <span>Failed: {job.documents_failed}</span>
                </div>
                {job.error_message ? (
                  <div className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-950/40 dark:text-red-200">
                    {job.error_message}
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

function SystemReadiness({ summary }: { summary: DashboardSummary }) {
  const entries = Object.entries(summary.readiness);

  return (
    <Card>
      <CardHeader>
        <CardTitle>System readiness</CardTitle>
        <CardDescription>
          Human-readable service checks for onboarding. Use Grafana for deeper infrastructure telemetry.
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        {entries.map(([name, item]) => (
          <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800" key={name}>
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-sm font-medium capitalize text-slate-950 dark:text-slate-50">
                <Settings2 className="h-4 w-4 text-slate-400" />
                {name.replace(/_/g, " ")}
              </div>
              <StatusBadge status={item.status} />
            </div>
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              {item.message ?? (item.configured ? "Configured" : "Not configured")}
            </p>
            {item.version ? (
              <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">Version: {item.version}</p>
            ) : null}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function EmptyState({
  actionLabel,
  description,
  onAction,
  title,
}: {
  actionLabel: string;
  description: string;
  onAction: () => void;
  title: string;
}) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 p-6 text-center dark:border-slate-700">
      <div className="text-sm font-medium text-slate-950 dark:text-slate-50">{title}</div>
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
