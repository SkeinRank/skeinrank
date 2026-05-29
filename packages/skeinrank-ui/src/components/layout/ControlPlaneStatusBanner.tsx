import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ShieldAlert } from "lucide-react";

import { getAlertsReport } from "../../lib/api";
import type { AlertingEvent, AlertingReport } from "../../types";
import { Badge } from "../ui/badge";

export function ControlPlaneStatusBanner() {
  const alertsQuery = useQuery({
    queryKey: ["ops", "alerts", "report"],
    queryFn: getAlertsReport,
    refetchOnWindowFocus: false,
    staleTime: 30_000,
  });

  if (!alertsQuery.data || alertsQuery.data.status === "ok" || alertsQuery.data.summary.events_total === 0) {
    return null;
  }

  return <DegradedStateBanner report={alertsQuery.data} />;
}

function DegradedStateBanner({ report }: { report: AlertingReport }) {
  const isCritical = report.severity === "critical";
  const Icon = isCritical ? ShieldAlert : AlertTriangle;
  const primaryEvent = report.events[0] ?? null;

  return (
    <section
      aria-label="Degraded state alert"
      className={
        isCritical
          ? "mt-4 rounded-2xl border border-red-200 bg-red-50 p-4 text-red-900 shadow-sm dark:border-red-900/60 dark:bg-red-950/45 dark:text-red-100"
          : "mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-amber-900 shadow-sm dark:border-amber-900/60 dark:bg-amber-950/45 dark:text-amber-100"
      }
      role={isCritical ? "alert" : "status"}
    >
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span
            className={
              isCritical
                ? "mt-0.5 flex h-9 w-9 flex-none items-center justify-center rounded-2xl bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-200"
                : "mt-0.5 flex h-9 w-9 flex-none items-center justify-center rounded-2xl bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-200"
            }
          >
            <Icon className="h-5 w-5" />
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-sm font-semibold tracking-tight">SkeinRank degraded state</h2>
              <Badge className={isCritical ? "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-100" : "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-100"}>
                {report.severity}
              </Badge>
              <Badge>{report.summary.events_total} event{report.summary.events_total === 1 ? "" : "s"}</Badge>
            </div>
            <p className="mt-1 text-sm leading-6 opacity-90">
              {primaryEvent ? primaryEvent.message : "The control plane reported degraded operational state."}
            </p>
            {primaryEvent ? <EventAction event={primaryEvent} /> : null}
          </div>
        </div>
        <div className="grid gap-2 text-xs lg:min-w-[260px]">
          <div className="flex items-center gap-2 rounded-xl bg-white/60 px-3 py-2 dark:bg-slate-950/35">
            <CheckCircle2 className="h-4 w-4 flex-none" />
            <span>Read-only banner. No webhooks or runtime changes are triggered from UI.</span>
          </div>
          {report.summary.degraded_sources.length > 0 ? (
            <div className="rounded-xl bg-white/60 px-3 py-2 dark:bg-slate-950/35">
              Sources: {report.summary.degraded_sources.join(", ")}
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}

function EventAction({ event }: { event: AlertingEvent }) {
  if (!event.recommended_action) {
    return null;
  }

  return (
    <p className="mt-2 text-xs leading-5 opacity-80">
      Recommended action: {event.recommended_action}
    </p>
  );
}
