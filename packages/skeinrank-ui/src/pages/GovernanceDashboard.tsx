import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, PlusCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { LEGACY_WRITE_TOOLS_LOCKED_MESSAGE } from "../config";
import { AddTermForm } from "../components/AddTermForm";
import { ProfileManager } from "../components/ProfileManager";
import { TermDetailsPanel } from "../components/TermDetailsPanel";
import { TermsTable } from "../components/TermsTable";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import {
  ConsolePage,
  EntityDetailPanel,
  MasterDetailLayout,
  MetricPill,
  SectionCard,
  WorkspaceHeader,
} from "../components/layout/ConsolePrimitives";
import {
  createAlias,
  createProfile,
  createTerm,
  deleteAlias,
  deleteProfile,
  deleteTerm,
  findElasticsearchEvidence,
  listElasticsearchBindings,
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
  ElasticsearchEvidenceResponse,
  Profile,
  ProfileCreateRequest,
  ProfileUpdateRequest,
  TermAlias,
  TermCreateRequest,
  TermUpdateRequest,
  AuthUser,
} from "../types";

type TermsSection = "terms" | "profiles";

export function GovernanceDashboard({
  currentUser,
}: {
  currentUser: AuthUser;
}) {
  const permissions = permissionsForUser(currentUser);
  const queryClient = useQueryClient();
  const profilesQuery = useQuery({
    queryKey: ["profiles"],
    queryFn: listProfiles,
  });

  const [selectedProfile, setSelectedProfile] = useState<string | null>(null);
  const [selectedTermId, setSelectedTermId] = useState<number | null>(null);
  const [activeSection, setActiveSection] = useState<TermsSection>("terms");
  const [isAddTermOpen, setIsAddTermOpen] = useState(false);

  useEffect(() => {
    if (!profilesQuery.data || profilesQuery.data.length === 0) {
      setSelectedProfile(null);
      setSelectedTermId(null);
      return;
    }

    if (
      !selectedProfile ||
      !profilesQuery.data.some((profile) => profile.name === selectedProfile)
    ) {
      setSelectedProfile(profilesQuery.data[0].name);
      setSelectedTermId(null);
    }
  }, [profilesQuery.data, selectedProfile]);

  const termsQuery = useQuery({
    queryKey: ["terms", selectedProfile],
    queryFn: () => listTerms(selectedProfile ?? ""),
    enabled: Boolean(selectedProfile),
  });

  const bindingsQuery = useQuery({
    queryKey: ["elasticsearch", "bindings", selectedProfile],
    queryFn: () => listElasticsearchBindings(selectedProfile ?? ""),
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

    if (
      !selectedTermId ||
      !termsQuery.data.some((term) => term.id === selectedTermId)
    ) {
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
        if (
          profiles.some((currentProfile) => currentProfile.id === profile.id)
        ) {
          return profiles;
        }
        return [...profiles, profile].sort((left, right) =>
          left.normalized_name.localeCompare(right.normalized_name),
        );
      });
      queryClient.setQueryData(["terms", profile.name], []);
      void queryClient.invalidateQueries({ queryKey: ["profiles"] });
    },
  });

  const updateProfileMutation = useMutation({
    mutationFn: ({
      profileName,
      payload,
    }: {
      profileName: string;
      payload: ProfileUpdateRequest;
    }) => updateProfile(profileName, payload),
    onSuccess: (profile, variables) => {
      setSelectedProfile(profile.name);
      setSelectedTermId(null);
      queryClient.setQueryData(["profiles"], (currentProfiles = []) =>
        (currentProfiles as Profile[])
          .map((currentProfile) =>
            currentProfile.id === profile.id ? profile : currentProfile,
          )
          .sort((left, right) =>
            left.normalized_name.localeCompare(right.normalized_name),
          ),
      );
      if (variables.profileName !== profile.name) {
        queryClient.removeQueries({
          queryKey: ["terms", variables.profileName],
        });
      }
      void queryClient.invalidateQueries({ queryKey: ["profiles"] });
      void queryClient.invalidateQueries({ queryKey: ["terms", profile.name] });
    },
  });

  const deleteProfileMutation = useMutation({
    mutationFn: (profileName: string) => deleteProfile(profileName),
    onSuccess: (_result, profileName) => {
      queryClient.setQueryData(["profiles"], (currentProfiles = []) =>
        (currentProfiles as Array<{ name: string }>).filter(
          (profile) => profile.name !== profileName,
        ),
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
      setIsAddTermOpen(false);
      queryClient.setQueryData<CanonicalTerm[]>(
        ["terms", selectedProfile],
        (currentTerms = []) => {
          if (currentTerms.some((currentTerm) => currentTerm.id === term.id)) {
            return currentTerms;
          }
          return [...currentTerms, term];
        },
      );
      void queryClient.invalidateQueries({
        queryKey: ["terms", selectedProfile],
      });
    },
  });

  const updateTermMutation = useMutation({
    mutationFn: ({
      term,
      payload,
    }: {
      term: CanonicalTerm;
      payload: TermUpdateRequest;
    }) => {
      if (!selectedProfile) {
        throw new Error("Select a profile before updating a term.");
      }
      return updateTerm(selectedProfile, term.canonical_value, payload);
    },
    onSuccess: (term) => {
      setSelectedTermId(term.id);
      setIsAddTermOpen(false);
      queryClient.setQueryData<CanonicalTerm[]>(
        ["terms", selectedProfile],
        (currentTerms = []) =>
          currentTerms.map((currentTerm) =>
            currentTerm.id === term.id ? term : currentTerm,
          ),
      );
      void queryClient.invalidateQueries({
        queryKey: ["terms", selectedProfile],
      });
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
      queryClient.setQueryData<CanonicalTerm[]>(
        ["terms", selectedProfile],
        (currentTerms = []) =>
          currentTerms.filter((currentTerm) => currentTerm.id !== term.id),
      );
      void queryClient.invalidateQueries({
        queryKey: ["terms", selectedProfile],
      });
    },
  });

  const createAliasMutation = useMutation({
    mutationFn: (payload: AliasCreateRequest) => {
      if (!selectedProfile || !selectedTerm) {
        throw new Error("Select a canonical term before creating an alias.");
      }
      return createAlias(
        selectedProfile,
        selectedTerm.canonical_value,
        payload,
      );
    },
    onSuccess: (alias) => {
      queryClient.setQueryData<CanonicalTerm[]>(
        ["terms", selectedProfile],
        (currentTerms = []) =>
          currentTerms.map((term) => {
            if (
              term.id !== selectedTerm?.id ||
              term.aliases.some((currentAlias) => currentAlias.id === alias.id)
            ) {
              return term;
            }
            return { ...term, aliases: [...term.aliases, alias] };
          }),
      );
      void queryClient.invalidateQueries({
        queryKey: ["terms", selectedProfile],
      });
    },
  });

  const updateAliasMutation = useMutation({
    mutationFn: ({
      alias,
      payload,
    }: {
      alias: TermAlias;
      payload: AliasUpdateRequest;
    }) => {
      if (!selectedProfile || !selectedTerm) {
        throw new Error("Select a canonical term before updating an alias.");
      }
      return updateAlias(
        selectedProfile,
        selectedTerm.canonical_value,
        alias.id,
        payload,
      );
    },
    onSuccess: (alias) => {
      queryClient.setQueryData<CanonicalTerm[]>(
        ["terms", selectedProfile],
        (currentTerms = []) =>
          currentTerms.map((term) => {
            if (term.id !== selectedTerm?.id) {
              return term;
            }
            return {
              ...term,
              aliases: term.aliases.map((currentAlias) =>
                currentAlias.id === alias.id ? alias : currentAlias,
              ),
            };
          }),
      );
      void queryClient.invalidateQueries({
        queryKey: ["terms", selectedProfile],
      });
    },
  });

  const deleteAliasMutation = useMutation({
    mutationFn: (alias: TermAlias) => {
      if (!selectedProfile || !selectedTerm) {
        throw new Error("Select a canonical term before deleting an alias.");
      }
      return deleteAlias(
        selectedProfile,
        selectedTerm.canonical_value,
        alias.id,
      );
    },
    onSuccess: (_result, alias) => {
      queryClient.setQueryData<CanonicalTerm[]>(
        ["terms", selectedProfile],
        (currentTerms = []) =>
          currentTerms.map((term) => {
            if (term.id !== selectedTerm?.id) {
              return term;
            }
            return {
              ...term,
              aliases: term.aliases.filter(
                (currentAlias) => currentAlias.id !== alias.id,
              ),
            };
          }),
      );
      void queryClient.invalidateQueries({
        queryKey: ["terms", selectedProfile],
      });
    },
  });

  const evidenceMutation = useMutation({
    mutationFn: ({
      bindingId,
      canonicalValue,
      query,
    }: {
      bindingId: number;
      canonicalValue: string;
      query: string;
    }) =>
      findElasticsearchEvidence(bindingId, {
        canonical_value: canonicalValue,
        max_documents: 5,
        query,
      }),
  });

  async function handleCheckEvidence(
    term: CanonicalTerm,
    bindingId: number,
    query: string,
  ) {
    await evidenceMutation.mutateAsync({
      bindingId,
      canonicalValue: term.canonical_value,
      query,
    });
  }

  function handleProfileSelect(profileName: string) {
    setSelectedProfile(profileName);
    setSelectedTermId(null);
    setIsAddTermOpen(false);
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
    evidenceMutation.reset();
  }

  async function handleCreateProfile(payload: ProfileCreateRequest) {
    await createProfileMutation.mutateAsync(payload);
  }

  async function handleUpdateProfile(
    profileName: string,
    payload: ProfileUpdateRequest,
  ) {
    await updateProfileMutation.mutateAsync({ profileName, payload });
  }

  async function handleDeleteProfile(profileName: string) {
    await deleteProfileMutation.mutateAsync(profileName);
  }

  async function handleCreateTerm(payload: TermCreateRequest) {
    await createTermMutation.mutateAsync(payload);
  }

  async function handleUpdateTerm(
    term: CanonicalTerm,
    payload: TermUpdateRequest,
  ) {
    await updateTermMutation.mutateAsync({ term, payload });
  }

  async function handleDeleteTerm(term: CanonicalTerm) {
    await deleteTermMutation.mutateAsync(term);
  }

  async function handleCreateAlias(payload: AliasCreateRequest) {
    await createAliasMutation.mutateAsync(payload);
  }

  async function handleUpdateAlias(
    alias: TermAlias,
    payload: AliasUpdateRequest,
  ) {
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
    evidenceMutation.reset();
  }

  const selectedAliasCount = useMemo(
    () =>
      (termsQuery.data ?? []).reduce(
        (total, term) => total + term.aliases.length,
        0,
      ),
    [termsQuery.data],
  );

  return (
    <ConsolePage maxWidthClassName="max-w-[1560px]" className="space-y-4">
      <TerminologyWorkspaceHeader
        activeSection={activeSection}
        aliasCount={selectedAliasCount}
        onSelectSection={setActiveSection}
        profileCount={profilesQuery.data?.length ?? 0}
        selectedProfile={selectedProfile}
        termCount={termsQuery.data?.length ?? 0}
      />

      {!permissions.canManageTerms && !permissions.canManageProfiles ? <LegacyReadOnlyNotice /> : null}

      {activeSection === "profiles" ? (
        <MasterDetailLayout asideWidthClassName="xl:grid-cols-[minmax(0,1fr)_360px] 2xl:grid-cols-[minmax(0,1fr)_400px]">
          <ProfileManager
            createErrorMessage={errorMessage(createProfileMutation.error)}
            deleteErrorMessage={errorMessage(deleteProfileMutation.error)}
            isCreating={createProfileMutation.isPending}
            isDeleting={deleteProfileMutation.isPending}
            isUpdating={updateProfileMutation.isPending}
            loading={profilesQuery.isLoading}
            loadErrorMessage={
              profilesQuery.isError ? profilesQuery.error.message : null
            }
            disabled={!permissions.canManageProfiles}
            readOnlyMessage={
              permissions.canManageProfiles
                ? null
                : LEGACY_WRITE_TOOLS_LOCKED_MESSAGE
            }
            onCreateProfile={handleCreateProfile}
            onDeleteProfile={handleDeleteProfile}
            onSelectProfile={handleProfileSelect}
            onUpdateProfile={handleUpdateProfile}
            profiles={profilesQuery.data ?? []}
            selectedProfileName={selectedProfile}
            updateErrorMessage={errorMessage(updateProfileMutation.error)}
          />
          <EntityDetailPanel
            badge={<Badge>{profilesQuery.data?.length ?? 0} profiles</Badge>}
            description="Selected namespace health, bindings, and dictionary size."
            title="Profile contents"
          >
            <div className="grid gap-3 text-sm">
              <MetricRow
                label="Selected profile"
                value={selectedProfile ?? "—"}
              />
              <MetricRow
                label="Canonical terms"
                value={String(termsQuery.data?.length ?? 0)}
              />
              <MetricRow label="Aliases" value={String(selectedAliasCount)} />
              <MetricRow
                label="Bindings"
                value={String(bindingsQuery.data?.length ?? 0)}
              />
            </div>
          </EntityDetailPanel>
        </MasterDetailLayout>
      ) : (
        <MasterDetailLayout asideWidthClassName="xl:grid-cols-[minmax(0,1fr)_420px] 2xl:grid-cols-[minmax(0,1fr)_460px]">
          <div className="space-y-4">
            <TermsProfileToolbar
              bindingsCount={bindingsQuery.data?.length ?? 0}
              canManageTerms={
                Boolean(selectedProfile) && permissions.canManageTerms
              }
              isLoading={profilesQuery.isLoading}
              loadErrorMessage={
                profilesQuery.isError ? profilesQuery.error.message : null
              }
              onAddTerm={() => setIsAddTermOpen((current) => !current)}
              onSelectProfile={handleProfileSelect}
              profiles={profilesQuery.data ?? []}
              selectedProfile={selectedProfile}
              termsCount={termsQuery.data?.length ?? 0}
              isAddTermOpen={isAddTermOpen}
            />

            {isAddTermOpen ? (
              <AddTermForm
                disabled={!selectedProfile || !permissions.canManageTerms}
                errorMessage={errorMessage(createTermMutation.error)}
                isSubmitting={createTermMutation.isPending}
                readOnlyMessage={
                  permissions.canManageTerms
                    ? null
                    : LEGACY_WRITE_TOOLS_LOCKED_MESSAGE
                }
                onSubmit={handleCreateTerm}
              />
            ) : null}

            {termsQuery.isError ? (
              <ErrorMessage message={termsQuery.error.message} />
            ) : termsQuery.isLoading && selectedProfile ? (
              <SectionCard
                title="Canonical terms"
                description="Loading profile terms and aliases."
              >
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  Loading terms...
                </p>
              </SectionCard>
            ) : (
              <TermsTable
                onSelectTerm={(term) => handleTermSelect(term.id)}
                selectedTermId={selectedTermId}
                terms={termsQuery.data ?? []}
              />
            )}
          </div>

          <TermDetailsPanel
            aliasErrorMessage={
              errorMessage(updateAliasMutation.error) ??
              errorMessage(deleteAliasMutation.error)
            }
            bindings={bindingsQuery.data ?? []}
            bindingsErrorMessage={
              bindingsQuery.isError ? bindingsQuery.error.message : null
            }
            bindingsLoading={
              bindingsQuery.isLoading && Boolean(selectedProfile)
            }
            evidence={
              evidenceMutation.data as ElasticsearchEvidenceResponse | undefined
            }
            evidenceErrorMessage={errorMessage(evidenceMutation.error)}
            errorMessage={errorMessage(createAliasMutation.error)}
            isAddingAlias={createAliasMutation.isPending}
            isDeletingAlias={deleteAliasMutation.isPending}
            isDeletingTerm={deleteTermMutation.isPending}
            isCheckingEvidence={evidenceMutation.isPending}
            isUpdatingAlias={updateAliasMutation.isPending}
            isUpdatingTerm={updateTermMutation.isPending}
            canManageAliases={permissions.canManageAliases}
            canManageTerm={permissions.canManageTerms}
            onAddAlias={handleCreateAlias}
            onDeleteAlias={handleDeleteAlias}
            onDeleteTerm={handleDeleteTerm}
            onCheckEvidence={handleCheckEvidence}
            onUpdateAlias={handleUpdateAlias}
            onUpdateTerm={handleUpdateTerm}
            term={selectedTerm}
            termErrorMessage={
              errorMessage(updateTermMutation.error) ??
              errorMessage(deleteTermMutation.error)
            }
          />
        </MasterDetailLayout>
      )}
    </ConsolePage>
  );
}


