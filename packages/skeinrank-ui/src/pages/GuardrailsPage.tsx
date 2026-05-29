import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useMemo, useState } from "react";
import { Ban, Globe2, Layers3, ShieldCheck } from "lucide-react";

import { LEGACY_WRITE_TOOLS_LOCKED_MESSAGE } from "../config";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import {
  ConsolePage,
  EntityDetailPanel,
  MasterDetailLayout,
  MetricPill,
  SectionCard,
  WorkspaceHeader,
} from "../components/layout/ConsolePrimitives";
import {
  createGlobalStopListEntry,
  createStopListEntry,
  deleteGlobalStopListEntry,
  deleteStopListEntry,
  listGlobalStopList,
  listProfiles,
  listStopList,
  updateGlobalStopListEntry,
  updateStopListEntry,
} from "../lib/api";
import { permissionsForUser } from "../permissions";
import type {
  AuthUser,
  GlobalStopListCreateRequest,
  GlobalStopListEntry,
  GlobalStopListUpdateRequest,
  Profile,
  StopListCreateRequest,
  StopListEntry,
  StopListTarget,
  StopListUpdateRequest,
} from "../types";

const stopListTargets: StopListTarget[] = ["alias", "canonical", "both"];

type StopListEntryLike = GlobalStopListEntry | StopListEntry;
type GuardrailSection = "global" | "profile";

