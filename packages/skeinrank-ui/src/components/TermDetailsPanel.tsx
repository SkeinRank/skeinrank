import { PlusCircle } from "lucide-react";

import type { AliasCreateRequest, CanonicalTerm } from "../types";
import { AddAliasForm } from "./AddAliasForm";
import { Badge } from "./ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";

type TermDetailsPanelProps = {
  errorMessage?: string | null;
  isAddingAlias?: boolean;
  onAddAlias: (payload: AliasCreateRequest) => Promise<void> | void;
  term: CanonicalTerm | null;
};

export function TermDetailsPanel({ errorMessage, isAddingAlias = false, onAddAlias, term }: TermDetailsPanelProps) {
  if (!term) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Term details</CardTitle>
          <CardDescription>Select a canonical term to inspect aliases and add new mappings.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="rounded-xl border border-dashed border-slate-200 p-5 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
            No term selected yet.
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>{term.canonical_value}</CardTitle>
            <CardDescription>Canonical term details and alias management.</CardDescription>
          </div>
          <Badge>{term.slot}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-3 text-sm">
          <div className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-950">
            <span className="text-slate-500 dark:text-slate-400">Status</span>
            <span className="font-medium capitalize text-slate-800 dark:text-slate-100">{term.status}</span>
          </div>
          <div className="rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-950">
            <div className="text-slate-500 dark:text-slate-400">Description</div>
            <div className="mt-1 text-slate-800 dark:text-slate-100">{term.description || "No description."}</div>
          </div>
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-slate-950 dark:text-slate-50">Aliases</h3>
            <Badge>{term.aliases.length}</Badge>
          </div>
          {term.aliases.length > 0 ? (
            <div className="space-y-2">
              {term.aliases.map((alias) => (
                <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-800" key={alias.id}>
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-medium text-slate-950 dark:text-slate-50">{alias.alias_value}</span>
                    <Badge className="bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-200">{alias.confidence.toFixed(2)}</Badge>
                  </div>
                  <div className="mt-1 text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500">{alias.status}</div>
                  {alias.notes ? <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{alias.notes}</p> : null}
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
              No aliases yet. Add the first known spelling, abbreviation, or team jargon.
            </div>
          )}
        </div>

        <div className="space-y-3 border-t border-slate-100 pt-4 dark:border-slate-800">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-950 dark:text-slate-50">
            <PlusCircle className="h-4 w-4" />
            Add alias
          </div>
          <AddAliasForm errorMessage={errorMessage} isSubmitting={isAddingAlias} onSubmit={onAddAlias} />
        </div>
      </CardContent>
    </Card>
  );
}