function LegacyReadOnlyNotice() {
  return (
    <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
      <div className="font-semibold">Legacy terminology editor is read-only</div>
      <p className="mt-1">{LEGACY_WRITE_TOOLS_LOCKED_MESSAGE}</p>
    </div>
  );
}

function TerminologyWorkspaceHeader({
  activeSection,
  aliasCount,
  onSelectSection,
  profileCount,
  selectedProfile,
  termCount,
}: {
  activeSection: TermsSection;
  aliasCount: number;
  onSelectSection: (section: TermsSection) => void;
  profileCount: number;
  selectedProfile: string | null;
  termCount: number;
}) {
  return (
    <WorkspaceHeader
      actions={
        <div
          aria-label="Terminology section"
          className="inline-flex w-full rounded-2xl border border-slate-200 bg-slate-50 p-1 dark:border-slate-800 dark:bg-slate-900 sm:w-auto"
          role="tablist"
        >
          <TermsTabButton
            isActive={activeSection === "terms"}
            label="Terms"
            meta={`${selectedProfile ?? "No profile"} · ${termCount} terms · ${aliasCount} aliases`}
            onClick={() => onSelectSection("terms")}
          />
          <TermsTabButton
            isActive={activeSection === "profiles"}
            label="Profiles"
            meta={`${profileCount} namespaces`}
            onClick={() => onSelectSection("profiles")}
          />
        </div>
      }
      description="Review canonical values, aliases, profile scope, and evidence without leaving the workspace."
      eyebrow="Terminology control plane"
      title="Governed terminology workspace"
    />
  );
}

