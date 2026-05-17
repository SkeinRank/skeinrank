import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Circle,
  Database,
  GitBranch,
  Plug,
  Search,
  Settings2,
  Sparkles,
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
import { getDashboardSummary } from "../lib/api";
import type {
  DashboardBindingSummary,
  DashboardRecentJob,
  DashboardSetupChecklist,
  DashboardSummary,
} from "../types";

type SetupItem = {
  done: boolean;
  label: string;
  description: string;
  actionLabel: string;
  section: AppSection;
};

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
    <div className="space-y-5">
      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px] 2xl:grid-cols-[minmax(0,1fr)_420px]">
        <CommandCenter summary={summary} onNavigate={onNavigate} />
        <NextActions summary={summary} onNavigate={onNavigate} />
      </section>

      <RuntimeStatus summary={summary} />

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px] 2xl:grid-cols-[minmax(0,1fr)_460px]">
        <BindingHealth bindings={summary.bindings} onNavigate={onNavigate} />
        <RecentJobs jobs={summary.recent_jobs} onNavigate={onNavigate} />
      </section>

      <SystemReadiness summary={summary} />
    </div>
  );
}

function getSetupItems(setup: DashboardSetupChecklist): SetupItem[] {
  return [
    {
      done: setup.has_profile,
      label: "Create or import terminology",
      description: "Define the domain vocabulary.",
      actionLabel: "Open Terms",
      section: "terms",
    },
    {
      done: setup.has_terms,
      label: "Add canonical terms and aliases",
      description: "Map noisy language to canonical values.",
      actionLabel: "Open Terms",
      section: "terms",
    },
    {
      done: setup.has_binding,
      label: "Create an Elasticsearch binding",
      description: "Connect a profile to an index.",
      actionLabel: "Open Integrations",
      section: "integrations",
    },
    {
      done: setup.has_successful_enrichment,
      label: "Run enrichment successfully",
      description: "Build runtime output for search.",
      actionLabel: "Run Enrichment",
      section: "integrations",
    },
    {
      done: setup.has_runtime_snapshot,
      label: "Verify a ready runtime snapshot",
      description: "Confirm search uses pinned terminology.",
      actionLabel: "Open Snapshots",
      section: "snapshots",
    },
  ];
}