export function GuardrailsPage({ currentUser }: { currentUser: AuthUser }) {
  const permissions = permissionsForUser(currentUser);
  const queryClient = useQueryClient();
  const profilesQuery = useQuery({
    queryKey: ["profiles"],
    queryFn: listProfiles,
  });
  const globalStopListQuery = useQuery({
    queryKey: ["global-stop-list"],
    queryFn: listGlobalStopList,
    enabled: permissions.canReadStopLists,
  });
  const [selectedProfile, setSelectedProfile] = useState<string | null>(null);
  const [selectedEntryId, setSelectedEntryId] = useState<number | null>(null);
  const [selectedGlobalEntryId, setSelectedGlobalEntryId] = useState<
    number | null
  >(null);
  const [activeSection, setActiveSection] =
    useState<GuardrailSection>("global");

  useEffect(() => {
    if (!profilesQuery.data || profilesQuery.data.length === 0) {
      setSelectedProfile(null);
      setSelectedEntryId(null);
      return;
    }

    if (
      !selectedProfile ||
      !profilesQuery.data.some((profile) => profile.name === selectedProfile)
    ) {
      setSelectedProfile(profilesQuery.data[0].name);
      setSelectedEntryId(null);
    }
  }, [profilesQuery.data, selectedProfile]);

  useEffect(() => {
    if (!globalStopListQuery.data || globalStopListQuery.data.length === 0) {
      setSelectedGlobalEntryId(null);
      return;
    }
    if (
      !selectedGlobalEntryId ||
      !globalStopListQuery.data.some(
        (entry) => entry.id === selectedGlobalEntryId,
      )
    ) {
      setSelectedGlobalEntryId(globalStopListQuery.data[0].id);
    }
  }, [globalStopListQuery.data, selectedGlobalEntryId]);

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
    if (
      !selectedEntryId ||
      !stopListQuery.data.some((entry) => entry.id === selectedEntryId)
    ) {
      setSelectedEntryId(stopListQuery.data[0].id);
    }
  }, [selectedEntryId, stopListQuery.data]);

  const selectedEntry = useMemo(() => {
    if (!stopListQuery.data || !selectedEntryId) {
      return null;
    }
    return (
      stopListQuery.data.find((entry) => entry.id === selectedEntryId) ?? null
    );
  }, [selectedEntryId, stopListQuery.data]);

  const selectedGlobalEntry = useMemo(() => {
    if (!globalStopListQuery.data || !selectedGlobalEntryId) {
      return null;
    }
    return (
      globalStopListQuery.data.find(
        (entry) => entry.id === selectedGlobalEntryId,
      ) ?? null
    );
  }, [globalStopListQuery.data, selectedGlobalEntryId]);

  const activeGlobalEntries = useMemo(
    () => (globalStopListQuery.data ?? []).filter((entry) => entry.is_active),
    [globalStopListQuery.data],
  );

  const createGlobalMutation = useMutation({
    mutationFn: (payload: GlobalStopListCreateRequest) =>
      createGlobalStopListEntry(payload),
    onSuccess: (entry) => {
      setSelectedGlobalEntryId(entry.id);
      upsertGlobalStopListEntry(queryClient, entry);
      void queryClient.invalidateQueries({ queryKey: ["global-stop-list"] });
    },
  });

  const updateGlobalMutation = useMutation({
    mutationFn: ({
      entryId,
      payload,
    }: {
      entryId: number;
      payload: GlobalStopListUpdateRequest;
    }) => updateGlobalStopListEntry(entryId, payload),
    onSuccess: (entry) => {
      setSelectedGlobalEntryId(entry.id);
      upsertGlobalStopListEntry(queryClient, entry);
      void queryClient.invalidateQueries({ queryKey: ["global-stop-list"] });
    },
  });

  const deleteGlobalMutation = useMutation({
    mutationFn: (entryId: number) => deleteGlobalStopListEntry(entryId),
    onSuccess: (_result, entryId) => {
      setSelectedGlobalEntryId(null);
      removeGlobalStopListEntry(queryClient, entryId);
      void queryClient.invalidateQueries({ queryKey: ["global-stop-list"] });
    },
  });

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
      void queryClient.invalidateQueries({
        queryKey: ["stop-list", selectedProfile],
      });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({
      entryId,
      payload,
    }: {
      entryId: number;
      payload: StopListUpdateRequest;
    }) => {
      if (!selectedProfile) {
        throw new Error("Select a profile before updating a stop-list entry.");
      }
      return updateStopListEntry(selectedProfile, entryId, payload);
    },
    onSuccess: (entry) => {
      setSelectedEntryId(entry.id);
      upsertStopListEntry(queryClient, selectedProfile, entry);
      void queryClient.invalidateQueries({
        queryKey: ["stop-list", selectedProfile],
      });
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
      void queryClient.invalidateQueries({
        queryKey: ["stop-list", selectedProfile],
      });
    },
  });

  async function handleCreateGlobalEntry(payload: GlobalStopListCreateRequest) {
    await createGlobalMutation.mutateAsync(payload);
  }

  async function handleUpdateGlobalEntry(
    entryId: number,
    payload: GlobalStopListUpdateRequest,
  ) {
    await updateGlobalMutation.mutateAsync({ entryId, payload });
  }

  async function handleDeleteGlobalEntry(entryId: number) {
    await deleteGlobalMutation.mutateAsync(entryId);
  }

  async function handleCreateEntry(payload: StopListCreateRequest) {
    await createMutation.mutateAsync(payload);
  }

  async function handleUpdateEntry(
    entryId: number,
    payload: StopListUpdateRequest,
  ) {
    await updateMutation.mutateAsync({ entryId, payload });
  }

  async function handleDeleteEntry(entryId: number) {
    await deleteMutation.mutateAsync(entryId);
  }

  const globalEntries = globalStopListQuery.data ?? [];
  const profileEntries = stopListQuery.data ?? [];
  const activeGlobalCount = globalEntries.filter((entry) => entry.is_active).length;
  const activeProfileCount = profileEntries.filter((entry) => entry.is_active).length;
  return (
    <ConsolePage>
      <WorkspaceHeader
        actions={
          <Badge className="bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200">
            {permissions.canManageStopLists ? "Manage mode" : "Read-only"}
          </Badge>
        }
        description="Govern noisy aliases and canonical values before they reach suggestions, dictionary imports, enrichment jobs, and runtime search context."
        eyebrow="Guardrails"
        meta={
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <MetricPill
              helper={`${activeGlobalCount} active`}
              icon={Globe2}
              label="Global rules"
              tone="violet"
              value={globalEntries.length}
            />
            <MetricPill
              helper={selectedProfile ?? "No profile selected"}
              icon={Layers3}
              label="Profile rules"
              tone="cyan"
              value={profileEntries.length}
            />
            <MetricPill
              helper="Applied before review and enrichment"
              icon={ShieldCheck}
              label="Active blocks"
              tone="emerald"
              value={activeGlobalCount + activeProfileCount}
            />
            <MetricPill
              helper="Global entries inherited by profiles"
              icon={Ban}
              label="Inherited"
              tone="amber"
              value={activeGlobalEntries.length}
            />
          </div>
        }
        title="Stop-list governance workspace"
      />

      <GuardrailsScopeTabs
        activeSection={activeSection}
        globalCount={globalEntries.length}
        onSelectSection={setActiveSection}
        profileCount={profileEntries.length}
        selectedProfile={selectedProfile}
      />

      {activeSection === "global" ? (
        <MasterDetailLayout asideWidthClassName="xl:grid-cols-[minmax(0,1fr)_400px] 2xl:grid-cols-[minmax(0,1fr)_440px]">
          <div className="space-y-4">
            <GlobalStopListTable
              entries={globalEntries}
              isLoading={globalStopListQuery.isLoading}
              loadErrorMessage={
                globalStopListQuery.isError
                  ? globalStopListQuery.error.message
                  : null
              }
              onSelectEntry={(entry) => {
                setSelectedGlobalEntryId(entry.id);
                updateGlobalMutation.reset();
                deleteGlobalMutation.reset();
              }}
              selectedEntryId={selectedGlobalEntryId}
            />

            <CreateGlobalStopListEntryForm
              disabled={!permissions.canManageStopLists}
              errorMessage={errorMessage(createGlobalMutation.error)}
              isSubmitting={createGlobalMutation.isPending}
              onSubmit={handleCreateGlobalEntry}
              readOnlyMessage={
                permissions.canManageStopLists
                  ? null
                  : LEGACY_WRITE_TOOLS_LOCKED_MESSAGE
              }
            />
          </div>

          <GlobalStopListEntryDetailsPanel
            canManage={permissions.canManageStopLists}
            deleteErrorMessage={errorMessage(deleteGlobalMutation.error)}
            entry={selectedGlobalEntry}
            isDeleting={deleteGlobalMutation.isPending}
            isUpdating={updateGlobalMutation.isPending}
            onDelete={handleDeleteGlobalEntry}
            onUpdate={handleUpdateGlobalEntry}
            updateErrorMessage={errorMessage(updateGlobalMutation.error)}
          />
        </MasterDetailLayout>
      ) : (
        <MasterDetailLayout asideWidthClassName="xl:grid-cols-[minmax(0,1fr)_400px] 2xl:grid-cols-[minmax(0,1fr)_440px]">
          <div className="space-y-4">
            <ProfileScopeToolbar
              isLoading={profilesQuery.isLoading}
              loadErrorMessage={
                profilesQuery.isError ? profilesQuery.error.message : null
              }
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

            <InheritedGlobalStopListPanel entries={activeGlobalEntries} />

            <StopListTable
              entries={profileEntries}
              isLoading={stopListQuery.isLoading && Boolean(selectedProfile)}
              loadErrorMessage={
                stopListQuery.isError ? stopListQuery.error.message : null
              }
              onSelectEntry={(entry) => {
                setSelectedEntryId(entry.id);
                updateMutation.reset();
                deleteMutation.reset();
              }}
              selectedEntryId={selectedEntryId}
            />

            <CreateStopListEntryForm
              disabled={!selectedProfile || !permissions.canManageStopLists}
              errorMessage={errorMessage(createMutation.error)}
              globalEntries={activeGlobalEntries}
              isSubmitting={createMutation.isPending}
              onSubmit={handleCreateEntry}
              readOnlyMessage={
                permissions.canManageStopLists
                  ? null
                  : LEGACY_WRITE_TOOLS_LOCKED_MESSAGE
              }
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
        </MasterDetailLayout>
      )}
    </ConsolePage>
  );
}
function GuardrailsScopeTabs({
  activeSection,
  globalCount,
  onSelectSection,
  profileCount,
  selectedProfile,
}: {
  activeSection: GuardrailSection;
  globalCount: number;
  onSelectSection: (section: GuardrailSection) => void;
  profileCount: number;
  selectedProfile: string | null;
}) {
  return (
    <SectionCard
      actions={
        <div
          aria-label="Guardrail scope"
          className="inline-flex w-full rounded-2xl border border-slate-200 bg-slate-50 p-1 dark:border-slate-800 dark:bg-slate-900 sm:w-auto"
          role="tablist"
        >
          <GuardrailTabButton
            isActive={activeSection === "global"}
            label="Global"
            meta={`${globalCount} entries`}
            onClick={() => onSelectSection("global")}
          />
          <GuardrailTabButton
            isActive={activeSection === "profile"}
            label="Profile"
            meta={selectedProfile ? `${selectedProfile} · ${profileCount}` : "No profile"}
            onClick={() => onSelectSection("profile")}
          />
        </div>
      }
      description="Switch between organization-wide blocked values and profile-local guardrails inherited by runtime workflows."
      title="Stop-list scope"
    />
  );
}

