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
  const [confidence, setConfidence] = useState("1");
  const [notes, setNotes] = useState("");
  const confidenceValue = Number(confidence);
  const confidenceIsValid = Number.isFinite(confidenceValue) && confidenceValue >= 0 && confidenceValue <= 1;
  const canSubmit = !disabled && aliasValue.trim().length > 0 && confidenceIsValid && !isSubmitting;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }

    try {
      await onSubmit({
        alias_value: aliasValue.trim(),
        confidence: confidenceValue,
        notes: notes.trim() || null,
        status: "active",
      });

      setAliasValue("");
      setConfidence("1");
      setNotes("");
    } catch {
      // The parent mutation owns user-facing error rendering.
    }
  }

  return (
    <form className="space-y-3" onSubmit={handleSubmit}>
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_120px]">
        <label className="space-y-1.5">
          <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Alias value</span>
          <Input disabled={disabled || isSubmitting} onChange={(event) => setAliasValue(event.target.value)} placeholder="k8s" value={aliasValue} />
        </label>
        <label className="space-y-1.5">
          <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Confidence</span>
          <Input
            disabled={disabled || isSubmitting}
            max="1"
            min="0"
            onChange={(event) => setConfidence(event.target.value)}
            step="0.01"
            type="number"
            value={confidence}
          />
        </label>
      </div>
      <label className="space-y-1.5">
        <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Notes</span>
        <Input
          disabled={disabled || isSubmitting}
          onChange={(event) => setNotes(event.target.value)}
          placeholder="Optional rationale, source, or team note"
          value={notes}
        />
      </label>
      {!confidenceIsValid ? <p className="text-sm text-red-600 dark:text-red-300">Confidence must be between 0 and 1.</p> : null}
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
