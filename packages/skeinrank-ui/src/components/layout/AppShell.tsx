import { Database, GitBranch, LogOut, Moon, Monitor, Search, ShieldCheck, Sun, Users } from "lucide-react";
import type { ReactNode } from "react";

import { useTheme } from "../../theme";
import type { AuthUser } from "../../types";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";

export type AppSection = "terms" | "suggestions" | "guardrails" | "users";

type AppShellProps = {
  activeSection: AppSection;
  canManageUsers?: boolean;
  children: ReactNode;
  currentUser: AuthUser;
  onLogout: () => void;
  onNavigate: (section: AppSection) => void;
};

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

export function AppShell({ activeSection, canManageUsers = false, children, currentUser, onLogout, onNavigate }: AppShellProps) {
  const { theme, toggleTheme } = useTheme();
  const ThemeIcon = themeIcon[theme];

  const navigation = [
    { label: "Terms", icon: Database, section: "terms" as const, available: true },
    { label: "Suggestions", icon: Search, section: "suggestions" as const, available: true },
    { label: "Guardrails", icon: ShieldCheck, section: "guardrails" as const, available: true },
    { label: "Users", icon: Users, section: "users" as const, available: canManageUsers },
  ];

  return (
    <div className="min-h-screen bg-slate-50 text-slate-950 transition-colors dark:bg-slate-950 dark:text-slate-50">
      <aside className="fixed inset-y-0 left-0 hidden w-72 border-r border-slate-200 bg-white px-5 py-6 transition-colors dark:border-slate-800 dark:bg-slate-950 lg:block">
        <div>
          <div className="text-lg font-semibold tracking-tight">SkeinRank</div>
          <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">Governance Console</div>
        </div>

        <nav className="mt-8 space-y-1">
          {navigation
            .filter((item) => item.available)
            .map((item) => (
              <button
                key={item.label}
                className={`flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm font-medium transition-colors ${
                  activeSection === item.section
                    ? "bg-slate-950 text-white dark:bg-slate-100 dark:text-slate-950"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-50"
                }`}
                onClick={() => onNavigate(item.section)}
                type="button"
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </button>
            ))}
          <DisabledNavItem icon={GitBranch} label="Snapshots" />
        </nav>
      </aside>

      <main className="lg:pl-72">
        <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/90 px-6 py-4 backdrop-blur transition-colors dark:border-slate-800 dark:bg-slate-950/90">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="text-xl font-semibold tracking-tight">
                {activeSection === "users" ? "Users and roles" : activeSection === "suggestions" ? "Suggestions and approvals" : activeSection === "guardrails" ? "Guardrails" : "Terminology control plane"}
              </h1>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                {activeSection === "users"
                  ? "Manage local users, roles, and access to governance workflows."
                  : activeSection === "suggestions"
                    ? "Propose aliases, review pending changes, and approve terminology updates."
                    : activeSection === "guardrails"
                      ? "Manage stop lists that block noisy or unsafe terminology changes."
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
        </header>
        <div className="p-6">{children}</div>
      </main>
    </div>
  );
}

function DisabledNavItem({ icon: Icon, label }: { icon: typeof Search; label: string }) {
  return (
    <button
      className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-50"
      type="button"
    >
      <Icon className="h-4 w-4" />
      {label}
      <Badge className="ml-auto bg-slate-50 text-slate-400 dark:bg-slate-900 dark:text-slate-500">Soon</Badge>
    </button>
  );
}
