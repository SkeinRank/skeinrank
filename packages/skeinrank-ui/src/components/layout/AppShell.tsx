import { Database, GitBranch, Moon, Monitor, Search, ShieldCheck, Sun } from "lucide-react";
import type { ReactNode } from "react";

import { useTheme } from "../../theme";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";

const navigation = [
  { label: "Terms", icon: Database, active: true },
  { label: "Suggestions", icon: Search, active: false },
  { label: "Snapshots", icon: GitBranch, active: false },
  { label: "Governance", icon: ShieldCheck, active: false },
];

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

export function AppShell({ children }: { children: ReactNode }) {
  const { theme, toggleTheme } = useTheme();
  const ThemeIcon = themeIcon[theme];

  return (
    <div className="min-h-screen bg-slate-50 text-slate-950 transition-colors dark:bg-slate-950 dark:text-slate-50">
      <aside className="fixed inset-y-0 left-0 hidden w-72 border-r border-slate-200 bg-white px-5 py-6 transition-colors dark:border-slate-800 dark:bg-slate-950 lg:block">
        <div>
          <div className="text-lg font-semibold tracking-tight">SkeinRank</div>
          <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">Governance Console</div>
        </div>

        <nav className="mt-8 space-y-1">
          {navigation.map((item) => (
            <button
              key={item.label}
              className={`flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm font-medium transition-colors ${
                item.active
                  ? "bg-slate-950 text-white dark:bg-slate-100 dark:text-slate-950"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-950 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-50"
              }`}
              type="button"
            >
              <item.icon className="h-4 w-4" />
              {item.label}
              {!item.active ? (
                <Badge className="ml-auto bg-slate-50 text-slate-400 dark:bg-slate-900 dark:text-slate-500">Soon</Badge>
              ) : null}
            </button>
          ))}
        </nav>
      </aside>

      <main className="lg:pl-72">
        <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/90 px-6 py-4 backdrop-blur transition-colors dark:border-slate-800 dark:bg-slate-950/90">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="text-xl font-semibold tracking-tight">Terminology control plane</h1>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Manage canonical terms, aliases, slots, and runtime snapshots.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button aria-label={`Switch theme. Current theme: ${themeLabel[theme]}`} onClick={toggleTheme} variant="secondary">
                <ThemeIcon className="mr-2 h-4 w-4" />
                {themeLabel[theme]}
              </Button>
              <Badge>UI skeleton</Badge>
            </div>
          </div>
        </header>
        <div className="p-6">{children}</div>
      </main>
    </div>
  );
}
