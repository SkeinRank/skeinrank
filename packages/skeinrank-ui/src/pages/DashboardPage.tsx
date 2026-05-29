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
import { areLegacyWriteToolsEnabled, LEGACY_WRITE_TOOLS_LOCKED_MESSAGE } from "../config";
import { cn } from "../lib/utils";
import {
  ConsolePage,
  getConsoleToneForStatus,
  MasterDetailLayout,
  MetricPill,
  SectionCard,
} from "../components/layout/ConsolePrimitives";
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

type RuntimeMetric = {
  label: string;
  value: string | number;
  helper: string;
  tone: "cyan" | "emerald" | "violet" | "amber";
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

  const legacyWriteToolsEnabled = areLegacyWriteToolsEnabled();

  return (
    <ConsolePage>
      {!legacyWriteToolsEnabled ? <LegacyWriteLockdownNotice /> : null}
      <MasterDetailLayout asideWidthClassName="xl:grid-cols-[minmax(0,1fr)_330px] 2xl:grid-cols-[minmax(0,1fr)_380px]">
        <CommandCenter summary={summary} onNavigate={onNavigate} />
        <NextActions summary={summary} onNavigate={onNavigate} />
      </MasterDetailLayout>

      <RuntimeStatus summary={summary} />

      <MasterDetailLayout>
        <BindingHealth bindings={summary.bindings} onNavigate={onNavigate} />
        <RecentJobs jobs={summary.recent_jobs} onNavigate={onNavigate} />
      </MasterDetailLayout>

      <SystemReadiness summary={summary} />
    </ConsolePage>
  );
}

function getSetupItems(setup: DashboardSetupChecklist): SetupItem[] {
  const legacyWriteToolsEnabled = areLegacyWriteToolsEnabled();
  return legacyWriteToolsEnabled ? [
    {
      done: setup.has_profile,
      label: "Create terminology",
      description: "Define the vocabulary.",
      actionLabel: "Open Terms",
      section: "terms",
    },
    {
      done: setup.has_terms,
      label: "Map aliases",
      description: "Normalize noisy terms.",
      actionLabel: "Open Terms",
      section: "terms",
    },
    {
      done: setup.has_binding,
      label: "Bind an index",
      description: "Attach a profile to search.",
      actionLabel: "Open Integrations",
      section: "integrations",
    },
    {
      done: setup.has_successful_enrichment,
      label: "Run enrichment",
      description: "Build runtime context.",
      actionLabel: "Run Enrichment",
      section: "integrations",
    },
    {
      done: setup.has_runtime_snapshot,
      label: "Pin snapshot",
      description: "Serve a safe version.",
      actionLabel: "Open Snapshots",
      section: "snapshots",
    },
  ] : [
    {
      done: setup.has_profile,
      label: "Import terminology",
      description: "Keep terms in GitOps/YAML or proposals.",
      actionLabel: "View schema",
      section: "snapshots",
    },
    {
      done: setup.has_terms,
      label: "Review aliases",
      description: "Inspect canonicalized terms before rollout.",
      actionLabel: "View schema",
      section: "snapshots",
    },
    {
      done: setup.has_binding,
      label: "Provision binding",
      description: "Configure search contexts via deploy/runbook flow.",
      actionLabel: "View snapshots",
      section: "snapshots",
    },
    {
      done: setup.has_successful_enrichment,
      label: "Verify rollout",
      description: "Run controlled enrichment outside manual UI clicks.",
      actionLabel: "Open Playground",
      section: "search-playground",
    },
    {
      done: setup.has_runtime_snapshot,
      label: "Pin snapshot",
      description: "Serve immutable runtime versions.",
      actionLabel: "Open Snapshots",
      section: "snapshots",
    },
  ];
}

function getAttentionCount(summary: DashboardSummary) {
  return (
    summary.counts.stale_bindings +
    summary.counts.failed_bindings +
    summary.counts.running_jobs +
    summary.counts.failed_jobs
  );
}