function GuardrailTabButton({
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
      className={`flex min-w-0 flex-1 flex-col rounded-xl px-4 py-2 text-left transition-colors lg:min-w-36 lg:flex-none ${
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

function ProfileScopeToolbar({
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
    <SectionCard
      description="Choose which terminology profile receives local stop-list rules."
      title="Profile scope"
    >
      <div className="space-y-4">
        {loadErrorMessage ? <InlineError message={loadErrorMessage} /> : null}
        {isLoading ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Loading profiles...
          </p>
        ) : null}
        {profiles.length > 0 ? (
          <div className="space-y-2">
            <div className="text-sm font-medium text-slate-700 dark:text-slate-200">
              Profile
            </div>
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
            No profiles found. Create a terminology profile before adding
            profile stop-list guardrails.
          </p>
        )}
      </div>
    </SectionCard>
  );
}

function CreateGlobalStopListEntryForm({
  disabled = false,
  errorMessage,
  isSubmitting = false,
  onSubmit,
  readOnlyMessage,
}: {
  disabled?: boolean;
  errorMessage?: string | null;
  isSubmitting?: boolean;
  onSubmit: (payload: GlobalStopListCreateRequest) => Promise<void> | void;
  readOnlyMessage?: string | null;
}) {
  const [value, setValue] = useState("");
  const [target, setTarget] = useState<StopListTarget>("both");
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
      setTarget("both");
      setReason("");
    } catch {
      // Parent mutation owns user-facing error rendering.
    }
  }

  return (
    <SectionCard
      description="Block noisy values across every profile, suggestion, dry-run, and enrichment job."
      title="Add global stop-list entry"
    >
        {readOnlyMessage ? (
          <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
            {readOnlyMessage}
          </div>
        ) : null}
        <form className="space-y-4" onSubmit={handleSubmit}>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
                Global blocked value
              </span>
              <Input
                disabled={disabled || isSubmitting}
                onChange={(event) => setValue(event.target.value)}
                placeholder="unknown"
                value={value}
              />
            </label>
            <label className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
                Global target
              </span>
              <StopListTargetSelect
                disabled={disabled || isSubmitting}
                onChange={setTarget}
                value={target}
              />
            </label>
          </div>
          <label className="block space-y-1.5">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
              Global reason
            </span>
            <Input
              disabled={disabled || isSubmitting}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Too generic across all profiles"
              value={reason}
            />
          </label>
          {errorMessage ? <InlineError message={errorMessage} /> : null}
          <Button disabled={!canSubmit} type="submit">
            {isSubmitting ? "Adding..." : "Add to global stop list"}
          </Button>
        </form>
    </SectionCard>
  );
}

function CreateStopListEntryForm({
  disabled = false,
  errorMessage,
  globalEntries,
  isSubmitting = false,
  onSubmit,
  readOnlyMessage,
}: {
  disabled?: boolean;
  errorMessage?: string | null;
  globalEntries: GlobalStopListEntry[];
  isSubmitting?: boolean;
  onSubmit: (payload: StopListCreateRequest) => Promise<void> | void;
  readOnlyMessage?: string | null;
}) {
  const [value, setValue] = useState("");
  const [target, setTarget] = useState<StopListTarget>("alias");
  const [reason, setReason] = useState("");
  const inheritedMatch = findInheritedGlobalMatch(globalEntries, value, target);
  const canSubmit =
    !disabled && value.trim().length > 0 && !inheritedMatch && !isSubmitting;

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
    <SectionCard
      description="Block exact values that are too generic, ambiguous, or unsafe for the selected profile."
      title="Add profile stop-list entry"
    >
        {readOnlyMessage ? (
          <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
            {readOnlyMessage}
          </div>
        ) : null}
        <form className="space-y-4" onSubmit={handleSubmit}>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
                Blocked value
              </span>
              <Input
                disabled={disabled || isSubmitting}
                onChange={(event) => setValue(event.target.value)}
                placeholder="service"
                value={value}
              />
            </label>
            <label className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
                Target
              </span>
              <StopListTargetSelect
                disabled={disabled || isSubmitting}
                onChange={setTarget}
                value={target}
              />
            </label>
          </div>
          {inheritedMatch ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
              This value is already blocked globally as{" "}
              <span className="font-medium">{inheritedMatch.target}</span>.
              Manage it in the Global stop list instead of duplicating it
              locally.
            </div>
          ) : null}
          <label className="block space-y-1.5">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
              Reason
            </span>
            <Input
              disabled={disabled || isSubmitting}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Too generic for incident search"
              value={reason}
            />
          </label>
          {errorMessage ? <InlineError message={errorMessage} /> : null}
          <Button disabled={!canSubmit} type="submit">
            {isSubmitting ? "Adding..." : "Add to stop list"}
          </Button>
        </form>
    </SectionCard>
  );
}

function GlobalStopListTable({
  entries,
  isLoading,
  loadErrorMessage,
  onSelectEntry,
  selectedEntryId,
}: {
  entries: GlobalStopListEntry[];
  isLoading: boolean;
  loadErrorMessage?: string | null;
  onSelectEntry: (entry: GlobalStopListEntry) => void;
  selectedEntryId: number | null;
}) {
  return (
    <StopListTableBase
      description="Values inherited by every profile and enforced before profile-local stop lists."
      emptyMessage="No global stop-list entries yet."
      entries={entries}
      isGlobal
      isLoading={isLoading}
      loadErrorMessage={loadErrorMessage}
      onSelectEntry={onSelectEntry}
      selectedEntryId={selectedEntryId}
      title="Global stop list"
    />
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
    <StopListTableBase
      description="Local values blocked from direct edits, suggestions, and approvals for the selected profile."
      emptyMessage="No profile stop-list entries yet."
      entries={entries}
      isLoading={isLoading}
      loadErrorMessage={loadErrorMessage}
      onSelectEntry={onSelectEntry}
      selectedEntryId={selectedEntryId}
      title="Profile stop list"
    />
  );
}

function StopListTableBase<TEntry extends StopListEntryLike>({
  description,
  emptyMessage,
  entries,
  isGlobal = false,
  isLoading,
  loadErrorMessage,
  onSelectEntry,
  selectedEntryId,
  title,
}: {
  description: string;
  emptyMessage: string;
  entries: TEntry[];
  isGlobal?: boolean;
  isLoading: boolean;
  loadErrorMessage?: string | null;
  onSelectEntry: (entry: TEntry) => void;
  selectedEntryId: number | null;
  title: string;
}) {
  const activeEntries = entries.filter((entry) => entry.is_active).length;

  return (
    <SectionCard
      actions={
        <div className="flex flex-wrap items-center gap-2">
          {isGlobal ? <GlobalBadge /> : <Badge>Profile</Badge>}
          <Badge className="bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            {activeEntries}/{entries.length} active
          </Badge>
        </div>
      }
      contentClassName="p-0"
      description={description}
      title={title}
    >
      {loadErrorMessage ? (
        <div className="p-5">
          <InlineError message={loadErrorMessage} />
        </div>
      ) : null}
      {isLoading ? (
        <p className="p-5 text-sm text-slate-500 dark:text-slate-400">
          Loading stop-list entries...
        </p>
      ) : null}
      <div className="max-h-[520px] overflow-auto">
        <table className="w-full border-collapse text-left text-sm">
          <thead className="sticky top-0 z-10 bg-slate-50 text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-950 dark:text-slate-400">
            <tr>
              <th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">
                Value
              </th>
              <th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">
                Scope
              </th>
              <th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">
                Target
              </th>
              <th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">
                Status
              </th>
              <th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">
                Reason
              </th>
            </tr>
          </thead>
          <tbody>
            {entries.length === 0 ? (
              <tr>
                <td
                  className="px-5 py-8 text-center text-sm text-slate-500 dark:text-slate-400"
                  colSpan={5}
                >
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              entries.map((entry) => (
                <tr
                  className={`cursor-pointer transition-colors ${
                    selectedEntryId === entry.id
                      ? "bg-cyan-50/80 dark:bg-cyan-500/10"
                      : "hover:bg-slate-50 dark:hover:bg-slate-900"
                  }`}
                  key={entry.id}
                  onClick={() => onSelectEntry(entry)}
                >
                  <td className="border-b border-slate-100 px-5 py-4 dark:border-slate-800">
                    <div className="font-medium text-slate-950 dark:text-slate-50">
                      {entry.value}
                    </div>
                    <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                      {entry.normalized_value}
                    </div>
                  </td>
                  <td className="border-b border-slate-100 px-5 py-4 dark:border-slate-800">
                    {isGlobal ? <GlobalBadge /> : <Badge>Profile</Badge>}
                  </td>
                  <td className="border-b border-slate-100 px-5 py-4 dark:border-slate-800">
                    <StopListTargetBadge target={entry.target} />
                  </td>
                  <td className="border-b border-slate-100 px-5 py-4 dark:border-slate-800">
                    <StopListStatusBadge isActive={entry.is_active} />
                  </td>
                  <td className="max-w-[360px] border-b border-slate-100 px-5 py-4 text-slate-600 dark:border-slate-800 dark:text-slate-300">
                    <span className="line-clamp-2">{entry.reason || "—"}</span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </SectionCard>
  );
}

function InheritedGlobalStopListPanel({
  entries,
}: {
  entries: GlobalStopListEntry[];
}) {
  const sortedEntries = [...entries].sort(sortStopListEntries);

  return (
    <SectionCard
      actions={<GlobalBadge />}
      description="Read-only global entries applied before the selected profile's local stop list."
      title="Inherited global stop list"
    >
      {sortedEntries.length === 0 ? (
        <p className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
          No active global stop-list entries are inherited by this profile.
        </p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {sortedEntries.map((entry) => (
            <div
              className="flex items-center gap-2 rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-sm text-indigo-800 dark:border-indigo-900/60 dark:bg-indigo-950/40 dark:text-indigo-200"
              key={entry.id}
              title={entry.reason ?? undefined}
            >
              <span className="font-medium">{entry.value}</span>
              <span className="text-indigo-500 dark:text-indigo-300">·</span>
              <span>{entry.target}</span>
              <span className="rounded-full bg-white/70 px-2 py-0.5 text-xs font-medium uppercase tracking-wide text-indigo-700 dark:bg-indigo-900/70 dark:text-indigo-200">
                Global
              </span>
            </div>
          ))}
        </div>
      )}
    </SectionCard>
  );
}

function GlobalStopListEntryDetailsPanel({
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
  entry: GlobalStopListEntry | null;
  isDeleting?: boolean;
  isUpdating?: boolean;
  onDelete: (entryId: number) => Promise<void> | void;
  onUpdate: (
    entryId: number,
    payload: GlobalStopListUpdateRequest,
  ) => Promise<void> | void;
  updateErrorMessage?: string | null;
}) {
  const [value, setValue] = useState("");
  const [target, setTarget] = useState<StopListTarget>("both");
  const [reason, setReason] = useState("");
  const [isActive, setIsActive] = useState(true);

  useEffect(() => {
    setValue(entry?.value ?? "");
    setTarget(entry?.target ?? "both");
    setReason(entry?.reason ?? "");
    setIsActive(entry?.is_active ?? true);
  }, [entry?.id, entry?.is_active, entry?.reason, entry?.target, entry?.value]);

  if (!entry) {
    return (
      <EntityDetailPanel
        badge={<GlobalBadge />}
        description="Select a global entry to edit target, reason, or active status."
        title="Global stop-list details"
      >
        <p className="text-sm text-slate-500 dark:text-slate-400">
          No global stop-list entry selected.
        </p>
      </EntityDetailPanel>
    );
  }

  const canSave =
    canManage && value.trim().length > 0 && !isUpdating && !isDeleting;

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
    if (!window.confirm(`Delete global stop-list entry ${entry.value}?`)) {
      return;
    }
    await onDelete(entry.id);
  }

  return (
    <EntityDetailPanel
      badge={
        <div className="flex flex-wrap justify-end gap-2">
          <GlobalBadge />
          <StopListStatusBadge isActive={entry.is_active} />
        </div>
      }
      description="Global guardrail inherited by every profile."
      title={entry.value}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <InfoTile label="Scope" value="Global" />
        <InfoTile label="Target" value={entry.target} />
        <InfoTile label="Status" value={entry.is_active ? "active" : "disabled"} />
        <InfoTile label="Normalized" value={entry.normalized_value} />
      </div>
      {!canManage ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
          Legacy guardrail writes are locked. Change stop-list policy through proposals, GitOps/API runbooks, and snapshot rollout.
        </div>
      ) : null}
      <form className="space-y-4" onSubmit={handleSubmit}>
        <label className="space-y-1.5">
          <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
            Edit global blocked value
          </span>
          <Input
            disabled={!canManage || isUpdating || isDeleting}
            onChange={(event) => setValue(event.target.value)}
            value={value}
          />
        </label>
        <label className="space-y-1.5">
          <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
            Edit global target
          </span>
          <StopListTargetSelect
            disabled={!canManage || isUpdating || isDeleting}
            onChange={setTarget}
            value={target}
          />
        </label>
        <label className="space-y-1.5">
          <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
            Edit global reason
          </span>
          <Input
            disabled={!canManage || isUpdating || isDeleting}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Optional reason"
            value={reason}
          />
        </label>
        <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
          <input
            checked={isActive}
            disabled={!canManage || isUpdating || isDeleting}
            onChange={(event) => setIsActive(event.target.checked)}
            type="checkbox"
          />
          Active global guardrail
        </label>
        {updateErrorMessage ? <InlineError message={updateErrorMessage} /> : null}
        {deleteErrorMessage ? <InlineError message={deleteErrorMessage} /> : null}
        <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-4 dark:border-slate-800">
          <Button disabled={!canSave} type="submit">
            {isUpdating ? "Saving..." : "Save global stop-list entry"}
          </Button>
          <Button
            disabled={!canManage || isUpdating || isDeleting}
            onClick={handleDelete}
            type="button"
            variant="secondary"
          >
            {isDeleting ? "Deleting..." : "Delete global stop-list entry"}
          </Button>
        </div>
      </form>
    </EntityDetailPanel>
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
  onUpdate: (
    entryId: number,
    payload: StopListUpdateRequest,
  ) => Promise<void> | void;
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
      <EntityDetailPanel
        badge={<Badge>Profile</Badge>}
        description="Select a local entry to edit target, reason, or active status."
        title="Profile stop-list details"
      >
        <p className="text-sm text-slate-500 dark:text-slate-400">
          No profile stop-list entry selected.
        </p>
      </EntityDetailPanel>
    );
  }

  const canSave =
    canManage && value.trim().length > 0 && !isUpdating && !isDeleting;

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
    <EntityDetailPanel
      badge={
        <div className="flex flex-wrap justify-end gap-2">
          <Badge>Profile</Badge>
          <StopListStatusBadge isActive={entry.is_active} />
        </div>
      }
      description={`Profile guardrail for ${entry.target} values.`}
      title={entry.value}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <InfoTile label="Scope" value="Profile" />
        <InfoTile label="Target" value={entry.target} />
        <InfoTile label="Status" value={entry.is_active ? "active" : "disabled"} />
        <InfoTile label="Normalized" value={entry.normalized_value} />
      </div>
      {!canManage ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
          Legacy guardrail writes are locked. Change stop-list policy through proposals, GitOps/API runbooks, and snapshot rollout.
        </div>
      ) : null}
      <form className="space-y-4" onSubmit={handleSubmit}>
        <label className="space-y-1.5">
          <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
            Edit blocked value
          </span>
          <Input
            disabled={!canManage || isUpdating || isDeleting}
            onChange={(event) => setValue(event.target.value)}
            value={value}
          />
        </label>
        <label className="space-y-1.5">
          <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
            Edit target
          </span>
          <StopListTargetSelect
            disabled={!canManage || isUpdating || isDeleting}
            onChange={setTarget}
            value={target}
          />
        </label>
        <label className="space-y-1.5">
          <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
            Edit reason
          </span>
          <Input
            disabled={!canManage || isUpdating || isDeleting}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Optional reason"
            value={reason}
          />
        </label>
        <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
          <input
            checked={isActive}
            disabled={!canManage || isUpdating || isDeleting}
            onChange={(event) => setIsActive(event.target.checked)}
            type="checkbox"
          />
          Active guardrail
        </label>
        {updateErrorMessage ? <InlineError message={updateErrorMessage} /> : null}
        {deleteErrorMessage ? <InlineError message={deleteErrorMessage} /> : null}
        <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-4 dark:border-slate-800">
          <Button disabled={!canSave} type="submit">
            {isUpdating ? "Saving..." : "Save stop-list entry"}
          </Button>
          <Button
            disabled={!canManage || isUpdating || isDeleting}
            onClick={handleDelete}
            type="button"
            variant="secondary"
          >
            {isDeleting ? "Deleting..." : "Delete stop-list entry"}
          </Button>
        </div>
      </form>
    </EntityDetailPanel>
  );
}

function StopListTargetSelect({
  disabled,
  onChange,
  value,
}: {
  disabled?: boolean;
  onChange: (target: StopListTarget) => void;
  value: StopListTarget;
}) {
  return (
    <select
      className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100 disabled:cursor-not-allowed disabled:bg-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:disabled:bg-slate-900 dark:focus:border-slate-500 dark:focus:ring-slate-800"
      disabled={disabled}
      onChange={(event) => onChange(event.target.value as StopListTarget)}
      value={value}
    >
      {stopListTargets.map((entryTarget) => (
        <option key={entryTarget} value={entryTarget}>
          {entryTarget}
        </option>
      ))}
    </select>
  );
}


function StopListTargetBadge({ target }: { target: StopListTarget }) {
  const className =
    target === "both"
      ? "bg-cyan-50 text-cyan-700 dark:bg-cyan-950 dark:text-cyan-200"
      : target === "alias"
        ? "bg-violet-50 text-violet-700 dark:bg-violet-950 dark:text-violet-200"
        : "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-200";

  return <Badge className={className}>{target}</Badge>;
}

function InfoTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-slate-100 bg-slate-50/70 p-3 dark:border-slate-800 dark:bg-slate-900/60">
      <div className="text-[0.65rem] font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">
        {label}
      </div>
      <div className="mt-1 truncate text-sm font-semibold text-slate-950 dark:text-slate-50">
        {value}
      </div>
    </div>
  );
}

function GlobalBadge() {
  return (
    <Badge className="bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-200">
      Global
    </Badge>
  );
}

function StopListStatusBadge({ isActive }: { isActive: boolean }) {
  return isActive ? (
    <Badge className="bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200">
      active
    </Badge>
  ) : (
    <Badge className="bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
      disabled
    </Badge>
  );
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
  return error instanceof Error
    ? error.message
    : "Request failed. Check the governance API and try again.";
}

function upsertGlobalStopListEntry(
  queryClient: ReturnType<typeof useQueryClient>,
  entry: GlobalStopListEntry,
) {
  queryClient.setQueryData<GlobalStopListEntry[]>(
    ["global-stop-list"],
    (entries = []) => {
      const withoutEntry = entries.filter((current) => current.id !== entry.id);
      return [entry, ...withoutEntry].sort(sortStopListEntries);
    },
  );
}

function removeGlobalStopListEntry(
  queryClient: ReturnType<typeof useQueryClient>,
  entryId: number,
) {
  queryClient.setQueryData<GlobalStopListEntry[]>(
    ["global-stop-list"],
    (entries = []) => entries.filter((entry) => entry.id !== entryId),
  );
}

function upsertStopListEntry(
  queryClient: ReturnType<typeof useQueryClient>,
  profileName: string | null,
  entry: StopListEntry,
) {
  queryClient.setQueryData<StopListEntry[]>(
    ["stop-list", profileName],
    (entries = []) => {
      const withoutEntry = entries.filter((current) => current.id !== entry.id);
      return [entry, ...withoutEntry].sort(sortStopListEntries);
    },
  );
}

function removeStopListEntry(
  queryClient: ReturnType<typeof useQueryClient>,
  profileName: string | null,
  entryId: number,
) {
  queryClient.setQueryData<StopListEntry[]>(
    ["stop-list", profileName],
    (entries = []) => entries.filter((entry) => entry.id !== entryId),
  );
}

function sortStopListEntries(
  left: StopListEntryLike,
  right: StopListEntryLike,
) {
  if (left.target !== right.target) {
    return left.target.localeCompare(right.target);
  }
  return left.normalized_value.localeCompare(right.normalized_value);
}

function findInheritedGlobalMatch(
  entries: GlobalStopListEntry[],
  value: string,
  target: StopListTarget,
) {
  const normalizedValue = normalizeForUi(value);
  if (!normalizedValue) {
    return null;
  }
  return (
    entries.find(
      (entry) =>
        entry.is_active &&
        entry.normalized_value === normalizedValue &&
        targetsOverlap(entry.target, target),
    ) ?? null
  );
}

function targetsOverlap(left: StopListTarget, right: StopListTarget) {
  return left === "both" || right === "both" || left === right;
}

function normalizeForUi(value: string) {
  return value.trim().toLowerCase();
}
