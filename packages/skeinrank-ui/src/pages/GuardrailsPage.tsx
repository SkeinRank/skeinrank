import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useMemo, useState } from "react";

import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../components/ui/card";
import { Input } from "../components/ui/input";
import {
  createStopListEntry,
  deleteStopListEntry,
  listProfiles,
  listStopList,
  updateStopListEntry,
} from "../lib/api";
import { permissionsForUser } from "../permissions";
import type {
  AuthUser,
  Profile,
  StopListCreateRequest,
  StopListEntry,
  StopListTarget,
  StopListUpdateRequest,
} from "../types";

const stopListTargets: StopListTarget[] = ["alias", "canonical", "both"];

export function GuardrailsPage({ currentUser }: { currentUser: AuthUser }) {
  const permissions = permissionsForUser(currentUser);
  const queryClient = useQueryClient();
  const profilesQuery = useQuery({
    queryKey: ["profiles"],
    queryFn: listProfiles,
  });
  const [selectedProfile, setSelectedProfile] = useState<string | null>(null);
  const [selectedEntryId, setSelectedEntryId] = useState<number | null>(null);

  useEffect(() => {
    if (!profilesQuery.data || profilesQuery.data.length === 0) {
      setSelectedProfile(null);
      setSelectedEntryId(null);
      return;
    }

    if (!selectedProfile || !profilesQuery.data.some((profile) => profile.name === selectedProfile)) {
      setSelectedProfile(profilesQuery.data[0].name);
      setSelectedEntryId(null);
    }
  }, [profilesQuery.data, selectedProfile]);

  const stopListQuery = useQuery({
    queryKey: ["stop-list", selectedProfile],
    queryFn: () => listStopList(selectedProfile ?? ""),
    enabled: Boolean(selectedProfile) && permissions.canReadStopLists,
  });

  useEffect(() => {
    if (!stopListQuery.data || stopListQuery.data.length === 0) {
      setSelectedEntryId(null);
      return;
    }
    if (!selectedEntryId || !stopListQuery.data.some((entry) => entry.id === selectedEntryId)) {
      setSelectedEntryId(stopListQuery.data[0].id);
    }
  }, [selectedEntryId, stopListQuery.data]);

  const selectedEntry = useMemo(() => {
    if (!stopListQuery.data || !selectedEntryId) {
      return null;
    }
    return stopListQuery.data.find((entry) => entry.id === selectedEntryId) ?? null;
  }, [selectedEntryId, stopListQuery.data]);

  const createMutation = useMutation({
    mutationFn: (payload: StopListCreateRequest) => {
      if (!selectedProfile) {
        throw new Error("Select a profile before adding a stop-list entry.");
      }
      return createStopListEntry(selectedProfile, payload);
    },
    onSuccess: (entry) => {
      setSelectedEntryId(entry.id);
      upsertStopListEntry(queryClient, selectedProfile, entry);
      void queryClient.invalidateQueries({ queryKey: ["stop-list", selectedProfile] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ entryId, payload }: { entryId: number; payload: StopListUpdateRequest }) => {
      if (!selectedProfile) {
        throw new Error("Select a profile before updating a stop-list entry.");
      }
      return updateStopListEntry(selectedProfile, entryId, payload);
    },
    onSuccess: (entry) => {
      setSelectedEntryId(entry.id);
      upsertStopListEntry(queryClient, selectedProfile, entry);
      void queryClient.invalidateQueries({ queryKey: ["stop-list", selectedProfile] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (entryId: number) => {
      if (!selectedProfile) {
        throw new Error("Select a profile before deleting a stop-list entry.");
      }
      return deleteStopListEntry(selectedProfile, entryId);
    },
    onSuccess: (_result, entryId) => {
      setSelectedEntryId(null);
      removeStopListEntry(queryClient, selectedProfile, entryId);
      void queryClient.invalidateQueries({ queryKey: ["stop-list", selectedProfile] });
    },
  });

  async function handleCreateEntry(payload: StopListCreateRequest) {
    await createMutation.mutateAsync(payload);
  }

  async function handleUpdateEntry(entryId: number, payload: StopListUpdateRequest) {
    await updateMutation.mutateAsync({ entryId, payload });
  }

  async function handleDeleteEntry(entryId: number) {
    await deleteMutation.mutateAsync(entryId);
  }

  return (
    <div className="space-y-6">
      <section className="grid gap-4 md:grid-cols-3">
        <StatCard description="Profile-scoped terminology namespace." title="Profile" value={selectedProfile ?? "None"} />
        <StatCard description="Active and disabled blocked values." title="Stop-list entries" value={String(stopListQuery.data?.length ?? 0)} />
        <Card>
          <CardHeader>
            <CardTitle>Guardrail model</CardTitle>
            <CardDescription>Block noisy terms before they enter suggestions or runtime dictionaries.</CardDescription>
          </CardHeader>
          <CardContent>
            <Badge>Profile → Stop list → API guardrail</Badge>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="space-y-6">
          <GuardrailsToolbar
            isLoading={profilesQuery.isLoading}
            loadErrorMessage={profilesQuery.isError ? profilesQuery.error.message : null}
            onSelectProfile={(profileName) => {
              setSelectedProfile(profileName);
              setSelectedEntryId(null);
              createMutation.reset();
              updateMutation.reset();
              deleteMutation.reset();
            }}
            profiles={profilesQuery.data ?? []}
            selectedProfile={selectedProfile}
          />

          <CreateStopListEntryForm
            disabled={!selectedProfile || !permissions.canManageStopLists}
            errorMessage={errorMessage(createMutation.error)}
            isSubmitting={createMutation.isPending}
            onSubmit={handleCreateEntry}
            readOnlyMessage={permissions.canManageStopLists ? null : "Your role can inspect guardrails, but only admins and moderators can update stop lists."}
          />

          <StopListTable
            entries={stopListQuery.data ?? []}
            isLoading={stopListQuery.isLoading && Boolean(selectedProfile)}
            loadErrorMessage={stopListQuery.isError ? stopListQuery.error.message : null}
            onSelectEntry={(entry) => {
              setSelectedEntryId(entry.id);
              updateMutation.reset();
              deleteMutation.reset();
            }}
            selectedEntryId={selectedEntryId}
          />
        </div>

        <StopListEntryDetailsPanel
          canManage={permissions.canManageStopLists}
          deleteErrorMessage={errorMessage(deleteMutation.error)}
          entry={selectedEntry}
          isDeleting={deleteMutation.isPending}
          isUpdating={updateMutation.isPending}
          onDelete={handleDeleteEntry}
          onUpdate={handleUpdateEntry}
          updateErrorMessage={errorMessage(updateMutation.error)}
        />
      </section>
    </div>
  );
}

function StatCard({ description, title, value }: { description: string; title: string; value: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="text-3xl font-semibold">{value}</div>
      </CardContent>
    </Card>
  );
}

function GuardrailsToolbar({
  isLoading,
  loadErrorMessage,
  onSelectProfile,
  profiles,
  selectedProfile,
}: {
  isLoading: boolean;
  loadErrorMessage?: string | null;
  onSelectProfile: (profileName: string) => void;
  profiles: Profile[];
  selectedProfile: string | null;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Guardrails</CardTitle>
        <CardDescription>Manage profile stop lists that block noisy aliases and canonical terms before they enter governance workflows.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {loadErrorMessage ? <InlineError message={loadErrorMessage} /> : null}
        {isLoading ? <p className="text-sm text-slate-500 dark:text-slate-400">Loading profiles...</p> : null}
        {profiles.length > 0 ? (
          <div className="space-y-2">
            <div className="text-sm font-medium text-slate-700 dark:text-slate-200">Profile</div>
            <div className="flex flex-wrap gap-2">
              {profiles.map((profile) => (
                <button
                  className={`rounded-full border px-3 py-1.5 text-sm font-medium transition-colors ${
                    selectedProfile === profile.name
                      ? "border-slate-950 bg-slate-950 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-950"
                      : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300 dark:hover:bg-slate-900"
                  }`}
                  key={profile.id}
                  onClick={() => onSelectProfile(profile.name)}
                  type="button"
                >
                  {profile.name}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <p className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
            No profiles found. Create a terminology profile before adding stop-list guardrails.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function CreateStopListEntryForm({
  disabled = false,
  errorMessage,
  isSubmitting = false,
  onSubmit,
  readOnlyMessage,
}: {
  disabled?: boolean;
  errorMessage?: string | null;
  isSubmitting?: boolean;
  onSubmit: (payload: StopListCreateRequest) => Promise<void> | void;
  readOnlyMessage?: string | null;
}) {
  const [value, setValue] = useState("");
  const [target, setTarget] = useState<StopListTarget>("alias");
  const [reason, setReason] = useState("");
  const canSubmit = !disabled && value.trim().length > 0 && !isSubmitting;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }
    try {
      await onSubmit({
        value: value.trim(),
        target,
        reason: reason.trim() || null,
        is_active: true,
      });
      setValue("");
      setTarget("alias");
      setReason("");
    } catch {
      // Parent mutation owns user-facing error rendering.
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Add stop-list entry</CardTitle>
        <CardDescription>Block exact values that are too generic, ambiguous, or unsafe for the selected profile.</CardDescription>
      </CardHeader>
      <CardContent>
        {readOnlyMessage ? (
          <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
            {readOnlyMessage}
          </div>
        ) : null}
        <form className="space-y-4" onSubmit={handleSubmit}>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Blocked value</span>
              <Input disabled={disabled || isSubmitting} onChange={(event) => setValue(event.target.value)} placeholder="service" value={value} />
            </label>
            <label className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Target</span>
              <select
                className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100 disabled:cursor-not-allowed disabled:bg-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:disabled:bg-slate-900 dark:focus:border-slate-500 dark:focus:ring-slate-800"
                disabled={disabled || isSubmitting}
                onChange={(event) => setTarget(event.target.value as StopListTarget)}
                value={target}
              >
                {stopListTargets.map((entryTarget) => (
                  <option key={entryTarget} value={entryTarget}>{entryTarget}</option>
                ))}
              </select>
            </label>
          </div>
          <label className="block space-y-1.5">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Reason</span>
            <Input disabled={disabled || isSubmitting} onChange={(event) => setReason(event.target.value)} placeholder="Too generic for incident search" value={reason} />
          </label>
          {errorMessage ? <InlineError message={errorMessage} /> : null}
          <Button disabled={!canSubmit} type="submit">{isSubmitting ? "Adding..." : "Add to stop list"}</Button>
        </form>
      </CardContent>
    </Card>
  );
}

function StopListTable({
  entries,
  isLoading,
  loadErrorMessage,
  onSelectEntry,
  selectedEntryId,
}: {
  entries: StopListEntry[];
  isLoading: boolean;
  loadErrorMessage?: string | null;
  onSelectEntry: (entry: StopListEntry) => void;
  selectedEntryId: number | null;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Stop list</CardTitle>
        <CardDescription>Values blocked from direct edits, suggestions, and approvals for the selected profile.</CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        {loadErrorMessage ? <div className="p-5"><InlineError message={loadErrorMessage} /></div> : null}
        {isLoading ? <p className="p-5 text-sm text-slate-500 dark:text-slate-400">Loading stop-list entries...</p> : null}
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-950 dark:text-slate-400">
              <tr>
                <th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">Value</th>
                <th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">Target</th>
                <th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">Status</th>
                <th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">Reason</th>
              </tr>
            </thead>
            <tbody>
              {entries.length === 0 ? (
                <tr><td className="px-5 py-8 text-center text-sm text-slate-500 dark:text-slate-400" colSpan={4}>No stop-list entries yet.</td></tr>
              ) : entries.map((entry) => (
                <tr
                  className={`cursor-pointer transition-colors ${selectedEntryId === entry.id ? "bg-slate-100 dark:bg-slate-800/70" : "hover:bg-slate-50 dark:hover:bg-slate-900"}`}
                  key={entry.id}
                  onClick={() => onSelectEntry(entry)}
                >
                  <td className="border-b border-slate-100 px-5 py-4 dark:border-slate-800"><span className="font-medium text-slate-950 dark:text-slate-50">{entry.value}</span></td>
                  <td className="border-b border-slate-100 px-5 py-4 dark:border-slate-800"><Badge>{entry.target}</Badge></td>
                  <td className="border-b border-slate-100 px-5 py-4 dark:border-slate-800"><StopListStatusBadge isActive={entry.is_active} /></td>
                  <td className="border-b border-slate-100 px-5 py-4 text-slate-600 dark:border-slate-800 dark:text-slate-300">{entry.reason || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function StopListEntryDetailsPanel({
  canManage,
  deleteErrorMessage,
  entry,
  isDeleting = false,
  isUpdating = false,
  onDelete,
  onUpdate,
  updateErrorMessage,
}: {
  canManage: boolean;
  deleteErrorMessage?: string | null;
  entry: StopListEntry | null;
  isDeleting?: boolean;
  isUpdating?: boolean;
  onDelete: (entryId: number) => Promise<void> | void;
  onUpdate: (entryId: number, payload: StopListUpdateRequest) => Promise<void> | void;
  updateErrorMessage?: string | null;
}) {
  const [value, setValue] = useState("");
  const [target, setTarget] = useState<StopListTarget>("alias");
  const [reason, setReason] = useState("");
  const [isActive, setIsActive] = useState(true);

  useEffect(() => {
    setValue(entry?.value ?? "");
    setTarget(entry?.target ?? "alias");
    setReason(entry?.reason ?? "");
    setIsActive(entry?.is_active ?? true);
  }, [entry?.id, entry?.is_active, entry?.reason, entry?.target, entry?.value]);

  if (!entry) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Stop-list details</CardTitle>
          <CardDescription>Select an entry to edit target, reason, or active status.</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-slate-500 dark:text-slate-400">No stop-list entry selected.</p>
        </CardContent>
      </Card>
    );
  }

  const canSave = canManage && value.trim().length > 0 && !isUpdating && !isDeleting;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!entry || !canSave) {
      return;
    }
    await onUpdate(entry.id, {
      value: value.trim(),
      target,
      reason: reason.trim() || null,
      is_active: isActive,
    });
  }

  async function handleDelete() {
    if (!entry || !canManage || isDeleting) {
      return;
    }
    if (!window.confirm(`Delete stop-list entry ${entry.value}?`)) {
      return;
    }
    await onDelete(entry.id);
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>{entry.value}</CardTitle>
            <CardDescription>Profile guardrail for {entry.target} values.</CardDescription>
          </div>
          <StopListStatusBadge isActive={entry.is_active} />
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        {!canManage ? (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
            Contributors can inspect stop lists, but only admins and moderators can update guardrails.
          </div>
        ) : null}
        <form className="space-y-4" onSubmit={handleSubmit}>
          <label className="space-y-1.5">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit blocked value</span>
            <Input disabled={!canManage || isUpdating || isDeleting} onChange={(event) => setValue(event.target.value)} value={value} />
          </label>
          <label className="space-y-1.5">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit target</span>
            <select
              className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100 disabled:cursor-not-allowed disabled:bg-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:disabled:bg-slate-900 dark:focus:border-slate-500 dark:focus:ring-slate-800"
              disabled={!canManage || isUpdating || isDeleting}
              onChange={(event) => setTarget(event.target.value as StopListTarget)}
              value={target}
            >
              {stopListTargets.map((entryTarget) => (
                <option key={entryTarget} value={entryTarget}>{entryTarget}</option>
              ))}
            </select>
          </label>
          <label className="space-y-1.5">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit reason</span>
            <Input disabled={!canManage || isUpdating || isDeleting} onChange={(event) => setReason(event.target.value)} placeholder="Optional reason" value={reason} />
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
            <input checked={isActive} disabled={!canManage || isUpdating || isDeleting} onChange={(event) => setIsActive(event.target.checked)} type="checkbox" />
            Active guardrail
          </label>
          {updateErrorMessage ? <InlineError message={updateErrorMessage} /> : null}
          {deleteErrorMessage ? <InlineError message={deleteErrorMessage} /> : null}
          <div className="flex flex-wrap gap-2">
            <Button disabled={!canSave} type="submit">{isUpdating ? "Saving..." : "Save stop-list entry"}</Button>
            <Button disabled={!canManage || isUpdating || isDeleting} onClick={handleDelete} type="button" variant="secondary">{isDeleting ? "Deleting..." : "Delete stop-list entry"}</Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function StopListStatusBadge({ isActive }: { isActive: boolean }) {
  return isActive ? <Badge className="bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200">active</Badge> : <Badge className="bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">disabled</Badge>;
}

function InlineError({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200">
      {message}
    </div>
  );
}

function errorMessage(error: unknown) {
  if (!error) {
    return null;
  }
  return error instanceof Error ? error.message : "Request failed. Check the governance API and try again.";
}

function upsertStopListEntry(
  queryClient: ReturnType<typeof useQueryClient>,
  profileName: string | null,
  entry: StopListEntry,
) {
  queryClient.setQueryData<StopListEntry[]>(["stop-list", profileName], (entries = []) => {
    const withoutEntry = entries.filter((current) => current.id !== entry.id);
    return [entry, ...withoutEntry].sort(sortStopListEntries);
  });
}

function removeStopListEntry(
  queryClient: ReturnType<typeof useQueryClient>,
  profileName: string | null,
  entryId: number,
) {
  queryClient.setQueryData<StopListEntry[]>(["stop-list", profileName], (entries = []) => entries.filter((entry) => entry.id !== entryId));
}

function sortStopListEntries(left: StopListEntry, right: StopListEntry) {
  if (left.target !== right.target) {
    return left.target.localeCompare(right.target);
  }
  return left.normalized_value.localeCompare(right.normalized_value);
}