function getPrimaryBinding(summary: DashboardSummary) {
  return (
    summary.bindings.find((binding) => binding.status === "ready") ??
    summary.bindings[0] ??
    null
  );
}

function CommandCenter({
  summary,
  onNavigate,
}: {
  summary: DashboardSummary;
  onNavigate: (section: AppSection) => void;
}) {
  const items = getSetupItems(summary.setup);
  const completed = items.filter((item) => item.done).length;
  const progress = Math.round((completed / items.length) * 100);
  const nextItem = items.find((item) => !item.done);
  const runtimeReady = completed === items.length;
  const primaryBinding = getPrimaryBinding(summary);
  const latestJob = summary.recent_jobs[0] ?? null;

  const heroMetrics: RuntimeMetric[] = [
    {
      label: "Profiles",
      value: summary.counts.profiles,
      helper: `${summary.counts.canonical_terms} canonical terms`,
      tone: "cyan",
    },
    {
      label: "Aliases",
      value: summary.counts.aliases,
      helper: "runtime dictionary entries",
      tone: "violet",
    },
    {
      label: "Ready bindings",
      value: summary.counts.ready_bindings,
      helper: `${summary.counts.bindings} total bindings`,
      tone: "emerald",
    },
    {
      label: "Latest job",
      value: latestJob ? `#${latestJob.id}` : "—",
      helper: latestJob ? latestJob.status.replace(/_/g, " ") : "no rollout yet",
      tone: latestJob?.status === "failed" ? "amber" : "emerald",
    },
  ];

  return (
    <Card className="relative overflow-hidden border-slate-200 bg-white shadow-md shadow-slate-200/70 dark:border-slate-800 dark:bg-slate-950 dark:shadow-black/30">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(14,165,233,0.14),transparent_32%),radial-gradient(circle_at_top_right,rgba(139,92,246,0.12),transparent_34%)] dark:bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.12),transparent_30%),radial-gradient(circle_at_top_right,rgba(124,58,237,0.16),transparent_34%)]" />
      <CardContent className="relative p-4 sm:p-5">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0 max-w-3xl">
            <div className="inline-flex items-center gap-2 rounded-full border border-cyan-200 bg-cyan-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-cyan-700 dark:border-cyan-500/30 dark:bg-cyan-500/10 dark:text-cyan-200">
              <span className="h-2 w-2 rounded-full bg-emerald-500 shadow-[0_0_18px_rgba(16,185,129,0.8)]" />
              Runtime control center
            </div>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight text-slate-950 dark:text-white sm:text-3xl">
              {runtimeReady
                ? "Production search context is ready."
                : "Finish the terminology runtime path."}
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600 dark:text-slate-300">
              {runtimeReady
                ? "SkeinRank has a governed profile, a ready binding, and a pinned snapshot serving canonical context to search."
                : "Complete the setup path to move aliases from draft terminology into a safe runtime snapshot."}
            </p>
          </div>

          <div className="w-full rounded-2xl border border-slate-200 bg-white/80 p-3 shadow-sm backdrop-blur dark:border-slate-800 dark:bg-slate-900/70 xl:w-72">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
                  Setup progress
                </div>
                <div className="mt-1 text-2xl font-semibold tracking-tight text-slate-950 dark:text-slate-50">
                  {progress}%
                </div>
              </div>
              <Badge
                className={
                  runtimeReady
                    ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-200"
                    : "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-200"
                }
              >
                {completed}/{items.length} ready
              </Badge>
            </div>
            <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
              <div
                className="h-full rounded-full bg-gradient-to-r from-cyan-500 via-blue-500 to-violet-500 transition-[width]"
                style={{ width: `${progress}%` }}
              />
            </div>
            <div className="mt-3 truncate text-xs text-slate-500 dark:text-slate-400">
              {primaryBinding?.snapshot_version
                ? `Snapshot ${primaryBinding.snapshot_version}`
                : primaryBinding?.pending_snapshot_version
                  ? `Pending ${primaryBinding.pending_snapshot_version}`
                  : "No runtime snapshot pinned yet"}
            </div>
          </div>
        </div>

        <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          {heroMetrics.map((metric) => (
            <MetricPill
              className="bg-white/85 backdrop-blur dark:bg-slate-900/75"
              helper={metric.helper}
              key={metric.label}
              label={metric.label}
              tone={metric.tone}
              value={metric.value}
            />
          ))}
        </div>

        <div className="mt-4">
          <CompactSetupChecklist items={items} />
        </div>

        {nextItem ? (
          <div className="mt-4 flex flex-col gap-3 rounded-2xl border border-amber-200 bg-amber-50/90 p-3 dark:border-amber-500/30 dark:bg-amber-500/10 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="text-sm font-medium text-amber-900 dark:text-amber-100">
                Next step: {nextItem.label}
              </div>
              <div className="mt-1 text-xs text-amber-700 dark:text-amber-200">
                {nextItem.description}
              </div>
            </div>
            <Button onClick={() => onNavigate(nextItem.section)} variant="secondary">
              {nextItem.actionLabel}
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </div>
        ) : (
          <div className="mt-4 flex flex-col gap-3 rounded-2xl border border-emerald-200 bg-emerald-50/90 p-3 dark:border-emerald-500/30 dark:bg-emerald-500/10 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="text-sm font-medium text-emerald-900 dark:text-emerald-100">
                Runtime path is ready
              </div>
              <div className="mt-1 text-xs text-emerald-700 dark:text-emerald-200">
                Test canonicalization and search behavior from the playground.
              </div>
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
    <div className="grid gap-2 lg:grid-cols-5">
      {items.map((item, index) => (
        <div
          className={cn(
            "group flex min-w-0 items-center gap-2 rounded-2xl border p-2.5 transition-colors",
            item.done
              ? "border-emerald-200 bg-emerald-50/70 dark:border-emerald-500/25 dark:bg-emerald-500/10"
              : "border-slate-200 bg-white/70 dark:border-slate-800 dark:bg-slate-900/70",
          )}
          key={item.label}
        >
          <div className="flex h-7 w-7 flex-none items-center justify-center rounded-full border border-slate-200 bg-white text-xs font-semibold text-slate-500 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-400">
            {item.done ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-300" />
            ) : (
              index + 1
            )}
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-medium text-slate-950 dark:text-slate-50">
              {item.label}
            </div>
            <div className="mt-0.5 truncate text-xs text-slate-500 dark:text-slate-400">
              {item.description}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function NextActions({
  summary,
  onNavigate,
}: {
  summary: DashboardSummary;
  onNavigate: (section: AppSection) => void;
}) {
  const attentionCount = getAttentionCount(summary);

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
    <Card className="h-full border-slate-200 bg-white shadow-md shadow-slate-200/60 dark:border-slate-800 dark:bg-slate-950 dark:shadow-black/30">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>Next actions</CardTitle>
            <CardDescription>Jump to the next control-plane step.</CardDescription>
          </div>
          <Badge
            className={cn(
              "shrink-0 whitespace-nowrap px-3",
              attentionCount > 0
                ? "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-200"
                : "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-200",
            )}
          >
            {attentionCount > 0 ? `${attentionCount} attention` : "No alerts"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="grid gap-2.5">
        {actions.map((action) => (
          <button
            className="group flex w-full items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50/80 px-3 py-3 text-left transition-colors hover:border-slate-300 hover:bg-white dark:border-slate-800 dark:bg-slate-900/70 dark:hover:border-slate-700 dark:hover:bg-slate-900"
            key={action.label}
            onClick={() => onNavigate(action.section)}
            type="button"
          >
            <span className="flex h-9 w-9 flex-none items-center justify-center rounded-xl bg-white text-slate-600 shadow-sm ring-1 ring-slate-200 dark:bg-slate-950 dark:text-slate-300 dark:ring-slate-800">
              <action.icon className="h-4 w-4" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-semibold text-slate-950 dark:text-slate-50">
                {action.label}
              </span>
              <span className="block truncate text-xs font-normal text-slate-500 dark:text-slate-400">
                {action.helper}
              </span>
            </span>
            <ArrowRight className="h-4 w-4 flex-none text-slate-300 transition-colors group-hover:text-slate-500 dark:text-slate-700 dark:group-hover:text-slate-400" />
          </button>
        ))}
      </CardContent>
    </Card>
  );
}

function RuntimeStatus({ summary }: { summary: DashboardSummary }) {
  const attentionCount = getAttentionCount(summary);
  const primaryBinding = getPrimaryBinding(summary);

  const cards = [
    {
      label: "Profiles",
      value: summary.counts.profiles,
      helper: `${summary.counts.canonical_terms} canonical terms`,
      icon: Database,
      status: "ready",
    },
    {
      label: "Aliases",
      value: summary.counts.aliases,
      helper: "runtime dictionary entries",
      icon: Sparkles,
      status: "ready",
    },
    {
      label: "Runtime binding",
      value: summary.counts.ready_bindings,
      helper: primaryBinding ? primaryBinding.name : `${summary.counts.bindings} total bindings`,
      icon: Plug,
      status: primaryBinding?.status ?? "never_enriched",
    },
    {
      label: "Needs attention",
      value: attentionCount,
      helper: "stale, failed, or active jobs",
      icon: AlertCircle,
      status: attentionCount > 0 ? "degraded" : "ok",
    },
  ];

  return (
    <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      {cards.map((card) => (
        <MetricPill
          helper={
            <span className="flex items-center justify-between gap-3">
              <span className="truncate">{card.helper}</span>
              <StatusBadge status={card.status} />
            </span>
          }
          icon={card.icon}
          key={card.label}
          label={card.label}
          tone={getConsoleToneForStatus(card.status)}
          value={card.value}
        />
      ))}
    </section>
  );
}

function BindingHealth({
  bindings,
  onNavigate,
}: {
  bindings: DashboardBindingSummary[];
  onNavigate: (section: AppSection) => void;
}) {
  return (
    <SectionCard
      actions={
        <Button onClick={() => onNavigate(areLegacyWriteToolsEnabled() ? "integrations" : "snapshots")} variant="secondary">
          <Plug className="mr-2 h-4 w-4" />
          {areLegacyWriteToolsEnabled() ? "Open integrations" : "View runtime contexts"}
        </Button>
      }
      description="Runtime contexts that drive production search behavior."
      title="Binding health"
    >
        {bindings.length === 0 ? (
          <EmptyState
            actionLabel={areLegacyWriteToolsEnabled() ? "Create binding" : "View snapshot workspace"}
            description={areLegacyWriteToolsEnabled() ? "No Elasticsearch bindings exist yet. Create one after you add a terminology profile." : "No runtime contexts exist yet. Configure bindings through GitOps/API runbooks, then inspect them in Schema & Snapshots."}
            onAction={() => onNavigate(areLegacyWriteToolsEnabled() ? "integrations" : "snapshots")}
            title="No bindings configured"
          />
        ) : (
          <div className="overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-800">
            <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-[0.16em] text-slate-500 dark:bg-slate-900 dark:text-slate-400">
                <tr>
                  <th className="px-4 py-3 font-semibold">Binding</th>
                  <th className="px-4 py-3 font-semibold">Index</th>
                  <th className="px-4 py-3 font-semibold">Status</th>
                  <th className="px-4 py-3 font-semibold">Snapshot</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white dark:divide-slate-800 dark:bg-slate-950">
                {bindings.map((binding) => (
                  <tr className="transition-colors hover:bg-slate-50 dark:hover:bg-slate-900/80" key={binding.id}>
                    <td className="px-4 py-3">
                      <div className="font-semibold text-slate-950 dark:text-slate-50">{binding.name}</div>
                      <div className="text-xs text-slate-500 dark:text-slate-400">{binding.profile_name}</div>
                    </td>
                    <td className="px-4 py-3 text-slate-600 dark:text-slate-300">{binding.index_name}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={binding.status} />
                    </td>
                    <td className="max-w-[280px] truncate px-4 py-3 text-xs text-slate-500 dark:text-slate-400">
                      {binding.snapshot_version ?? binding.pending_snapshot_version ?? "Not created"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </SectionCard>
  );
}

function RecentJobs({
  jobs,
  onNavigate,
}: {
  jobs: DashboardRecentJob[];
  onNavigate: (section: AppSection) => void;
}) {
  return (
    <SectionCard
      actions={
        <Button onClick={() => onNavigate(areLegacyWriteToolsEnabled() ? "integrations" : "snapshots")} variant="secondary">
          <GitBranch className="mr-2 h-4 w-4" />
          {areLegacyWriteToolsEnabled() ? "View jobs" : "View snapshots"}
        </Button>
      }
      description="Latest rollout and snapshot activity."
      title="Recent enrichment jobs"
    >
        {jobs.length === 0 ? (
          <EmptyState
            actionLabel={areLegacyWriteToolsEnabled() ? "Run enrichment" : "Open Playground"}
            description={areLegacyWriteToolsEnabled() ? "No enrichment jobs have run yet. Start from the Integrations page after creating a binding." : "No enrichment jobs have run yet. Trigger rollout through CI/CD or an operator runbook, then verify behavior in Playground."}
            onAction={() => onNavigate(areLegacyWriteToolsEnabled() ? "integrations" : "search-playground")}
            title="No enrichment jobs yet"
          />
        ) : (
          <div className="space-y-2.5">
            {jobs.map((job) => (
              <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-3 dark:border-slate-800 dark:bg-slate-900/60" key={job.id}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="font-semibold text-slate-950 dark:text-slate-50">Job #{job.id}</div>
                  <StatusBadge status={job.status} />
                </div>
                <div className="mt-1 truncate text-sm text-slate-500 dark:text-slate-400">
                  {job.binding_name} · {job.source_index}
                </div>
                <div className="mt-3 grid gap-2 text-xs text-slate-500 dark:text-slate-400 sm:grid-cols-3">
                  <span className="rounded-lg bg-white px-2 py-1 dark:bg-slate-950">Seen: {job.documents_seen}</span>
                  <span className="rounded-lg bg-white px-2 py-1 dark:bg-slate-950">Enriched: {job.documents_enriched}</span>
                  <span className="rounded-lg bg-white px-2 py-1 dark:bg-slate-950">Failed: {job.documents_failed}</span>
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
    </SectionCard>
  );
}

function SystemReadiness({ summary }: { summary: DashboardSummary }) {
  const entries = Object.entries(summary.readiness);

  return (
    <SectionCard
      className="shadow-sm shadow-slate-200/50 dark:shadow-black/20"
      contentClassName="grid gap-2 md:grid-cols-2 xl:grid-cols-5"
      description="Service checks for onboarding. Use Grafana for deeper telemetry."
      title="System readiness"
    >
        {entries.map(([name, item]) => (
          <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-3 dark:border-slate-800 dark:bg-slate-900/60" key={name}>
            <div className="flex items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
                <Settings2 className="h-4 w-4 flex-none text-slate-400" />
                <span className="truncate">{name.replace(/_/g, " ")}</span>
              </div>
              <StatusBadge status={item.status} />
            </div>
            <p className="mt-2 line-clamp-2 text-xs text-slate-500 dark:text-slate-400">
              {item.message ?? (item.configured ? "Configured" : "Not configured")}
            </p>
          </div>
        ))}
    </SectionCard>
  );
}


function LegacyWriteLockdownNotice() {
  return (
    <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
      <div className="font-semibold">Legacy dashboard is read-only</div>
      <p className="mt-1">{LEGACY_WRITE_TOOLS_LOCKED_MESSAGE}</p>
    </div>
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
    <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50/70 p-6 text-center dark:border-slate-700 dark:bg-slate-900/40">
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
      ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-200"
      : status === "failed" || status === "degraded"
        ? "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-200"
        : status === "stale" || status === "updating" || status === "running" || status === "queued" || status === "unknown"
          ? "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-200"
          : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300";

  return <Badge className={className}>{normalized}</Badge>;
}
