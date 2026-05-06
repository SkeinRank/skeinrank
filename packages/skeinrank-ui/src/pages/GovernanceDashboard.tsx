import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { AddTermForm } from "../components/AddTermForm";
import { ProfileManager } from "../components/ProfileManager";
import { SnapshotPanel } from "../components/SnapshotPanel";
import { TermDetailsPanel } from "../components/TermDetailsPanel";
import { TermsTable } from "../components/TermsTable";
import { Badge } from "../components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import {
  createAlias,
  createProfile,
  createTerm,
  deleteAlias,
  deleteProfile,
  deleteTerm,
  listProfiles,
  listTerms,
  updateAlias,
  updateProfile,
  updateTerm,
} from "../lib/api";
import { permissionsForUser } from "../permissions";
import type {
  AliasCreateRequest,
  AliasUpdateRequest,
  CanonicalTerm,
  Profile,
  ProfileCreateRequest,
  ProfileUpdateRequest,
  TermAlias,
  TermCreateRequest,
  TermUpdateRequest,
  AuthUser,
} from "../types";

export function GovernanceDashboard({ currentUser }: { currentUser: AuthUser }) {
  const permissions = permissionsForUser(currentUser);
  const queryClient = useQueryClient();
  const profilesQuery = useQuery({
    queryKey: ["profiles"],
    queryFn: listProfiles,
  });

  const [selectedProfile, setSelectedProfile] = useState<string | null>(null);
  const [selectedTermId, setSelectedTermId] = useState<number | null>(null);

  useEffect(() => {
    if (!profilesQuery.data || profilesQuery.data.length === 0) {
      setSelectedProfile(null);
      setSelectedTermId(null);
      return;
    }

    if (!selectedProfile || !profilesQuery.data.some((profile) => profile.name === selectedProfile)) {
      setSelectedProfile(profilesQuery.data[0].name);
      setSelectedTermId(null);
    }
  }, [profilesQuery.data, selectedProfile]);

  const termsQuery = useQuery({
    queryKey: ["terms", selectedProfile],
    queryFn: () => listTerms(selectedProfile ?? ""),
    enabled: Boolean(selectedProfile),
  });

  useEffect(() => {
    if (!termsQuery.data) {
      return;
    }

    if (termsQuery.data.length === 0) {
      setSelectedTermId(null);
      return;
    }

    if (!selectedTermId || !termsQuery.data.some((term) => term.id === selectedTermId)) {
      setSelectedTermId(termsQuery.data[0].id);
    }
  }, [selectedTermId, termsQuery.data]);

  const selectedTerm = useMemo(() => {
    if (!termsQuery.data || !selectedTermId) {
      return null;
    }
    return termsQuery.data.find((term) => term.id === selectedTermId) ?? null;
  }, [selectedTermId, termsQuery.data]);

  const createProfileMutation = useMutation({
    mutationFn: (payload: ProfileCreateRequest) => createProfile(payload),
    onSuccess: (profile) => {
      setSelectedProfile(profile.name);
      setSelectedTermId(null);
      queryClient.setQueryData(["profiles"], (currentProfiles = []) => {
        const profiles = currentProfiles as Profile[];
        if (profiles.some((currentProfile) => currentProfile.id === profile.id)) {
          return profiles;
        }
        return [...profiles, profile].sort((left, right) => left.normalized_name.localeCompare(right.normalized_name));
      });
      queryClient.setQueryData(["terms", profile.name], []);
      void queryClient.invalidateQueries({ queryKey: ["profiles"] });
    },
  });

  const updateProfileMutation = useMutation({
    mutationFn: ({ profileName, payload }: { profileName: string; payload: ProfileUpdateRequest }) => updateProfile(profileName, payload),
    onSuccess: (profile, variables) => {
      setSelectedProfile(profile.name);
      setSelectedTermId(null);
      queryClient.setQueryData(["profiles"], (currentProfiles = []) =>
        (currentProfiles as Profile[])
          .map((currentProfile) => (currentProfile.id === profile.id ? profile : currentProfile))
          .sort((left, right) => left.normalized_name.localeCompare(right.normalized_name)),
      );
      if (variables.profileName !== profile.name) {
        queryClient.removeQueries({ queryKey: ["terms", variables.profileName] });
      }
      void queryClient.invalidateQueries({ queryKey: ["profiles"] });
      void queryClient.invalidateQueries({ queryKey: ["terms", profile.name] });
    },
  });

  const deleteProfileMutation = useMutation({
    mutationFn: (profileName: string) => deleteProfile(profileName),
    onSuccess: (_result, profileName) => {
      queryClient.setQueryData(["profiles"], (currentProfiles = []) =>
        (currentProfiles as Array<{ name: string }>).filter((profile) => profile.name !== profileName),
      );
      queryClient.removeQueries({ queryKey: ["terms", profileName] });
      setSelectedProfile(null);
      setSelectedTermId(null);
      void queryClient.invalidateQueries({ queryKey: ["profiles"] });
    },
  });

  const createTermMutation = useMutation({
    mutationFn: (payload: TermCreateRequest) => {
      if (!selectedProfile) {
        throw new Error("Select a profile before creating a term.");
      }
      return createTerm(selectedProfile, payload);
    },
    onSuccess: (term) => {
      setSelectedTermId(term.id);
      queryClient.setQueryData<CanonicalTerm[]>(["terms", selectedProfile], (currentTerms = []) => {
        if (currentTerms.some((currentTerm) => currentTerm.id === term.id)) {
          return currentTerms;
        }
        return [...currentTerms, term];
      });
      void queryClient.invalidateQueries({ queryKey: ["terms", selectedProfile] });
    },
  });

  const updateTermMutation = useMutation({
    mutationFn: ({ term, payload }: { term: CanonicalTerm; payload: TermUpdateRequest }) => {
      if (!selectedProfile) {
        throw new Error("Select a profile before updating a term.");
      }
      return updateTerm(selectedProfile, term.canonical_value, payload);
    },
    onSuccess: (term) => {
      setSelectedTermId(term.id);
      queryClient.setQueryData<CanonicalTerm[]>(["terms", selectedProfile], (currentTerms = []) =>
        currentTerms.map((currentTerm) => (currentTerm.id === term.id ? term : currentTerm)),
      );
      void queryClient.invalidateQueries({ queryKey: ["terms", selectedProfile] });
    },
  });

  const deleteTermMutation = useMutation({
    mutationFn: (term: CanonicalTerm) => {
      if (!selectedProfile) {
        throw new Error("Select a profile before deleting a term.");
      }
      return deleteTerm(selectedProfile, term.canonical_value);
    },
    onSuccess: (_result, term) => {
      setSelectedTermId(null);
      queryClient.setQueryData<CanonicalTerm[]>(["terms", selectedProfile], (currentTerms = []) =>
        currentTerms.filter((currentTerm) => currentTerm.id !== term.id),
      );
      void queryClient.invalidateQueries({ queryKey: ["terms", selectedProfile] });
    },
  });

  const createAliasMutation = useMutation({
    mutationFn: (payload: AliasCreateRequest) => {
      if (!selectedProfile || !selectedTerm) {
        throw new Error("Select a canonical term before creating an alias.");
      }
      return createAlias(selectedProfile, selectedTerm.canonical_value, payload);
    },
    onSuccess: (alias) => {
      queryClient.setQueryData<CanonicalTerm[]>(["terms", selectedProfile], (currentTerms = []) =>
        currentTerms.map((term) => {
          if (term.id !== selectedTerm?.id || term.aliases.some((currentAlias) => currentAlias.id === alias.id)) {
            return term;
          }
          return { ...term, aliases: [...term.aliases, alias] };
        }),
      );
      void queryClient.invalidateQueries({ queryKey: ["terms", selectedProfile] });
    },
  });

  const updateAliasMutation = useMutation({
    mutationFn: ({ alias, payload }: { alias: TermAlias; payload: AliasUpdateRequest }) => {
      if (!selectedProfile || !selectedTerm) {
        throw new Error("Select a canonical term before updating an alias.");
      }
      return updateAlias(selectedProfile, selectedTerm.canonical_value, alias.id, payload);
    },
    onSuccess: (alias) => {
      queryClient.setQueryData<CanonicalTerm[]>(["terms", selectedProfile], (currentTerms = []) =>
        currentTerms.map((term) => {
          if (term.id !== selectedTerm?.id) {
            return term;
          }
          return {
            ...term,
            aliases: term.aliases.map((currentAlias) => (currentAlias.id === alias.id ? alias : currentAlias)),
          };
        }),
      );
      void queryClient.invalidateQueries({ queryKey: ["terms", selectedProfile] });
    },
  });

  const deleteAliasMutation = useMutation({
    mutationFn: (alias: TermAlias) => {
      if (!selectedProfile || !selectedTerm) {
        throw new Error("Select a canonical term before deleting an alias.");
      }
      return deleteAlias(selectedProfile, selectedTerm.canonical_value, alias.id);
    },
    onSuccess: (_result, alias) => {
      queryClient.setQueryData<CanonicalTerm[]>(["terms", selectedProfile], (currentTerms = []) =>
        currentTerms.map((term) => {
          if (term.id !== selectedTerm?.id) {
            return term;
          }
          return { ...term, aliases: term.aliases.filter((currentAlias) => currentAlias.id !== alias.id) };
        }),
      );
      void queryClient.invalidateQueries({ queryKey: ["terms", selectedProfile] });
    },
  });

  function handleProfileSelect(profileName: string) {
    setSelectedProfile(profileName);
    setSelectedTermId(null);
    resetMutations();
  }

  function resetMutations() {
    createProfileMutation.reset();
    updateProfileMutation.reset();
    deleteProfileMutation.reset();
    createTermMutation.reset();
    updateTermMutation.reset();
    deleteTermMutation.reset();
    createAliasMutation.reset();
    updateAliasMutation.reset();
    deleteAliasMutation.reset();
  }

  async function handleCreateProfile(payload: ProfileCreateRequest) {
    await createProfileMutation.mutateAsync(payload);
  }

  async function handleUpdateProfile(profileName: string, payload: ProfileUpdateRequest) {
    await updateProfileMutation.mutateAsync({ profileName, payload });
  }

  async function handleDeleteProfile(profileName: string) {
    await deleteProfileMutation.mutateAsync(profileName);
  }

  async function handleCreateTerm(payload: TermCreateRequest) {
    await createTermMutation.mutateAsync(payload);
  }

  async function handleUpdateTerm(term: CanonicalTerm, payload: TermUpdateRequest) {
    await updateTermMutation.mutateAsync({ term, payload });
  }

  async function handleDeleteTerm(term: CanonicalTerm) {
    await deleteTermMutation.mutateAsync(term);
  }

  async function handleCreateAlias(payload: AliasCreateRequest) {
    await createAliasMutation.mutateAsync(payload);
  }

  async function handleUpdateAlias(alias: TermAlias, payload: AliasUpdateRequest) {
    await updateAliasMutation.mutateAsync({ alias, payload });
  }

  async function handleDeleteAlias(alias: TermAlias) {
    await deleteAliasMutation.mutateAsync(alias);
  }

  function handleTermSelect(termId: number) {
    setSelectedTermId(termId);
    createAliasMutation.reset();
    updateAliasMutation.reset();
    deleteAliasMutation.reset();
    updateTermMutation.reset();
    deleteTermMutation.reset();
  }

  return (
    <div className="space-y-6">
      <section className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Profiles</CardTitle>
            <CardDescription>Terminology namespaces.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">{profilesQuery.data?.length ?? 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Canonical terms</CardTitle>
            <CardDescription>Typed entities in the selected profile.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">{termsQuery.data?.length ?? 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Runtime model</CardTitle>
            <CardDescription>Snapshot-based extraction path.</CardDescription>
          </CardHeader>
          <CardContent>
            <Badge>Postgres → Snapshot → Aho-Corasick</Badge>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="space-y-6">
          <ProfileManager
            createErrorMessage={errorMessage(createProfileMutation.error)}
            deleteErrorMessage={errorMessage(deleteProfileMutation.error)}
            isCreating={createProfileMutation.isPending}
            isDeleting={deleteProfileMutation.isPending}
            isUpdating={updateProfileMutation.isPending}
            loading={profilesQuery.isLoading}
            loadErrorMessage={profilesQuery.isError ? profilesQuery.error.message : null}
            disabled={!permissions.canManageProfiles}
            readOnlyMessage={permissions.canManageProfiles ? null : "Only admins can create, rename, or delete terminology profiles."}
            onCreateProfile={handleCreateProfile}
            onDeleteProfile={handleDeleteProfile}
            onSelectProfile={handleProfileSelect}
            onUpdateProfile={handleUpdateProfile}
            profiles={profilesQuery.data ?? []}
            selectedProfileName={selectedProfile}
            updateErrorMessage={errorMessage(updateProfileMutation.error)}
          />

          <AddTermForm
            disabled={!selectedProfile || !permissions.canManageTerms}
            errorMessage={errorMessage(createTermMutation.error)}
            isSubmitting={createTermMutation.isPending}
            readOnlyMessage={permissions.canManageTerms ? null : "Your role can inspect terms, but cannot create canonical terms."}
            onSubmit={handleCreateTerm}
          />

          {termsQuery.isError ? (
            <ErrorMessage message={termsQuery.error.message} />
          ) : termsQuery.isLoading && selectedProfile ? (
            <Card>
              <CardContent>
                <p className="text-sm text-slate-500 dark:text-slate-400">Loading terms...</p>
              </CardContent>
            </Card>
          ) : (
            <TermsTable onSelectTerm={(term) => handleTermSelect(term.id)} selectedTermId={selectedTermId} terms={termsQuery.data ?? []} />
          )}
        </div>

        <div className="space-y-6">
          <TermDetailsPanel
            aliasErrorMessage={errorMessage(updateAliasMutation.error) ?? errorMessage(deleteAliasMutation.error)}
            errorMessage={errorMessage(createAliasMutation.error)}
            isAddingAlias={createAliasMutation.isPending}
            isDeletingAlias={deleteAliasMutation.isPending}
            isDeletingTerm={deleteTermMutation.isPending}
            isUpdatingAlias={updateAliasMutation.isPending}
            isUpdatingTerm={updateTermMutation.isPending}
            canManageAliases={permissions.canManageAliases}
            canManageTerm={permissions.canManageTerms}
            onAddAlias={handleCreateAlias}
            onDeleteAlias={handleDeleteAlias}
            onDeleteTerm={handleDeleteTerm}
            onUpdateAlias={handleUpdateAlias}
            onUpdateTerm={handleUpdateTerm}
            term={selectedTerm}
            termErrorMessage={errorMessage(updateTermMutation.error) ?? errorMessage(deleteTermMutation.error)}
          />
          <SnapshotPanel disabled={!permissions.canExportSnapshots} profileName={selectedProfile} readOnlyMessage={permissions.canExportSnapshots ? null : "Snapshot export requires an admin or moderator role."} />
        </div>
      </section>
    </div>
  );
}

function ErrorMessage({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200">
      <AlertCircle className="mt-0.5 h-4 w-4" />
      <div>
        <div className="font-medium">Unable to load governance data</div>
        <div className="mt-1">{message}</div>
      </div>
    </div>
  );
}

function errorMessage(error: unknown) {
  if (!error) {
    return null;
  }
  return error instanceof Error ? error.message : "Request failed. Check the governance API and try again.";
}
