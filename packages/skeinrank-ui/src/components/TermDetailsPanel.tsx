import { type FormEvent, useEffect, useState } from "react";
import { PlusCircle } from "lucide-react";

import type { AliasCreateRequest, AliasUpdateRequest, CanonicalTerm, TermAlias, TermUpdateRequest } from "../types";
import { AddAliasForm } from "./AddAliasForm";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Input } from "./ui/input";

const TERM_STATUSES = ["active", "deprecated", "disabled"];
const ALIAS_STATUSES = ["active", "deprecated", "disabled", "ambiguous", "pending", "rejected"];

type TermDetailsPanelProps = {
  aliasErrorMessage?: string | null;
  errorMessage?: string | null;
  isAddingAlias?: boolean;
  isDeletingAlias?: boolean;
  isDeletingTerm?: boolean;
  isUpdatingAlias?: boolean;
  isUpdatingTerm?: boolean;
  onAddAlias: (payload: AliasCreateRequest) => Promise<void> | void;
  onDeleteAlias: (alias: TermAlias) => Promise<void> | void;
  onDeleteTerm: (term: CanonicalTerm) => Promise<void> | void;
  onUpdateAlias: (alias: TermAlias, payload: AliasUpdateRequest) => Promise<void> | void;
  onUpdateTerm: (term: CanonicalTerm, payload: TermUpdateRequest) => Promise<void> | void;
  term: CanonicalTerm | null;
  termErrorMessage?: string | null;
};

