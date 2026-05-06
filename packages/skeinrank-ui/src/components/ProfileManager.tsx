import { type FormEvent, useEffect, useMemo, useState } from "react";

import type { Profile, ProfileCreateRequest, ProfileUpdateRequest } from "../types";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Input } from "./ui/input";

type ProfileManagerProps = {
  createErrorMessage?: string | null;
  deleteErrorMessage?: string | null;
  disabled?: boolean;
  isCreating?: boolean;
  isDeleting?: boolean;
  isUpdating?: boolean;
  loading?: boolean;
  loadErrorMessage?: string | null;
  onCreateProfile: (payload: ProfileCreateRequest) => Promise<void> | void;
  onDeleteProfile: (profileName: string) => Promise<void> | void;
  onSelectProfile: (profileName: string) => void;
  onUpdateProfile: (profileName: string, payload: ProfileUpdateRequest) => Promise<void> | void;
  profiles: Profile[];
  selectedProfileName: string | null;
  updateErrorMessage?: string | null;
};

export function ProfileManager({
  createErrorMessage,
  deleteErrorMessage,
  disabled = false,
  isCreating = false,
  isDeleting = false,
  isUpdating = false,
  loading = false,
  loadErrorMessage,
  onCreateProfile,
  onDeleteProfile,
  onSelectProfile,
  onUpdateProfile,
  profiles,
  selectedProfileName,
  updateErrorMessage,
}: ProfileManagerProps) {
  const selectedProfile = useMemo(
    () => profiles.find((profile) => profile.name === selectedProfileName) ?? null,
    [profiles, selectedProfileName],
  );
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");

  useEffect(() => {
    setEditName(selectedProfile?.name ?? "");
    setEditDescription(selectedProfile?.description ?? "");
  }, [selectedProfile?.description, selectedProfile?.id, selectedProfile?.name]);

  const canCreate = !disabled && newName.trim().length > 0 && !isCreating;
  const canUpdate = Boolean(selectedProfile) && !disabled && editName.trim().length > 0 && !isUpdating;
  const canDelete = Boolean(selectedProfile) && !disabled && !isDeleting;

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canCreate) {
      return;
    }

    try {
      await onCreateProfile({
        name: newName.trim(),
        description: newDescription.trim() || null,
      });
      setNewName("");
      setNewDescription("");
    } catch {
      // Parent mutation owns user-facing error rendering.
    }
  }

  async function handleUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProfile || !canUpdate) {
      return;
    }

    try {
      await onUpdateProfile(selectedProfile.name, {
        name: editName.trim(),
        description: editDescription.trim() || null,
      });
    } catch {
      // Parent mutation owns user-facing error rendering.
    }
  }

  async function handleDelete() {
    if (!selectedProfile || !canDelete) {
      return;
    }

    const confirmed = window.confirm(
      `Delete profile "${selectedProfile.name}"? This will also delete its canonical terms and aliases.`,
    );
    if (!confirmed) {
      return;
    }

    try {
      await onDeleteProfile(selectedProfile.name);
    } catch {
      // Parent mutation owns user-facing error rendering.
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Profiles</CardTitle>
        <CardDescription>Create, select, rename, and delete terminology namespaces.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {loadErrorMessage ? <InlineError message={loadErrorMessage} /> : null}

        {loading ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">Loading profiles...</p>
        ) : profiles.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {profiles.map((profile) => (
              <button
                className={`rounded-full border px-3 py-1.5 text-sm font-medium transition-colors ${
                  selectedProfileName === profile.name
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
        ) : (
          <p className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
            No profiles found. Create a terminology profile to start adding canonical terms and aliases.
          </p>
        )}

        <form className="space-y-3 rounded-xl border border-slate-100 p-4 dark:border-slate-800" onSubmit={handleCreate}>
          <div>
            <h3 className="text-sm font-semibold text-slate-950 dark:text-slate-50">Create profile</h3>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Use profiles as namespaces for different domains, teams, customers, or corpora.
            </p>
          </div>
          <label className="space-y-1.5">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-200">New profile name</span>
            <Input
              disabled={disabled || isCreating}
              onChange={(event) => setNewName(event.target.value)}
              placeholder="infra_incidents"
              value={newName}
            />
          </label>
          <label className="space-y-1.5">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-200">New profile description</span>
            <Input
              disabled={disabled || isCreating}
              onChange={(event) => setNewDescription(event.target.value)}
              placeholder="Optional namespace note"
              value={newDescription}
            />
          </label>
          {createErrorMessage ? <InlineError message={createErrorMessage} /> : null}
          <Button disabled={!canCreate} type="submit">
            {isCreating ? "Creating..." : "Create profile"}
          </Button>
        </form>

        {selectedProfile ? (
          <form className="space-y-3 rounded-xl border border-slate-100 p-4 dark:border-slate-800" onSubmit={handleUpdate}>
            <div>
              <h3 className="text-sm font-semibold text-slate-950 dark:text-slate-50">Selected profile</h3>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                Rename the namespace or update the profile description.
              </p>
            </div>
            <label className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Profile name</span>
              <Input
                disabled={disabled || isUpdating || isDeleting}
                onChange={(event) => setEditName(event.target.value)}
                value={editName}
              />
            </label>
            <label className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Profile description</span>
              <Input
                disabled={disabled || isUpdating || isDeleting}
                onChange={(event) => setEditDescription(event.target.value)}
                placeholder="Optional profile description"
                value={editDescription}
              />
            </label>
            {updateErrorMessage ? <InlineError message={updateErrorMessage} /> : null}
            {deleteErrorMessage ? <InlineError message={deleteErrorMessage} /> : null}
            <div className="flex flex-wrap gap-2">
              <Button disabled={!canUpdate} type="submit">
                {isUpdating ? "Saving..." : "Save profile"}
              </Button>
              <Button disabled={!canDelete} onClick={handleDelete} type="button" variant="secondary">
                {isDeleting ? "Deleting..." : "Delete profile"}
              </Button>
            </div>
          </form>
        ) : null}
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
