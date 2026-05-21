import { type FormEvent, useEffect, useState } from "react";
import { PlusCircle, Search } from "lucide-react";

import type {
  AliasCreateRequest,
  AliasUpdateRequest,
  CanonicalTerm,
  ElasticsearchBinding,
  ElasticsearchEvidenceResponse,
  TermAlias,
  TermUpdateRequest,
} from "../types";
import { AddAliasForm } from "./AddAliasForm";
import { EvidenceDocumentsList } from "./EvidenceDocumentsList";
import { EntityDetailPanel } from "./layout/ConsolePrimitives";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Input } from "./ui/input";

const TERM_STATUSES = ["active", "deprecated", "disabled"];
const ALIAS_STATUSES = ["active", "deprecated", "disabled"];

type TermDetailsPanelProps = {
  aliasErrorMessage?: string | null;
  bindings?: ElasticsearchBinding[];
  bindingsErrorMessage?: string | null;
  bindingsLoading?: boolean;
  canManageAliases?: boolean;
  canManageTerm?: boolean;
  errorMessage?: string | null;
  evidence?: ElasticsearchEvidenceResponse | null;
  evidenceErrorMessage?: string | null;
  isAddingAlias?: boolean;
  isDeletingAlias?: boolean;
  isDeletingTerm?: boolean;
  isCheckingEvidence?: boolean;
  isUpdatingAlias?: boolean;
  isUpdatingTerm?: boolean;
  onAddAlias: (payload: AliasCreateRequest) => Promise<void> | void;
  onCheckEvidence?: (
    term: CanonicalTerm,
    bindingId: number,
    query: string,
  ) => Promise<void> | void;
  onDeleteAlias: (alias: TermAlias) => Promise<void> | void;
  onDeleteTerm: (term: CanonicalTerm) => Promise<void> | void;
  onUpdateAlias: (
    alias: TermAlias,
    payload: AliasUpdateRequest,
  ) => Promise<void> | void;
  onUpdateTerm: (
    term: CanonicalTerm,
    payload: TermUpdateRequest,
  ) => Promise<void> | void;
  term: CanonicalTerm | null;
  termErrorMessage?: string | null;
};

