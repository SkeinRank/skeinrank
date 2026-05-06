import { useMutation } from "@tanstack/react-query";
import { ClipboardCheck, Download } from "lucide-react";

import { exportSnapshot } from "../lib/api";
import type { RuntimeSnapshot } from "../types";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";

export function SnapshotPanel({ disabled = false, profileName, readOnlyMessage }: { disabled?: boolean; profileName: string | null; readOnlyMessage?: string | null }) {
  const mutation = useMutation<RuntimeSnapshot>({
    mutationFn: () => {
      if (!profileName) {
        throw new Error("Select a profile before exporting a snapshot.");
      }
      return exportSnapshot(profileName, {
        snapshot_version: `${profileName}@draft`,
        description: "Runtime snapshot exported from the governance console.",
      });
    },
  });

  function handleDownloadSnapshot() {
    if (!mutation.data || !profileName) {
      return;
    }

    const snapshotJson = JSON.stringify(mutation.data, null, 2);
    const blob = new Blob([snapshotJson], { type: "application/json" });
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = `skeinrank-${profileName}-snapshot-draft.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(objectUrl);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Runtime snapshot</CardTitle>
        <CardDescription>
          Export a runtime-compatible JSON snapshot for SkeinRank core, API, or Elasticsearch enrichment.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <Button disabled={disabled || !profileName || mutation.isPending} onClick={() => mutation.mutate()} type="button">
            <ClipboardCheck className="mr-2 h-4 w-4" />
            {mutation.isPending ? "Exporting..." : "Export draft snapshot"}
          </Button>
          <Button disabled={disabled || !mutation.data || !profileName} onClick={handleDownloadSnapshot} type="button" variant="secondary">
            <Download className="mr-2 h-4 w-4" />
            Download JSON
          </Button>
        </div>

        {readOnlyMessage ? (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
            {readOnlyMessage}
          </div>
        ) : null}

        {mutation.isError ? <p className="text-sm text-red-600 dark:text-red-300">{mutation.error.message}</p> : null}

        {mutation.data ? (
          <pre className="max-h-80 overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-100 dark:bg-black">
            {JSON.stringify(mutation.data, null, 2)}
          </pre>
        ) : (
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Draft snapshots can be downloaded and used by SkeinRank runtime components. Publishing and rollback will be added in a later workflow.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
