import type { HTMLAttributes, ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { cn } from "../../lib/utils";

export type ConsoleTone = "slate" | "cyan" | "emerald" | "violet" | "amber" | "red";

const toneStyles: Record<ConsoleTone, { accent: string; surface: string; text: string }> = {
  slate: {
    accent: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
    surface: "border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950",
    text: "text-slate-600 dark:text-slate-300",
  },
  cyan: {
    accent: "bg-cyan-100 text-cyan-700 dark:bg-cyan-500/15 dark:text-cyan-200",
    surface: "border-cyan-100 bg-cyan-50/35 dark:border-cyan-500/20 dark:bg-cyan-500/5",
    text: "text-cyan-700 dark:text-cyan-200",
  },
  emerald: {
    accent: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-200",
    surface: "border-emerald-100 bg-emerald-50/35 dark:border-emerald-500/20 dark:bg-emerald-500/5",
    text: "text-emerald-700 dark:text-emerald-200",
  },
  violet: {
    accent: "bg-violet-100 text-violet-700 dark:bg-violet-500/15 dark:text-violet-200",
    surface: "border-violet-100 bg-violet-50/35 dark:border-violet-500/20 dark:bg-violet-500/5",
    text: "text-violet-700 dark:text-violet-200",
  },
  amber: {
    accent: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-200",
    surface: "border-amber-100 bg-amber-50/35 dark:border-amber-500/20 dark:bg-amber-500/5",
    text: "text-amber-700 dark:text-amber-200",
  },
  red: {
    accent: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-200",
    surface: "border-red-100 bg-red-50/35 dark:border-red-500/20 dark:bg-red-500/5",
    text: "text-red-700 dark:text-red-200",
  },
};

export interface ConsolePageProps extends HTMLAttributes<HTMLDivElement> {
  maxWidthClassName?: string;
}

export function ConsolePage({ className, maxWidthClassName = "max-w-[1680px]", ...props }: ConsolePageProps) {
  return <div className={cn("mx-auto w-full space-y-4", maxWidthClassName, className)} {...props} />;
}

export interface MasterDetailLayoutProps extends HTMLAttributes<HTMLDivElement> {
  asideWidthClassName?: string;
}

export function MasterDetailLayout({
  asideWidthClassName = "xl:grid-cols-[minmax(0,1fr)_380px] 2xl:grid-cols-[minmax(0,1fr)_420px]",
  className,
  ...props
}: MasterDetailLayoutProps) {
  return <section className={cn("grid gap-4", asideWidthClassName, className)} {...props} />;
}

export interface WorkspaceHeaderProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  actions?: ReactNode;
  description?: ReactNode;
  eyebrow?: ReactNode;
  meta?: ReactNode;
  title: ReactNode;
}

export function WorkspaceHeader({ actions, children, className, description, eyebrow, meta, title, ...props }: WorkspaceHeaderProps) {
  return (
    <Card className={cn("border-slate-200 bg-white shadow-sm shadow-slate-200/50 dark:border-slate-800 dark:bg-slate-950 dark:shadow-black/20", className)} {...props}>
      <CardContent className="p-4 sm:p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            {eyebrow ? (
              <div className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
                {eyebrow}
              </div>
            ) : null}
            <h2 className="text-xl font-semibold tracking-tight text-slate-950 dark:text-slate-50 sm:text-2xl">
              {title}
            </h2>
            {description ? (
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600 dark:text-slate-300">
                {description}
              </p>
            ) : null}
          </div>
          {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
        </div>
        {meta ? <div className="mt-4">{meta}</div> : null}
        {children}
      </CardContent>
    </Card>
  );
}

export interface SectionCardProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  actions?: ReactNode;
  contentClassName?: string;
  description?: ReactNode;
  headerClassName?: string;
  title: ReactNode;
}

export function SectionCard({
  actions,
  children,
  className,
  contentClassName,
  description,
  headerClassName,
  title,
  ...props
}: SectionCardProps) {
  return (
    <Card className={cn("border-slate-200 bg-white shadow-md shadow-slate-200/60 dark:border-slate-800 dark:bg-slate-950 dark:shadow-black/30", className)} {...props}>
      <CardHeader className={cn("pb-3", headerClassName)}>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <CardTitle>{title}</CardTitle>
            {description ? <CardDescription>{description}</CardDescription> : null}
          </div>
          {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
        </div>
      </CardHeader>
      <CardContent className={contentClassName}>{children}</CardContent>
    </Card>
  );
}

export interface EntityDetailPanelProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  badge?: ReactNode;
  contentClassName?: string;
  description?: ReactNode;
  footer?: ReactNode;
  title: ReactNode;
}

export function EntityDetailPanel({ badge, children, className, contentClassName, description, footer, title, ...props }: EntityDetailPanelProps) {
  return (
    <Card className={cn("overflow-hidden border-slate-200 bg-white shadow-md shadow-slate-200/60 dark:border-slate-800 dark:bg-slate-950 dark:shadow-black/30 xl:sticky xl:top-28", className)} {...props}>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="truncate">{title}</CardTitle>
            {description ? <CardDescription>{description}</CardDescription> : null}
          </div>
          {badge ? <div className="shrink-0">{badge}</div> : null}
        </div>
      </CardHeader>
      <CardContent className={cn("space-y-4", contentClassName)}>{children}</CardContent>
      {footer ? <div className="border-t border-slate-100 px-5 py-4 dark:border-slate-800">{footer}</div> : null}
    </Card>
  );
}

export interface MetricPillProps extends HTMLAttributes<HTMLDivElement> {
  helper?: ReactNode;
  icon?: LucideIcon;
  label: ReactNode;
  tone?: ConsoleTone;
  value: ReactNode;
}

export function MetricPill({ className, helper, icon: Icon, label, tone = "slate", value, ...props }: MetricPillProps) {
  const styles = toneStyles[tone];

  return (
    <div
      className={cn(
        "rounded-2xl border p-4 shadow-sm transition-colors",
        styles.surface,
        className,
      )}
      {...props}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className={cn("text-xs font-semibold uppercase tracking-[0.18em]", styles.text)}>{label}</div>
          <div className="mt-2 text-2xl font-semibold tracking-tight text-slate-950 dark:text-slate-50 sm:text-3xl">
            {value}
          </div>
        </div>
        {Icon ? (
          <div className={cn("flex h-10 w-10 flex-none items-center justify-center rounded-2xl", styles.accent)}>
            <Icon className="h-5 w-5" />
          </div>
        ) : null}
      </div>
      {helper ? <div className="mt-2 truncate text-xs text-slate-500 dark:text-slate-400">{helper}</div> : null}
    </div>
  );
}

export function getConsoleToneForStatus(status: string): ConsoleTone {
  if (status === "ok" || status === "ready" || status === "succeeded" || status === "enabled") {
    return "emerald";
  }

  if (status === "failed" || status === "degraded") {
    return "red";
  }

  if (status === "stale" || status === "updating" || status === "running" || status === "queued" || status === "unknown") {
    return "amber";
  }

  return "slate";
}
