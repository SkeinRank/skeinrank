import { ChevronLeft, ChevronRight, Database, GitBranch, Home, Inbox, LogOut, Moon, Monitor, Plug, Search, Settings, ShieldCheck, Sparkles, Sun, Users, Wrench } from "lucide-react";
import type { FocusEvent, ReactNode } from "react";
import { useState } from "react";

import { cn } from "../../lib/utils";
import { useTheme } from "../../theme";
import type { AuthUser } from "../../types";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { ControlPlaneStatusBanner } from "./ControlPlaneStatusBanner";

export type AppSection = "dashboard" | "terms" | "proposal-inbox" | "suggestions" | "guardrails" | "integrations" | "search-playground" | "snapshots" | "api-access" | "users";

type AppShellProps = {
  activeSection: AppSection;
  canManageApiTokens?: boolean;
  canManageUsers?: boolean;
  children: ReactNode;
  currentUser: AuthUser;
  onLogout: () => void;
  onNavigate: (section: AppSection) => void;
};

type SidebarMode = "expanded" | "collapsed";

type NavigationItem = {
  label: string;
  icon: typeof Search;
  section: AppSection;
  available: boolean;
};

const SIDEBAR_STORAGE_KEY = "skeinrank-ui-sidebar-mode";

const themeLabel = {
  light: "Light",
  dark: "Dark",
  system: "System",
};

const themeIcon = {
  light: Sun,
  dark: Moon,
  system: Monitor,
};

function getInitialSidebarMode(): SidebarMode {
  if (typeof window === "undefined") {
    return "expanded";
  }

  const storedMode = window.localStorage.getItem(SIDEBAR_STORAGE_KEY);
  if (storedMode === "collapsed" || storedMode === "expanded") {
    return storedMode;
  }

  return "expanded";
}