function CommandCenter({ summary, onNavigate }: { summary: DashboardSummary; onNavigate: (section: AppSection) => void }) {
  const items = getSetupItems(summary.setup);
  const completed = items.filter((item) => item.done).length;
  const progress = Math.round((completed / items.length) * 100);
  const nextItem = items.find((item) => !item.done);

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle>Welcome to SkeinRank</CardTitle>
            <CardDescription>Command center for setup, rollout, and runtime health.</CardDescription>
          </div>
          <Badge
            className={
              completed === items.length
                ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
                : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"
            }
          >
            {completed}/{items.length} ready
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <div className="flex items-center justify-between text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
            <span>Setup progress</span>
            <span>{progress}%</span>
          </div>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-900">
            <div
              className="h-full rounded-full bg-slate-950 transition-[width] dark:bg-slate-100"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        <CompactSetupChecklist items={items} />

        {nextItem ? (
          <div className="flex flex-col gap-3 rounded-xl border border-amber-200 bg-amber-50 p-3 dark:border-amber-900/60 dark:bg-amber-950/30 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="text-sm font-medium text-amber-900 dark:text-amber-100">Next step: {nextItem.label}</div>
              <div className="mt-1 text-xs text-amber-700 dark:text-amber-200">{nextItem.description}</div>
            </div>
            <Button onClick={() => onNavigate(nextItem.section)} variant="secondary">
              {nextItem.actionLabel}
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </div>
        ) : (
          <div className="flex flex-col gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-3 dark:border-emerald-900/60 dark:bg-emerald-950/30 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="text-sm font-medium text-emerald-900 dark:text-emerald-100">Runtime path is ready</div>
              <div className="mt-1 text-xs text-emerald-700 dark:text-emerald-200">Test canonicalization and search behavior from the playground.</div>
            </div>
            <Button onClick={() => onNavigate("search-playground")} variant="secondary">
              Open Search Playground
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function CompactSetupChecklist({ items }: { items: SetupItem[] }) {
  return (
    <div className="grid gap-2 lg:grid-cols-2 2xl:grid-cols-5">
      {items.map((item, index) => (
        <div
          className="flex min-w-0 gap-2 rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-950"
          key={item.label}
        >
          <div className="mt-0.5 flex-none">
            {item.done ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
            ) : (
              <Circle className="h-4 w-4 text-slate-300 dark:text-slate-700" />
            )}
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-medium text-slate-950 dark:text-slate-50">
              {index + 1}. {item.label}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <Badge
                className={
                  item.done
                    ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
                    : "bg-slate-100 text-slate-500 dark:bg-slate-900 dark:text-slate-400"
                }
              >
                {item.done ? "Done" : "Not started"}
              </Badge>
              <span className="text-xs text-slate-500 dark:text-slate-400">{item.description}</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function NextActions({ summary, onNavigate }: { summary: DashboardSummary; onNavigate: (section: AppSection) => void }) {
  const attentionCount =
    summary.counts.stale_bindings +
    summary.counts.failed_bindings +
    summary.counts.running_jobs +
    summary.counts.failed_jobs;

  const actions = [
    {
      label: "Manage terminology",
      helper: "Profiles, terms, aliases",
      icon: Database,
      section: "terms" as const,
    },
    {
      label: "Configure bindings",
      helper: "Index mapping and rollout",
      icon: Plug,
      section: "integrations" as const,
    },
    {
      label: "Test search behavior",
      helper: "Canonical query preview",
      icon: Search,
      section: "search-playground" as const,
    },
    {
      label: "Review suggestions",
      helper: "Approve terminology changes",
      icon: Sparkles,
      section: "suggestions" as const,
    },
  ];

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>Next actions</CardTitle>
            <CardDescription>Jump to the next control-plane step.</CardDescription>
          </div>
          <Badge
            className={
              attentionCount > 0
                ? "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
                : "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
            }
          >
            {attentionCount > 0 ? `${attentionCount} attention` : "No alerts"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="grid gap-2">
        {actions.map((action) => (
          <Button
            className="h-auto justify-start gap-3 px-3 py-2 text-left"
            key={action.label}
            onClick={() => onNavigate(action.section)}
            variant="secondary"
          >
            <action.icon className="h-4 w-4 flex-none" />
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium">{action.label}</span>
              <span className="block truncate text-xs font-normal text-slate-500 dark:text-slate-400">{action.helper}</span>
            </span>
          </Button>
        ))}
      </CardContent>
    </Card>
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
    <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      {cards.map((card) => (
        <Card key={card.label}>
          <CardContent className="py-4">
            <div className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">{card.label}</div>
            <div className="mt-2 text-2xl font-semibold tracking-tight text-slate-950 dark:text-slate-50">
              {card.value}
            </div>
            <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{card.helper}</div>
          </CardContent>
        </Card>
      ))}
    </section>
  );
}

function BindingHealth({ bindings, onNavigate }: { bindings: DashboardBindingSummary[]; onNavigate: (section: AppSection) => void }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle>Binding health</CardTitle>
            <CardDescription>Runtime contexts that drive production search behavior.</CardDescription>
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
      <CardHeader className="pb-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle>Recent enrichment jobs</CardTitle>
            <CardDescription>Latest rollout and snapshot activity.</CardDescription>
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
          <div className="space-y-2">
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
      <CardHeader className="pb-3">
        <CardTitle>System readiness</CardTitle>
        <CardDescription>Service checks for onboarding. Use Grafana for deeper telemetry.</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-2 md:grid-cols-2 xl:grid-cols-5">
        {entries.map(([name, item]) => (
          <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800" key={name}>
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
                <Settings2 className="h-4 w-4 text-slate-400" />
                {name.replace(/_/g, " ")}
              </div>
              <StatusBadge status={item.status} />
            </div>
            <p className="mt-2 line-clamp-2 text-xs text-slate-500 dark:text-slate-400">
              {item.message ?? (item.configured ? "Configured" : "Not configured")}
            </p>
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
