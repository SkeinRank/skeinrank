import { type FormEvent, useState } from "react";

import type { AliasCreateRequest } from "../types";
import { Button } from "./ui/button";
import { Input } from "./ui/input";

type AddAliasFormProps = {
  disabled?: boolean;
  errorMessage?: string | null;
  isSubmitting?: boolean;
  onSubmit: (payload: AliasCreateRequest) => Promise<void> | void;
};

export function AddAliasForm({ disabled = false, errorMessage, isSubmitting = false, onSubmit }: AddAliasFormProps) {
  const [aliasValue, setAliasValue] = useState("");
  const [notes, setNotes] = useState("");
  const canSubmit = !disabled && aliasValue.trim().length > 0 && !isSubmitting;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }

    try {
      await onSubmit({
        alias_value: aliasValue.trim(),
        confidence: 1,
        notes: notes.trim() || null,
        status: "active",
      });

      setAliasValue("");
      setNotes("");
    } catch {
      // The parent mutation owns user-facing error rendering.
    }
  }

  return (
    <form className="space-y-3" onSubmit={handleSubmit}>
      <label className="space-y-1.5">
        <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Alias</span>
        <Input disabled={disabled || isSubmitting} onChange={(event) => setAliasValue(event.target.value)} placeholder="k8s" value={aliasValue} />
      </label>
      <label className="space-y-1.5">
        <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Notes</span>
        <Input
          disabled={disabled || isSubmitting}
          onChange={(event) => setNotes(event.target.value)}
          placeholder="Optional rationale, source, or team note"
          value={notes}
        />
      </label>
      <p className="text-xs text-slate-500 dark:text-slate-400">
        Manual aliases are treated as approved governance entries. Suggestion confidence will appear in the approval workflow.
      </p>
      {errorMessage ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200">
          {errorMessage}
        </div>
      ) : null}
      <Button className="w-full" disabled={!canSubmit} type="submit">
        {isSubmitting ? "Adding..." : "Add alias"}
      </Button>
    </form>
  );
}