export function AppShell({ activeSection, canManageApiTokens = true, canManageUsers = false, children, currentUser, onLogout, onNavigate }: AppShellProps) {
  const { theme, toggleTheme } = useTheme();
  const ThemeIcon = themeIcon[theme];
  const [sidebarMode, setSidebarMode] = useState<SidebarMode>(getInitialSidebarMode);
  const [isSidebarPreviewed, setIsSidebarPreviewed] = useState(false);

  const isSidebarCollapsed = sidebarMode === "collapsed";
  const isSidebarOpen = !isSidebarCollapsed || isSidebarPreviewed;

  const primaryNavigation: NavigationItem[] = [
    { label: "Playground", icon: Search, section: "search-playground", available: true },
    { label: "AI Inbox", icon: Inbox, section: "proposal-inbox", available: true },
    { label: "Schema & Snapshots", icon: GitBranch, section: "snapshots", available: true },
  ];

  const settingsNavigation: NavigationItem[] = [
    { label: "API Access", icon: Settings, section: "api-access", available: canManageApiTokens },
    { label: "Users", icon: Users, section: "users", available: canManageUsers },
    { label: "Integrations", icon: Plug, section: "integrations", available: true },
  ];

  const legacyNavigation: NavigationItem[] = [
    { label: "Dashboard", icon: Home, section: "dashboard", available: true },
    { label: "Terms", icon: Database, section: "terms", available: true },
    { label: "Suggestions", icon: Sparkles, section: "suggestions", available: true },
    { label: "Guardrails", icon: ShieldCheck, section: "guardrails", available: true },
  ];

  function setNextSidebarMode(mode: SidebarMode) {
    setSidebarMode(mode);
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, mode);
    setIsSidebarPreviewed(false);
  }

  function handleSidebarBlur(event: FocusEvent<HTMLElement>) {
    const nextTarget = event.relatedTarget;
    if (!(nextTarget instanceof Node) || !event.currentTarget.contains(nextTarget)) {
      setIsSidebarPreviewed(false);
    }
  }

  function renderNavigationGroup(label: string, items: NavigationItem[], options: { compact?: boolean; ariaLabel: string }) {
    const availableItems = items.filter((item) => item.available);
    if (availableItems.length === 0) {
      return null;
    }

    return (
      <nav aria-label={options.ariaLabel} className={cn(options.compact ? "space-y-1" : "space-y-1.5")}>
        {isSidebarOpen ? (
          <div className={cn("px-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400 dark:text-slate-500", options.compact ? "mb-1" : "mb-2")}>{label}</div>
        ) : (
          <div className="mx-auto mb-2 h-px w-8 bg-slate-200 dark:bg-slate-800" aria-hidden="true" />
        )}
        {availableItems.map((item) => (
          <button
            key={item.label}
            aria-current={activeSection === item.section ? "page" : undefined}
            aria-label={item.label}
            className={cn(
              "group relative flex w-full items-center rounded-xl text-left font-medium transition-colors",
              options.compact ? "py-2 text-xs" : "py-2.5 text-sm",
              isSidebarOpen ? "gap-3 px-3" : "justify-center px-0",
              activeSection === item.section
                ? "bg-slate-950 text-white dark:bg-slate-100 dark:text-slate-950"
                : options.compact
                  ? "text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-500 dark:hover:bg-slate-900 dark:hover:text-slate-50"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-50",
            )}
            onClick={() => onNavigate(item.section)}
            title={isSidebarOpen ? undefined : item.label}
            type="button"
          >
            <item.icon className={cn("shrink-0", options.compact ? "h-4 w-4" : "h-5 w-5")} />
            <span className={isSidebarOpen ? "truncate" : "sr-only"}>{item.label}</span>
            {!isSidebarOpen ? (
              <span className="pointer-events-none absolute left-12 z-30 hidden whitespace-nowrap rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs font-medium text-slate-700 shadow-lg group-hover:block dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200">
                {item.label}
              </span>
            ) : null}
          </button>
        ))}
      </nav>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-950 transition-colors dark:bg-slate-950 dark:text-slate-50">
      <aside
        aria-label="Primary navigation"
        className={cn(
          "fixed inset-y-0 left-0 z-20 hidden border-r border-slate-200 bg-white px-4 py-5 shadow-sm transition-[width,box-shadow] duration-200 ease-out dark:border-slate-800 dark:bg-slate-950 lg:block",
          isSidebarOpen ? "w-72" : "w-20",
          isSidebarCollapsed && isSidebarPreviewed ? "shadow-xl" : "",
        )}
        onBlur={handleSidebarBlur}
        onFocus={() => setIsSidebarPreviewed(true)}
        onMouseEnter={() => setIsSidebarPreviewed(true)}
        onMouseLeave={() => setIsSidebarPreviewed(false)}
      >
        <div className={cn("flex items-start", isSidebarOpen ? "justify-between gap-3" : "justify-center")}>
          <div className={cn("min-w-0", isSidebarOpen ? "flex items-center gap-3" : "flex justify-center")}>
            <img
              className="h-12 w-12 shrink-0 rounded-2xl object-cover shadow-sm"
              src="/skeinrank-logo.png"
              alt="SkeinRank logo"
            />
            {isSidebarOpen ? (
              <div className="min-w-0">
                <div className="truncate text-lg font-semibold tracking-tight">SkeinRank</div>
                <div className="mt-1 truncate text-sm text-slate-500 dark:text-slate-400">Control Plane</div>
              </div>
            ) : null}
          </div>
          {isSidebarOpen ? (
            <button
              aria-label={isSidebarCollapsed ? "Pin sidebar open" : "Collapse sidebar"}
              className="inline-flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-600 transition-colors hover:bg-slate-50 hover:text-slate-950 focus:outline-none focus:ring-2 focus:ring-slate-400 focus:ring-offset-2 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-50 dark:focus:ring-slate-500 dark:focus:ring-offset-slate-950"
              onClick={() => setNextSidebarMode(isSidebarCollapsed ? "expanded" : "collapsed")}
              type="button"
            >
              {isSidebarCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
            </button>
          ) : null}
        </div>

        <div className="mt-12 flex h-[calc(100%-7rem)] flex-col justify-between gap-6">
          <div className="space-y-6">
            {renderNavigationGroup("Control Plane", primaryNavigation, { ariaLabel: "Primary product navigation" })}
          </div>

          <div className="space-y-5 border-t border-slate-200 pt-5 dark:border-slate-800">
            {renderNavigationGroup("Settings", settingsNavigation, { ariaLabel: "Settings navigation", compact: true })}
            <div>
              {isSidebarOpen ? (
                <div className="mb-2 flex items-center gap-2 px-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400 dark:text-slate-500">
                  <Wrench className="h-3.5 w-3.5" />
                  Developer Cockpit
                </div>
              ) : null}
              {renderNavigationGroup("Developer", legacyNavigation, { ariaLabel: "Developer Cockpit navigation", compact: true })}
            </div>
          </div>
        </div>
      </aside>

      <main className={cn("transition-[padding] duration-200 ease-out", isSidebarCollapsed ? "lg:pl-20" : "lg:pl-72")}>
        <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/90 px-6 py-4 backdrop-blur transition-colors dark:border-slate-800 dark:bg-slate-950/90">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="text-xl font-semibold tracking-tight">
                {activeSection === "dashboard"
                  ? "Dashboard"
                  : activeSection === "users"
                  ? "Users and roles"
                  : activeSection === "snapshots"
                    ? "Schema & Snapshots"
                  : activeSection === "proposal-inbox"
                    ? "AI Proposals Inbox"
                  : activeSection === "search-playground"
                    ? "Search Playground"
                  : activeSection === "suggestions"
                    ? "Suggestions and approvals"
                    : activeSection === "guardrails"
                      ? "Guardrails"
                      : activeSection === "integrations"
                        ? "Integrations"
                        : activeSection === "api-access"
                          ? "Settings"
                          : "Terminology control plane"}
              </h1>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                {activeSection === "dashboard"
                  ? "Legacy readiness, setup checklist, and runtime status for local development."
                  : activeSection === "users"
                  ? "Manage local users, roles, and access to governance workflows."
                  : activeSection === "snapshots"
                    ? "Inspect terminology schema, aliases, bindings, and immutable runtime snapshots."
                  : activeSection === "proposal-inbox"
                    ? "Review agent-submitted terminology changes with risk, evidence, and human approval."
                  : activeSection === "search-playground"
                    ? "Debug query canonicalization and compare snapshot behavior before rollout."
                  : activeSection === "suggestions"
                    ? "Legacy manual suggestion workspace retained for development and compatibility."
                    : activeSection === "guardrails"
                      ? "Manage stop lists that block noisy or unsafe terminology changes."
                      : activeSection === "integrations"
                        ? "Configure Elasticsearch enrichment bindings for profiles and indices."
                        : activeSection === "api-access"
                          ? "Create personal API tokens and manage service account access."
                          : "Manage canonical terms, aliases, slots, and runtime snapshots."}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-900">
                <span className="font-medium">{currentUser.display_name || currentUser.username}</span>
                <span className="mx-1 text-slate-400">·</span>
                <span className="text-slate-500 dark:text-slate-400">{currentUser.role}</span>
              </div>
              <Button aria-label={`Switch theme. Current theme: ${themeLabel[theme]}`} onClick={toggleTheme} variant="secondary">
                <ThemeIcon className="mr-2 h-4 w-4" />
                {themeLabel[theme]}
              </Button>
              <Button onClick={onLogout} variant="ghost">
                <LogOut className="mr-2 h-4 w-4" />
                Logout
              </Button>
              <Badge>MVP</Badge>
            </div>
          </div>
          <ControlPlaneStatusBanner />
        </header>
        <div className="p-6">{children}</div>
      </main>
    </div>
  );
}