export function TermDetailsPanel({
  aliasErrorMessage,
  errorMessage,
  isAddingAlias = false,
  isDeletingAlias = false,
  isDeletingTerm = false,
  isUpdatingAlias = false,
  isUpdatingTerm = false,
  onAddAlias,
  onDeleteAlias,
  onDeleteTerm,
  onUpdateAlias,
  onUpdateTerm,
  term,
  termErrorMessage,
}: TermDetailsPanelProps) {
  const [canonicalValue, setCanonicalValue] = useState("");
  const [slot, setSlot] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState("active");
  const [editingAliasId, setEditingAliasId] = useState<number | null>(null);
  const [aliasValue, setAliasValue] = useState("");
  const [aliasNotes, setAliasNotes] = useState("");
  const [aliasStatus, setAliasStatus] = useState("active");

  useEffect(() => {
    setCanonicalValue(term?.canonical_value ?? "");
    setSlot(term?.slot ?? "");
    setDescription(term?.description ?? "");
    setStatus(term?.status ?? "active");
    setEditingAliasId(null);
  }, [term?.canonical_value, term?.description, term?.id, term?.slot, term?.status]);

  if (!term) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Term details</CardTitle>
          <CardDescription>Select a canonical term to manage aliases. Suggested aliases will appear in the approval workflow.</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="rounded-xl border border-dashed border-slate-200 p-5 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
            No term selected yet. Select a canonical term to manage aliases, or create the first term manually.
          </div>
        </CardContent>
      </Card>
    );
  }

  const currentTerm = term;
  const canUpdateTerm = canonicalValue.trim().length > 0 && slot.trim().length > 0 && !isUpdatingTerm && !isDeletingTerm;
  const canUpdateAlias = aliasValue.trim().length > 0 && !isUpdatingAlias && !isDeletingAlias;

  async function handleUpdateTerm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canUpdateTerm) {
      return;
    }

    try {
      await onUpdateTerm(currentTerm, {
        canonical_value: canonicalValue.trim(),
        slot: slot.trim(),
        description: description.trim() || null,
        status,
      });
    } catch {
      // Parent mutation owns user-facing error rendering.
    }
  }

  async function handleDeleteTerm() {
    const confirmed = window.confirm(`Delete canonical term "${currentTerm.canonical_value}" and all of its aliases?`);
    if (!confirmed) {
      return;
    }

    try {
      await onDeleteTerm(currentTerm);
    } catch {
      // Parent mutation owns user-facing error rendering.
    }
  }

  function startAliasEdit(alias: TermAlias) {
    setEditingAliasId(alias.id);
    setAliasValue(alias.alias_value);
    setAliasNotes(alias.notes ?? "");
    setAliasStatus(alias.status);
  }

  async function handleUpdateAlias(event: FormEvent<HTMLFormElement>, alias: TermAlias) {
    event.preventDefault();
    if (!canUpdateAlias) {
      return;
    }

    try {
      await onUpdateAlias(alias, {
        alias_value: aliasValue.trim(),
        confidence: 1,
        notes: aliasNotes.trim() || null,
        status: aliasStatus,
      });
      setEditingAliasId(null);
    } catch {
      // Parent mutation owns user-facing error rendering.
    }
  }

  async function handleDeleteAlias(alias: TermAlias) {
    const confirmed = window.confirm(`Delete alias "${alias.alias_value}"?`);
    if (!confirmed) {
      return;
    }

    try {
      await onDeleteAlias(alias);
    } catch {
      // Parent mutation owns user-facing error rendering.
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>{term.canonical_value}</CardTitle>
            <CardDescription>Approved canonical term and manual alias management.</CardDescription>
          </div>
          <Badge>{term.slot}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <form className="space-y-3 rounded-xl border border-slate-100 p-4 dark:border-slate-800" onSubmit={handleUpdateTerm}>
          <div>
            <h3 className="text-sm font-semibold text-slate-950 dark:text-slate-50">Edit canonical term</h3>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Update the canonical value, slot, description, or lifecycle status.
            </p>
          </div>
          <label className="space-y-1.5">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit canonical value</span>
            <Input
              disabled={isUpdatingTerm || isDeletingTerm}
              onChange={(event) => setCanonicalValue(event.target.value)}
              value={canonicalValue}
            />
          </label>
          <label className="space-y-1.5">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit slot</span>
            <Input disabled={isUpdatingTerm || isDeletingTerm} onChange={(event) => setSlot(event.target.value)} value={slot} />
          </label>
          <label className="space-y-1.5">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit description</span>
            <Input
              disabled={isUpdatingTerm || isDeletingTerm}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Optional term description"
              value={description}
            />
          </label>
          <label className="space-y-1.5">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Term status</span>
            <select
              className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:focus:border-slate-500 dark:focus:ring-slate-800"
              disabled={isUpdatingTerm || isDeletingTerm}
              onChange={(event) => setStatus(event.target.value)}
              value={status}
            >
              {TERM_STATUSES.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          {termErrorMessage ? <InlineError message={termErrorMessage} /> : null}
          <div className="flex flex-wrap gap-2">
            <Button disabled={!canUpdateTerm} type="submit">
              {isUpdatingTerm ? "Saving..." : "Save term"}
            </Button>
            <Button disabled={isUpdatingTerm || isDeletingTerm} onClick={handleDeleteTerm} type="button" variant="secondary">
              {isDeletingTerm ? "Deleting..." : "Delete term"}
            </Button>
          </div>
        </form>

        <div className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-slate-950 dark:text-slate-50">Aliases</h3>
            <Badge>{term.aliases.length}</Badge>
          </div>
          {aliasErrorMessage ? <InlineError message={aliasErrorMessage} /> : null}
          {term.aliases.length > 0 ? (
            <div className="space-y-2">
              {term.aliases.map((alias) => (
                <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-800" key={alias.id}>
                  {editingAliasId === alias.id ? (
                    <form className="space-y-3" onSubmit={(event) => handleUpdateAlias(event, alias)}>
                      <label className="space-y-1.5">
                        <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit alias</span>
                        <Input
                          disabled={isUpdatingAlias || isDeletingAlias}
                          onChange={(event) => setAliasValue(event.target.value)}
                          value={aliasValue}
                        />
                      </label>
                      <label className="space-y-1.5">
                        <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit alias notes</span>
                        <Input
                          disabled={isUpdatingAlias || isDeletingAlias}
                          onChange={(event) => setAliasNotes(event.target.value)}
                          placeholder="Optional alias notes"
                          value={aliasNotes}
                        />
                      </label>
                      <label className="space-y-1.5">
                        <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Alias status</span>
                        <select
                          className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:focus:border-slate-500 dark:focus:ring-slate-800"
                          disabled={isUpdatingAlias || isDeletingAlias}
                          onChange={(event) => setAliasStatus(event.target.value)}
                          value={aliasStatus}
                        >
                          {ALIAS_STATUSES.map((item) => (
                            <option key={item} value={item}>
                              {item}
                            </option>
                          ))}
                        </select>
                      </label>
                      <div className="flex flex-wrap gap-2">
                        <Button disabled={!canUpdateAlias} type="submit">
                          {isUpdatingAlias ? "Saving..." : "Save alias"}
                        </Button>
                        <Button disabled={isUpdatingAlias || isDeletingAlias} onClick={() => setEditingAliasId(null)} type="button" variant="ghost">
                          Cancel
                        </Button>
                      </div>
                    </form>
                  ) : (
                    <>
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-medium text-slate-950 dark:text-slate-50">{alias.alias_value}</span>
                        <Badge className="bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200">{alias.status}</Badge>
                      </div>
                      {alias.notes ? <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{alias.notes}</p> : null}
                      <div className="mt-3 flex flex-wrap gap-2">
                        <Button disabled={isUpdatingAlias || isDeletingAlias} onClick={() => startAliasEdit(alias)} type="button" variant="secondary">
                          Edit alias
                        </Button>
                        <Button disabled={isUpdatingAlias || isDeletingAlias} onClick={() => handleDeleteAlias(alias)} type="button" variant="ghost">
                          {isDeletingAlias ? "Deleting..." : "Delete alias"}
                        </Button>
                      </div>
                    </>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
              No aliases yet. Add the first known spelling, abbreviation, or team jargon. Suggested aliases will be reviewed in the approval workflow.
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

function InlineError({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200">
      {message}
    </div>
  );
}