export function TermDetailsPanel({
  aliasErrorMessage,
  bindings = [],
  bindingsErrorMessage,
  bindingsLoading = false,
  canManageAliases = true,
  canManageTerm = true,
  errorMessage,
  evidence,
  evidenceErrorMessage,
  isAddingAlias = false,
  isDeletingAlias = false,
  isDeletingTerm = false,
  isCheckingEvidence = false,
  isUpdatingAlias = false,
  isUpdatingTerm = false,
  onAddAlias,
  onCheckEvidence,
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
  const [selectedBindingId, setSelectedBindingId] = useState<number | null>(
    null,
  );
  const [evidenceQuery, setEvidenceQuery] = useState("");

  useEffect(() => {
    setCanonicalValue(term?.canonical_value ?? "");
    setSlot(term?.slot ?? "");
    setDescription(term?.description ?? "");
    setStatus(term?.status ?? "active");
    setEditingAliasId(null);
    setEvidenceQuery(term?.canonical_value ?? "");
  }, [
    term?.canonical_value,
    term?.description,
    term?.id,
    term?.slot,
    term?.status,
  ]);

  useEffect(() => {
    if (bindings.length === 0) {
      setSelectedBindingId(null);
      return;
    }
    if (
      !selectedBindingId ||
      !bindings.some((binding) => binding.id === selectedBindingId)
    ) {
      setSelectedBindingId(bindings[0].id);
    }
  }, [bindings, selectedBindingId]);

  if (!term) {
    return (
      <EntityDetailPanel
        badge={<Badge>empty</Badge>}
        description="Select a row to manage aliases, lifecycle, and evidence."
        title="Term details"
      >
        <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/70 p-5 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-900/50 dark:text-slate-400">
          No term selected yet. Select a canonical term to manage aliases, or
          create the first term manually.
        </div>
      </EntityDetailPanel>
    );
  }

  const currentTerm = term;
  const canUpdateTerm =
    canManageTerm &&
    canonicalValue.trim().length > 0 &&
    slot.trim().length > 0 &&
    !isUpdatingTerm &&
    !isDeletingTerm;
  const canUpdateAlias =
    canManageAliases &&
    aliasValue.trim().length > 0 &&
    !isUpdatingAlias &&
    !isDeletingAlias;
  const canCheckEvidence = Boolean(
    onCheckEvidence &&
    selectedBindingId &&
    evidenceQuery.trim().length > 0 &&
    !isCheckingEvidence,
  );

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
    if (!canManageTerm) {
      return;
    }
    const confirmed = window.confirm(
      `Delete canonical term "${currentTerm.canonical_value}" and all of its aliases?`,
    );
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
    setAliasStatus(
      ALIAS_STATUSES.includes(alias.status) ? alias.status : "active",
    );
  }

  async function handleUpdateAlias(
    event: FormEvent<HTMLFormElement>,
    alias: TermAlias,
  ) {
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
    if (!canManageAliases) {
      return;
    }
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

  async function handleCheckEvidence() {
    if (!onCheckEvidence || !selectedBindingId || !canCheckEvidence) {
      return;
    }

    try {
      await onCheckEvidence(
        currentTerm,
        selectedBindingId,
        evidenceQuery.trim(),
      );
    } catch {
      // Parent mutation owns user-facing error rendering.
    }
  }

  function checkAliasEvidence(alias: TermAlias) {
    setEvidenceQuery(alias.alias_value);
    if (onCheckEvidence && selectedBindingId) {
      void onCheckEvidence(currentTerm, selectedBindingId, alias.alias_value);
    }
  }

  return (
    <EntityDetailPanel
      badge={<Badge>{term.slot}</Badge>}
      description="Canonical term lifecycle, aliases, and evidence checks."
      title={term.canonical_value}
    >
      <div className="grid grid-cols-3 gap-2 text-xs">
        <SummaryChip label="Status" value={term.status} />
        <SummaryChip label="Aliases" value={String(term.aliases.length)} />
        <SummaryChip label="Bindings" value={String(bindings.length)} />
      </div>

      {!canManageTerm || !canManageAliases ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
          Your role has read-only access to this terminology profile. Use the
          Suggestions tab to propose changes for review.
        </div>
      ) : null}

      <form
        className="space-y-3 rounded-2xl border border-slate-100 bg-slate-50/60 p-4 dark:border-slate-800 dark:bg-slate-900/50"
        onSubmit={handleUpdateTerm}
      >
        <div>
          <h3 className="text-sm font-semibold text-slate-950 dark:text-slate-50">
            Edit canonical term
          </h3>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Update the canonical value, slot, description, or lifecycle status.
          </p>
        </div>
        <label className="space-y-1.5">
          <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
            Edit canonical value
          </span>
          <Input
            disabled={!canManageTerm || isUpdatingTerm || isDeletingTerm}
            onChange={(event) => setCanonicalValue(event.target.value)}
            value={canonicalValue}
          />
        </label>
        <label className="space-y-1.5">
          <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
            Edit slot
          </span>
          <Input
            disabled={!canManageTerm || isUpdatingTerm || isDeletingTerm}
            onChange={(event) => setSlot(event.target.value)}
            value={slot}
          />
        </label>
        <label className="space-y-1.5">
          <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
            Edit description
          </span>
          <Input
            disabled={!canManageTerm || isUpdatingTerm || isDeletingTerm}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Optional description"
            value={description}
          />
        </label>
        <label className="space-y-1.5">
          <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
            Term status
          </span>
          <select
            className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 focus:border-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-200 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-50 dark:focus:border-slate-500 dark:focus:ring-slate-800 dark:disabled:bg-slate-900"
            disabled={!canManageTerm || isUpdatingTerm || isDeletingTerm}
            onChange={(event) => setStatus(event.target.value)}
            value={status}
          >
            {TERM_STATUSES.map((termStatus) => (
              <option key={termStatus} value={termStatus}>
                {termStatus}
              </option>
            ))}
          </select>
        </label>
        {termErrorMessage ? <InlineError message={termErrorMessage} /> : null}
        <div className="flex flex-wrap gap-2">
          <Button disabled={!canUpdateTerm} type="submit">
            {isUpdatingTerm ? "Saving..." : "Save term"}
          </Button>
          <Button
            disabled={!canManageTerm || isDeletingTerm}
            onClick={handleDeleteTerm}
            type="button"
            variant="secondary"
          >
            {isDeletingTerm ? "Deleting..." : "Delete term"}
          </Button>
        </div>
      </form>

      <section className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-950 dark:text-slate-50">
              Aliases
            </h3>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Manual aliases attached to this canonical value.
            </p>
          </div>
          <Badge>{term.aliases.length}</Badge>
        </div>

        <div className="space-y-2">
          {term.aliases.length > 0 ? (
            term.aliases.map((alias) => (
              <div
                className="rounded-2xl border border-slate-100 bg-white p-3 shadow-sm dark:border-slate-800 dark:bg-slate-950"
                key={alias.id}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="truncate text-sm font-semibold text-slate-950 dark:text-slate-50">
                        {alias.alias_value}
                      </span>
                      <Badge>{alias.status}</Badge>
                    </div>
                    {alias.notes ? (
                      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                        {alias.notes}
                      </p>
                    ) : null}
                  </div>
                </div>

                {editingAliasId === alias.id ? (
                  <form
                    className="mt-3 space-y-3 rounded-xl border border-slate-100 bg-slate-50/70 p-3 dark:border-slate-800 dark:bg-slate-900/60"
                    onSubmit={(event) => handleUpdateAlias(event, alias)}
                  >
                    <label className="space-y-1.5">
                      <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
                        Edit alias
                      </span>
                      <Input
                        disabled={isUpdatingAlias || isDeletingAlias}
                        onChange={(event) => setAliasValue(event.target.value)}
                        value={aliasValue}
                      />
                    </label>
                    <label className="space-y-1.5">
                      <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
                        Edit alias notes
                      </span>
                      <Input
                        disabled={isUpdatingAlias || isDeletingAlias}
                        onChange={(event) => setAliasNotes(event.target.value)}
                        placeholder="Optional notes"
                        value={aliasNotes}
                      />
                    </label>
                    <label className="space-y-1.5">
                      <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
                        Alias status
                      </span>
                      <select
                        className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 focus:border-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-200 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-50 dark:focus:border-slate-500 dark:focus:ring-slate-800 dark:disabled:bg-slate-900"
                        disabled={isUpdatingAlias || isDeletingAlias}
                        onChange={(event) => setAliasStatus(event.target.value)}
                        value={aliasStatus}
                      >
                        {ALIAS_STATUSES.map((statusValue) => (
                          <option key={statusValue} value={statusValue}>
                            {statusValue}
                          </option>
                        ))}
                      </select>
                    </label>
                    <div className="flex flex-wrap gap-2">
                      <Button disabled={!canUpdateAlias} type="submit">
                        {isUpdatingAlias ? "Saving..." : "Save alias"}
                      </Button>
                      <Button
                        onClick={() => setEditingAliasId(null)}
                        type="button"
                        variant="ghost"
                      >
                        Cancel
                      </Button>
                    </div>
                  </form>
                ) : (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {canManageAliases ? (
                      <>
                        <Button
                          disabled={isUpdatingAlias || isDeletingAlias}
                          onClick={() => startAliasEdit(alias)}
                          type="button"
                          variant="secondary"
                        >
                          Edit alias
                        </Button>
                        <Button
                          disabled={isDeletingAlias}
                          onClick={() => handleDeleteAlias(alias)}
                          type="button"
                          variant="ghost"
                        >
                          Delete alias
                        </Button>
                      </>
                    ) : null}
                    <Button
                      disabled={
                        !onCheckEvidence ||
                        !selectedBindingId ||
                        isCheckingEvidence
                      }
                      onClick={() => checkAliasEvidence(alias)}
                      type="button"
                      variant="ghost"
                    >
                      Check evidence
                    </Button>
                  </div>
                )}
              </div>
            ))
          ) : (
            <div className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
              No aliases yet. Add one manually or accept a suggestion from the
              review queue.
            </div>
          )}
        </div>
      </section>

      <section className="rounded-2xl border border-slate-100 bg-slate-50/60 p-4 dark:border-slate-800 dark:bg-slate-900/50">
        <div className="mb-3 flex items-center gap-2">
          <PlusCircle className="h-4 w-4 text-slate-500" />
          <h3 className="text-sm font-semibold text-slate-950 dark:text-slate-50">
            Add alias
          </h3>
        </div>
        <AddAliasForm
          disabled={!canManageAliases || isAddingAlias}
          errorMessage={errorMessage}
          isSubmitting={isAddingAlias}
          onSubmit={onAddAlias}
        />
      </section>

      <section className="space-y-3 rounded-2xl border border-slate-100 bg-slate-50/60 p-4 dark:border-slate-800 dark:bg-slate-900/50">
        <div className="flex items-start gap-2">
          <Search className="mt-0.5 h-4 w-4 text-slate-500" />
          <div>
            <h3 className="text-sm font-semibold text-slate-950 dark:text-slate-50">
              Evidence check
            </h3>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Search this profile's Elasticsearch bindings for the canonical
              term or one of its aliases.
            </p>
          </div>
        </div>
        {bindingsErrorMessage ? (
          <InlineError message={bindingsErrorMessage} />
        ) : null}
        {bindingsLoading ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Loading bindings...
          </p>
        ) : bindings.length > 0 ? (
          <>
            <label className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
                Binding
              </span>
              <select
                className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 focus:border-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-200 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-50 dark:focus:border-slate-500 dark:focus:ring-slate-800"
                onChange={(event) =>
                  setSelectedBindingId(Number(event.target.value))
                }
                value={selectedBindingId ?? ""}
              >
                {bindings.map((binding) => (
                  <option key={binding.id} value={binding.id}>
                    {binding.name} · {binding.index_name}
                  </option>
                ))}
              </select>
            </label>
            <label className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
                Evidence query
              </span>
              <Input
                onChange={(event) => setEvidenceQuery(event.target.value)}
                value={evidenceQuery}
              />
            </label>
            {evidenceErrorMessage ? (
              <InlineError message={evidenceErrorMessage} />
            ) : null}
            <Button
              className="w-full gap-2"
              disabled={!canCheckEvidence}
              onClick={handleCheckEvidence}
              type="button"
              variant="secondary"
            >
              <Search className="h-4 w-4" />
              {isCheckingEvidence ? "Checking..." : "Check evidence"}
            </Button>
            {evidence ? (
              <EvidenceDocumentsList documents={evidence.documents} />
            ) : null}
          </>
        ) : (
          <p className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
            Create an Elasticsearch binding to check evidence for this term.
          </p>
        )}
      </section>

      {aliasErrorMessage ? <InlineError message={aliasErrorMessage} /> : null}
    </EntityDetailPanel>
  );
}

function SummaryChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-100 bg-slate-50/80 px-3 py-2 dark:border-slate-800 dark:bg-slate-900/60">
      <div className="text-[0.65rem] font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">
        {label}
      </div>
      <div className="mt-1 truncate text-sm font-semibold capitalize text-slate-950 dark:text-slate-50">
        {value}
      </div>
    </div>
  );
}

function InlineError({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200">
      {message}
    </div>
  );
}
