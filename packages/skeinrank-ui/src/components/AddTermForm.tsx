import { type FormEvent, useState } from "react";

import type { TermCreateRequest } from "../types";
import { SectionCard } from "./layout/ConsolePrimitives";
import { Button } from "./ui/button";
import { Input } from "./ui/input";

type AddTermFormProps = {
  disabled?: boolean;
  errorMessage?: string | null;
  isSubmitting?: boolean;
  readOnlyMessage?: string | null;
  onSubmit: (payload: TermCreateRequest) => Promise<void> | void;
};

export function AddTermForm({
  disabled = false,
  errorMessage,
  isSubmitting = false,
  readOnlyMessage,
  onSubmit,
}: AddTermFormProps) {
  const [canonicalValue, setCanonicalValue] = useState("");
  const [slot, setSlot] = useState("");
  const [description, setDescription] = useState("");

  const canSubmit =
    !disabled &&
    canonicalValue.trim().length > 0 &&
    slot.trim().length > 0 &&
    !isSubmitting;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }

    try {
      await onSubmit({
        canonical_value: canonicalValue.trim(),
        slot: slot.trim(),
        description: description.trim() || null,
        status: "active",
      });

      setCanonicalValue("");
      setSlot("");
      setDescription("");
    } catch {
      // The parent mutation owns user-facing error rendering.
    }
  }

  return (
    <SectionCard
      contentClassName="pt-0"
      description="Create one approved canonical value without leaving the workspace."
      title="Add canonical term"
    >
      <form
        className="grid gap-4 border-t border-slate-100 pt-4 dark:border-slate-800 lg:grid-cols-[minmax(0,1.2fr)_180px]"
        onSubmit={handleSubmit}
      >
        <label className="space-y-1.5">
          <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
            Canonical value
          </span>
          <Input
            disabled={disabled || isSubmitting}
            onChange={(event) => setCanonicalValue(event.target.value)}
            placeholder="kubernetes"
            value={canonicalValue}
          />
        </label>
        <label className="space-y-1.5">
          <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
            Slot
          </span>
          <Input
            disabled={disabled || isSubmitting}
            onChange={(event) => setSlot(event.target.value)}
            placeholder="TOOL"
            value={slot}
          />
        </label>
        <label className="space-y-1.5 lg:col-span-2">
          <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
            Description
          </span>
          <Input
            disabled={disabled || isSubmitting}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Optional note for reviewers and snapshot maintainers"
            value={description}
          />
        </label>
        <div className="flex flex-col gap-3 rounded-xl border border-slate-100 bg-slate-50/60 p-3 dark:border-slate-800 dark:bg-slate-900/60 sm:flex-row sm:items-center sm:justify-between lg:col-span-2">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Manual terms are approved active records. Suggested terms stay in
            the review workflow.
          </p>
          <Button disabled={!canSubmit} type="submit">
            {isSubmitting ? "Creating..." : "Create term"}
          </Button>
        </div>
        {readOnlyMessage ? (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200 lg:col-span-2">
            {readOnlyMessage}
          </div>
        ) : null}
        {errorMessage ? (
          <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200 lg:col-span-2">
            {errorMessage}
          </div>
        ) : null}
      </form>
    </SectionCard>
  );
}
