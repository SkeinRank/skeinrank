import { useMutation } from "@tanstack/react-query";
import { ClipboardCheck } from "lucide-react";

import { exportSnapshot } from "../lib/api";
import type { RuntimeSnapshot } from "../types";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";

export function SnapshotPanel({ profileName }: { profileName: string | null }) {
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

  return (
    <Card>
      <CardHeader>
        <CardTitle>Runtime snapshot</CardTitle>
        <CardDescription>
          Export a runtime-compatible JSON snapshot for SkeinRank core, API, or Elasticsearch enrichment.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Button disabled={!profileName || mutation.isPending} onClick={() => mutation.mutate()} type="button">
          <ClipboardCheck className="mr-2 h-4 w-4" />
          {mutation.isPending ? "Exporting..." : "Export draft snapshot"}
        </Button>

        {mutation.isError ? <p className="text-sm text-red-600 dark:text-red-300">{mutation.error.message}</p> : null}

        {mutation.data ? (
          <pre className="max-h-80 overflow-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-100 dark:bg-black">
            {JSON.stringify(mutation.data, null, 2)}
          </pre>
        ) : (
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Snapshot publishing is not enabled yet. This skeleton only exports the current active profile as JSON.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