function TermsTabButton({
  isActive,
  label,
  meta,
  onClick,
}: {
  isActive: boolean;
  label: string;
  meta: string;
  onClick: () => void;
}) {
  return (
    <button
      aria-selected={isActive}
      className={`flex min-w-0 flex-1 flex-col rounded-xl px-4 py-2 text-left transition-colors sm:min-w-44 sm:flex-none ${
        isActive
          ? "bg-white text-slate-950 shadow-sm dark:bg-slate-950 dark:text-slate-50"
          : "text-slate-500 hover:text-slate-950 dark:text-slate-400 dark:hover:text-slate-100"
      }`}
      onClick={onClick}
      role="tab"
      type="button"
    >
      <span className="text-sm font-semibold">{label}</span>
      <span className="mt-0.5 truncate text-xs text-slate-500 dark:text-slate-400">
        {meta}
      </span>
    </button>
  );
}

function TermsProfileToolbar({
  bindingsCount,
  canManageTerms,
  isAddTermOpen,
  isLoading,
  loadErrorMessage,
  onAddTerm,
  onSelectProfile,
  profiles,
  selectedProfile,
  termsCount,
}: {
  bindingsCount: number;
  canManageTerms: boolean;
  isAddTermOpen: boolean;
  isLoading: boolean;
  loadErrorMessage?: string | null;
  onAddTerm: () => void;
  onSelectProfile: (profileName: string) => void;
  profiles: Profile[];
  selectedProfile: string | null;
  termsCount: number;
}) {
  return (
    <SectionCard
      actions={
        <Button
          className="gap-2"
          disabled={!canManageTerms}
          onClick={onAddTerm}
          type="button"
          variant={isAddTermOpen ? "secondary" : "primary"}
        >
          <PlusCircle className="h-4 w-4" />
          {isAddTermOpen ? "Close term form" : "Add term"}
        </Button>
      }
      contentClassName="space-y-4"
      description="Select the namespace that will drive the terms table, details panel, and evidence checks."
      title="Profile scope"
    >
      {loadErrorMessage ? <InlineError message={loadErrorMessage} /> : null}
      <div className="grid gap-3 sm:grid-cols-3">
        <MetricPill
          helper="current namespace"
          label="Profile"
          value={selectedProfile ?? "—"}
        />
        <MetricPill
          helper="canonical values"
          label="Terms"
          tone="cyan"
          value={termsCount}
        />
        <MetricPill
          helper="runtime contexts"
          label="Bindings"
          tone="emerald"
          value={bindingsCount}
        />
      </div>
      {isLoading ? (
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Loading profiles...
        </p>
      ) : profiles.length > 0 ? (
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
      ) : (
        <p className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
          No profiles yet. Open the Profiles tab to create a terminology
          namespace.
        </p>
      )}
    </SectionCard>
  );
}

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-xl border border-slate-100 bg-slate-50/60 px-3 py-2 dark:border-slate-800 dark:bg-slate-900/60">
      <span className="text-slate-500 dark:text-slate-400">{label}</span>
      <span className="font-medium text-slate-950 dark:text-slate-50">
        {value}
      </span>
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
  return error instanceof Error
    ? error.message
    : "Request failed. Check the governance API and try again.";
}
