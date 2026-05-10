import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useMemo, useState } from "react";

import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";
import {
  cancelElasticsearchEnrichmentJob,
  createElasticsearchBinding,
  deleteElasticsearchBinding,
  dryRunElasticsearchBinding,
  getElasticsearchConnectionStatus,
  getElasticsearchEnrichmentJob,
  getElasticsearchIndexMapping,
  listElasticsearchBindings,
  listElasticsearchEnrichmentJobs,
  listElasticsearchIndices,
  listProfiles,
  startElasticsearchEnrichmentJob,
  updateElasticsearchBinding,
} from "../lib/api";
import { permissionsForUser } from "../permissions";
import type {
  AuthUser,
  ElasticsearchBinding,
  ElasticsearchBindingCreateRequest,
  ElasticsearchBindingDryRunResponse,
  ElasticsearchBindingMode,
  ElasticsearchBindingUpdateRequest,
  ElasticsearchBindingWriteStrategy,
  ElasticsearchEnrichmentJob,
  ElasticsearchEnrichmentJobCreateRequest,
  ElasticsearchConnectionStatus,
  ElasticsearchIndex,
  ElasticsearchMappingField,
  Profile,
} from "../types";

const bindingModes: ElasticsearchBindingMode[] = ["dry_run", "write"];
const bindingWriteStrategies: ElasticsearchBindingWriteStrategy[] = ["reindex_alias_swap", "in_place"];
const timeWindowOptions = [
  { label: "All documents", value: "all" },
  { label: "Last 30 days", value: "30" },
  { label: "Last 1 year", value: "365" },
  { label: "Last 5 years", value: "1825" },
  { label: "Custom days", value: "custom" },
] as const;

type TimeWindowValue = (typeof timeWindowOptions)[number]["value"];

type BindingDraft = {
  id?: number;
  profileName: string;
  indexName: string;
  filterField: string;
  filterValue: string;
};

type BindingValidation = {
  hasPartialFilter: boolean;
  isSharedIndex: boolean;
  missingDiscriminator: boolean;
  sharedProfiles: string[];
};

export function IntegrationsPage({ currentUser }: { currentUser: AuthUser }) {
  const permissions = permissionsForUser(currentUser);
  const queryClient = useQueryClient();
  const profilesQuery = useQuery({ queryKey: ["profiles"], queryFn: listProfiles });
  const [selectedProfile, setSelectedProfile] = useState<string | null>(null);
  const [selectedBindingId, setSelectedBindingId] = useState<number | null>(null);
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);

  useEffect(() => {
    if (!profilesQuery.data || profilesQuery.data.length === 0) {
      setSelectedProfile(null);
      setSelectedBindingId(null);
      setSelectedJobId(null);
      return;
    }

    if (!selectedProfile || !profilesQuery.data.some((profile) => profile.name === selectedProfile)) {
      setSelectedProfile(profilesQuery.data[0].name);
      setSelectedBindingId(null);
      setSelectedJobId(null);
    }
  }, [profilesQuery.data, selectedProfile]);

  const connectionQuery = useQuery({
    queryKey: ["elasticsearch", "connection-status"],
    queryFn: getElasticsearchConnectionStatus,
    enabled: permissions.canReadBindings,
  });

  const indicesQuery = useQuery({
    queryKey: ["elasticsearch", "indices"],
    queryFn: listElasticsearchIndices,
    enabled: permissions.canReadBindings && Boolean(connectionQuery.data?.ok),
  });

  const allBindingsQuery = useQuery({
    queryKey: ["elasticsearch-bindings", "all"],
    queryFn: () => listElasticsearchBindings(),
    enabled: permissions.canReadBindings,
  });

  const bindingsQuery = useQuery({
    queryKey: ["elasticsearch-bindings", selectedProfile],
    queryFn: () => listElasticsearchBindings(selectedProfile ?? undefined),
    enabled: permissions.canReadBindings && Boolean(selectedProfile),
  });

  useEffect(() => {
    if (!bindingsQuery.data || bindingsQuery.data.length === 0) {
      setSelectedBindingId(null);
      setSelectedJobId(null);
      return;
    }

    if (!selectedBindingId || !bindingsQuery.data.some((binding) => binding.id === selectedBindingId)) {
      setSelectedBindingId(bindingsQuery.data[0].id);
    }
  }, [bindingsQuery.data, selectedBindingId]);

  const selectedBinding = useMemo(() => {
    if (!bindingsQuery.data || !selectedBindingId) {
      return null;
    }
    return bindingsQuery.data.find((binding) => binding.id === selectedBindingId) ?? null;
  }, [bindingsQuery.data, selectedBindingId]);

  const jobsQuery = useQuery({
    queryKey: ["elasticsearch-enrichment-jobs", selectedBindingId],
    queryFn: () => listElasticsearchEnrichmentJobs(selectedBindingId ?? undefined),
    enabled: permissions.canReadBindings && Boolean(selectedBindingId),
  });

  useEffect(() => {
    if (!jobsQuery.data || jobsQuery.data.length === 0) {
      setSelectedJobId(null);
      return;
    }

    if (!selectedJobId || !jobsQuery.data.some((job) => job.id === selectedJobId)) {
      setSelectedJobId(jobsQuery.data[0].id);
    }
  }, [jobsQuery.data, selectedJobId]);

  const jobDetailsQuery = useQuery({
    queryKey: ["elasticsearch-enrichment-job", selectedJobId],
    queryFn: () => getElasticsearchEnrichmentJob(selectedJobId ?? 0),
    enabled: permissions.canReadBindings && Boolean(selectedJobId),
  });

  const createMutation = useMutation({
    mutationFn: (payload: ElasticsearchBindingCreateRequest) => createElasticsearchBinding(payload),
    onSuccess: (binding) => {
      setSelectedProfile(binding.profile_name);
      setSelectedBindingId(binding.id);
      setSelectedJobId(null);
      upsertElasticsearchBinding(queryClient, "all", binding);
      upsertElasticsearchBinding(queryClient, binding.profile_name, binding);
      void queryClient.invalidateQueries({ queryKey: ["elasticsearch-bindings"] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ bindingId, payload }: { bindingId: number; payload: ElasticsearchBindingUpdateRequest }) =>
      updateElasticsearchBinding(bindingId, payload),
    onSuccess: (binding) => {
      setSelectedProfile(binding.profile_name);
      setSelectedBindingId(binding.id);
      upsertElasticsearchBinding(queryClient, "all", binding);
      upsertElasticsearchBinding(queryClient, binding.profile_name, binding);
      void queryClient.invalidateQueries({ queryKey: ["elasticsearch-bindings"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (bindingId: number) => deleteElasticsearchBinding(bindingId),
    onSuccess: (_result, bindingId) => {
      setSelectedBindingId(null);
      setSelectedJobId(null);
      removeElasticsearchBinding(queryClient, "all", bindingId);
      removeElasticsearchBinding(queryClient, selectedProfile, bindingId);
      void queryClient.invalidateQueries({ queryKey: ["elasticsearch-bindings"] });
    },
  });

  const dryRunMutation = useMutation({
    mutationFn: (bindingId: number) => dryRunElasticsearchBinding(bindingId, { limit: 3 }),
  });

  const startJobMutation = useMutation({
    mutationFn: ({ bindingId, payload }: { bindingId: number; payload: ElasticsearchEnrichmentJobCreateRequest }) =>
      startElasticsearchEnrichmentJob(bindingId, payload),
    onSuccess: (job) => {
      setSelectedJobId(job.id);
      queryClient.setQueryData<ElasticsearchEnrichmentJob[]>(["elasticsearch-enrichment-jobs", job.binding_id], (jobs = []) => {
        const withoutJob = jobs.filter((current) => current.id !== job.id);
        return [job, ...withoutJob].sort(sortJobs);
      });
      queryClient.setQueryData(["elasticsearch-enrichment-job", job.id], job);
      void queryClient.invalidateQueries({ queryKey: ["elasticsearch-enrichment-jobs", job.binding_id] });
    },
  });

  const cancelJobMutation = useMutation({
    mutationFn: ({ jobId, reason }: { jobId: number; reason?: string }) =>
      cancelElasticsearchEnrichmentJob(jobId, reason ? { reason } : {}),
    onSuccess: (job) => {
      queryClient.setQueryData<ElasticsearchEnrichmentJob[]>(["elasticsearch-enrichment-jobs", job.binding_id], (jobs = []) => {
        const withoutJob = jobs.filter((current) => current.id !== job.id);
        return [job, ...withoutJob].sort(sortJobs);
      });
      queryClient.setQueryData(["elasticsearch-enrichment-job", job.id], job);
      void queryClient.invalidateQueries({ queryKey: ["elasticsearch-enrichment-jobs", job.binding_id] });
    },
  });

  async function handleCreateBinding(payload: ElasticsearchBindingCreateRequest) {
    await createMutation.mutateAsync(payload);
  }

  async function handleUpdateBinding(bindingId: number, payload: ElasticsearchBindingUpdateRequest) {
    await updateMutation.mutateAsync({ bindingId, payload });
  }

  async function handleDeleteBinding(bindingId: number) {
    await deleteMutation.mutateAsync(bindingId);
  }

  async function handleDryRunBinding(bindingId: number) {
    await dryRunMutation.mutateAsync(bindingId);
  }

  async function handleStartJob(bindingId: number, payload: ElasticsearchEnrichmentJobCreateRequest) {
    await startJobMutation.mutateAsync({ bindingId, payload });
  }

  async function handleCancelJob(jobId: number) {
    await cancelJobMutation.mutateAsync({ jobId, reason: "Cancelled from Integrations UI." });
  }

  const allBindings = allBindingsQuery.data ?? [];
  const indices = indicesQuery.data ?? [];

  return (
    <div className="space-y-6">
      <section className="grid gap-4 md:grid-cols-3">
        <StatCard description="Terminology namespace applied by bindings." title="Profile" value={selectedProfile ?? "None"} />
        <StatCard description="Saved Elasticsearch enrichment configs." title="Bindings" value={String(bindingsQuery.data?.length ?? 0)} />
        <Card>
          <CardHeader>
            <CardTitle>Binding model</CardTitle>
            <CardDescription>Connect profiles to indices, text fields, target fields, and optional document discriminators.</CardDescription>
          </CardHeader>
          <CardContent>
            <Badge>Profile → Binding → Elasticsearch</Badge>
          </CardContent>
        </Card>
      </section>

      <ElasticsearchDiscoveryPanel
        connection={connectionQuery.data ?? null}
        indices={indices}
        isLoadingConnection={connectionQuery.isLoading}
        isLoadingIndices={indicesQuery.isLoading}
        errorMessage={getErrorMessage(connectionQuery.error) ?? getErrorMessage(indicesQuery.error)}
        onRefresh={() => {
          void connectionQuery.refetch();
          void indicesQuery.refetch();
        }}
      />

      <BindingPatternsHelp />

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_460px]">
        <div className="space-y-6">
          <IntegrationsToolbar
            isLoading={profilesQuery.isLoading}
            loadErrorMessage={profilesQuery.isError ? profilesQuery.error.message : null}
            onSelectProfile={(profileName) => {
              setSelectedProfile(profileName);
              setSelectedBindingId(null);
              setSelectedJobId(null);
              createMutation.reset();
              updateMutation.reset();
              deleteMutation.reset();
              dryRunMutation.reset();
              startJobMutation.reset();
              cancelJobMutation.reset();
            }}
            profiles={profilesQuery.data ?? []}
            selectedProfile={selectedProfile}
          />

          <CreateBindingForm
            allBindings={allBindings}
            discoveredIndices={indices}
            discoveryEnabled={Boolean(connectionQuery.data?.ok)}
            disabled={!selectedProfile || !permissions.canManageBindings}
            errorMessage={getErrorMessage(createMutation.error)}
            isSubmitting={createMutation.isPending}
            onSubmit={handleCreateBinding}
            profiles={profilesQuery.data ?? []}
            readOnlyMessage={
              permissions.canManageBindings
                ? null
                : "Your role can inspect Elasticsearch bindings, but only admins and moderators can update integrations."
            }
            selectedProfile={selectedProfile}
          />

          <BindingsTable
            bindings={bindingsQuery.data ?? []}
            isLoading={bindingsQuery.isLoading && Boolean(selectedProfile)}
            loadErrorMessage={bindingsQuery.isError ? bindingsQuery.error.message : null}
            onSelectBinding={(binding) => {
              setSelectedBindingId(binding.id);
              updateMutation.reset();
              deleteMutation.reset();
              dryRunMutation.reset();
              startJobMutation.reset();
              cancelJobMutation.reset();
              setSelectedJobId(null);
            }}
            selectedBindingId={selectedBindingId}
          />
        </div>

        <BindingDetailsPanel
          allBindings={allBindings}
          binding={selectedBinding}
          canManage={permissions.canManageBindings}
          deleteErrorMessage={getErrorMessage(deleteMutation.error)}
          discoveredIndices={indices}
          discoveryEnabled={Boolean(connectionQuery.data?.ok)}
          dryRunErrorMessage={getErrorMessage(dryRunMutation.error)}
          dryRunResult={dryRunMutation.data ?? null}
          isDeleting={deleteMutation.isPending}
          isDryRunning={dryRunMutation.isPending}
          isCancellingJob={cancelJobMutation.isPending}
          isLoadingJobs={jobsQuery.isLoading && Boolean(selectedBinding)}
          isStartingJob={startJobMutation.isPending}
          isUpdating={updateMutation.isPending}
          jobDetails={jobDetailsQuery.data ?? null}
          jobErrorMessage={getErrorMessage(startJobMutation.error) ?? getErrorMessage(cancelJobMutation.error) ?? getErrorMessage(jobsQuery.error) ?? getErrorMessage(jobDetailsQuery.error)}
          jobs={jobsQuery.data ?? []}
          onCancelJob={handleCancelJob}
          onDelete={handleDeleteBinding}
          onDryRun={handleDryRunBinding}
          onSelectJob={setSelectedJobId}
          onStartJob={handleStartJob}
          onUpdate={handleUpdateBinding}
          profiles={profilesQuery.data ?? []}
          selectedJobId={selectedJobId}
          updateErrorMessage={getErrorMessage(updateMutation.error)}
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

function ElasticsearchDiscoveryPanel({
  connection,
  errorMessage,
  indices,
  isLoadingConnection,
  isLoadingIndices,
  onRefresh,
}: {
  connection: ElasticsearchConnectionStatus | null;
  errorMessage?: string | null;
  indices: ElasticsearchIndex[];
  isLoadingConnection: boolean;
  isLoadingIndices: boolean;
  onRefresh: () => void;
}) {
  const statusText = isLoadingConnection
    ? "Checking..."
    : connection?.ok
      ? "Connected"
      : connection?.configured
        ? "Connection failed"
        : "Manual mode";

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle>Elasticsearch discovery</CardTitle>
            <CardDescription>Test the configured connection, list indices, and use mapping fields as input suggestions. Manual config still works without a connection.</CardDescription>
          </div>
          <Button onClick={onRefresh} type="button" variant="secondary">
            Test connection
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {errorMessage ? <InlineError message={errorMessage} /> : null}
        <div className="flex flex-wrap items-center gap-2">
          <Badge className={connection?.ok ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200" : undefined}>{statusText}</Badge>
          {connection?.url ? <span className="text-slate-500 dark:text-slate-400">{connection.url}</span> : null}
          {connection?.cluster_name ? <span className="text-slate-500 dark:text-slate-400">{connection.cluster_name}</span> : null}
          {connection?.cluster_version ? <span className="text-slate-500 dark:text-slate-400">v{connection.cluster_version}</span> : null}
        </div>
        {connection?.error ? <p className="text-sm text-slate-500 dark:text-slate-400">{connection.error}</p> : null}
        {connection?.ok ? (
          <div>
            <div className="font-medium text-slate-700 dark:text-slate-200">Discovered indices</div>
            {isLoadingIndices ? (
              <p className="mt-1 text-slate-500 dark:text-slate-400">Loading indices...</p>
            ) : indices.length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-2">
                {indices.map((index) => (
                  <Badge key={index.name} className="bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200">
                    {index.name}{index.docs_count !== null ? ` · ${index.docs_count} docs` : ""}
                  </Badge>
                ))}
              </div>
            ) : (
              <p className="mt-1 text-slate-500 dark:text-slate-400">No indices returned by Elasticsearch.</p>
            )}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function BindingPatternsHelp() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Binding patterns</CardTitle>
        <CardDescription>Use bindings to keep profile terminology separate from Elasticsearch storage layout.</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid gap-3 text-sm text-slate-600 dark:text-slate-300 md:grid-cols-3">
          <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
            <div className="font-medium text-slate-950 dark:text-slate-50">1 profile → 1 index</div>
            <div className="mt-1">Use one binding without a discriminator when the whole index belongs to one profile.</div>
          </div>
          <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
            <div className="font-medium text-slate-950 dark:text-slate-50">1 profile → many indices</div>
            <div className="mt-1">Create one binding per index so enrichment jobs can run and fail independently.</div>
          </div>
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-100">
            <div className="font-medium">Many profiles → 1 index</div>
            <div className="mt-1">A document discriminator is required, for example <code>team = infra</code>.</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function IntegrationsToolbar({
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
        <CardTitle>Elasticsearch bindings</CardTitle>
        <CardDescription>Configure where each terminology profile should be applied during enrichment jobs.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {loadErrorMessage ? <InlineError message={loadErrorMessage} /> : null}
        {isLoading ? <p className="text-sm text-slate-500 dark:text-slate-400">Loading profiles...</p> : null}
        {profiles.length > 0 ? (
          <div className="space-y-2">
            <div className="text-sm font-medium text-slate-700 dark:text-slate-200">Filter by profile</div>
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
            No profiles found. Create a terminology profile before adding Elasticsearch bindings.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function CreateBindingForm({
  allBindings,
  discoveredIndices,
  discoveryEnabled,
  disabled = false,
  errorMessage,
  isSubmitting = false,
  onSubmit,
  profiles,
  readOnlyMessage,
  selectedProfile,
}: {
  allBindings: ElasticsearchBinding[];
  discoveredIndices: ElasticsearchIndex[];
  discoveryEnabled: boolean;
  disabled?: boolean;
  errorMessage?: string | null;
  isSubmitting?: boolean;
  onSubmit: (payload: ElasticsearchBindingCreateRequest) => Promise<void> | void;
  profiles: Profile[];
  readOnlyMessage?: string | null;
  selectedProfile: string | null;
}) {
  const [name, setName] = useState("");
  const [profileName, setProfileName] = useState(selectedProfile ?? "");
  const [description, setDescription] = useState("");
  const [indexName, setIndexName] = useState("");
  const [textFields, setTextFields] = useState("");
  const [targetField, setTargetField] = useState("skeinrank");
  const [discriminatorField, setDiscriminatorField] = useState("");
  const [discriminatorValue, setDiscriminatorValue] = useState("");
  const [timestampField, setTimestampField] = useState("");
  const [timeWindow, setTimeWindow] = useState<TimeWindowValue>("all");
  const [customTimeWindowDays, setCustomTimeWindowDays] = useState("90");
  const [mode, setMode] = useState<ElasticsearchBindingMode>("dry_run");
  const [writeStrategy, setWriteStrategy] = useState<ElasticsearchBindingWriteStrategy>("reindex_alias_swap");
  const [isEnabled, setIsEnabled] = useState(true);

  useEffect(() => {
    setProfileName(selectedProfile ?? "");
  }, [selectedProfile]);

  const mappingQuery = useQuery({
    queryKey: ["elasticsearch", "mapping", indexName.trim()],
    queryFn: () => getElasticsearchIndexMapping(indexName.trim()),
    enabled: discoveryEnabled && indexName.trim().length > 0,
  });
  const mappingFields = mappingQuery.data?.fields ?? [];
  const textCandidates = mappingFields.filter((field) => field.is_text_candidate);
  const discriminatorCandidates = mappingFields.filter((field) => field.is_discriminator_candidate);
  const timestampCandidates = mappingFields.filter((field) => field.type === "date" || field.type === "date_nanos");

  const parsedTextFields = parseTextFields(textFields);
  const timeWindowDays = timeWindowDaysFromDraft(timeWindow, customTimeWindowDays);
  const hasInvalidCustomTimeWindow = timeWindow === "custom" && timeWindowDays === null;
  const hasTimeWindowWithoutTimestamp = timeWindowDays !== null && timestampField.trim().length === 0;
  const validation = validateBindingDraft(allBindings, {
    profileName,
    indexName,
    filterField: discriminatorField,
    filterValue: discriminatorValue,
  });
  const canSubmit =
    !disabled &&
    !isSubmitting &&
    name.trim().length > 0 &&
    profileName.trim().length > 0 &&
    indexName.trim().length > 0 &&
    targetField.trim().length > 0 &&
    parsedTextFields.length > 0 &&
    !hasInvalidCustomTimeWindow &&
    !hasTimeWindowWithoutTimestamp &&
    !validation.hasPartialFilter &&
    !validation.missingDiscriminator;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    await onSubmit({
      name: name.trim(),
      profile_name: profileName.trim(),
      description: description.trim() || null,
      index_name: indexName.trim(),
      text_fields: parsedTextFields,
      target_field: targetField.trim(),
      filter_field: discriminatorField.trim() || null,
      filter_value: discriminatorValue.trim() || null,
      timestamp_field: timestampField.trim() || null,
      time_window_days: timeWindowDays,
      mode,
      write_strategy: writeStrategy,
      is_enabled: isEnabled,
    });
    setName("");
    setDescription("");
    setIndexName("");
    setTextFields("");
    setTargetField("skeinrank");
    setDiscriminatorField("");
    setDiscriminatorValue("");
    setTimestampField("");
    setTimeWindow("all");
    setCustomTimeWindowDays("90");
    setMode("dry_run");
    setWriteStrategy("reindex_alias_swap");
    setIsEnabled(true);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Create Elasticsearch binding</CardTitle>
        <CardDescription>Save a manual config that maps one profile to one Elasticsearch index or filtered document subset.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {readOnlyMessage ? (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
            {readOnlyMessage}
          </div>
        ) : null}
        <form className="space-y-4" onSubmit={handleSubmit}>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Binding name</span>
              <Input disabled={disabled || isSubmitting} onChange={(event) => setName(event.target.value)} placeholder="infra docs" value={name} />
            </label>
            <label className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Profile</span>
              <select className={selectClassName} disabled={disabled || isSubmitting || profiles.length === 0} onChange={(event) => setProfileName(event.target.value)} value={profileName}>
                {profiles.map((profile) => (
                  <option key={profile.id} value={profile.name}>{profile.name}</option>
                ))}
              </select>
            </label>
          </div>
          <label className="space-y-1.5">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Description</span>
            <Input disabled={disabled || isSubmitting} onChange={(event) => setDescription(event.target.value)} placeholder="Optional binding note" value={description} />
          </label>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Index</span>
              <Input disabled={disabled || isSubmitting} list="create-es-indices" onChange={(event) => setIndexName(event.target.value)} placeholder="docs" value={indexName} />
              <IndexDatalist id="create-es-indices" indices={discoveredIndices} />
            </label>
            <label className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Target field</span>
              <Input disabled={disabled || isSubmitting} list="create-es-target-fields" onChange={(event) => setTargetField(event.target.value)} placeholder="skeinrank" value={targetField} />
              <FieldsDatalist id="create-es-target-fields" fields={mappingFields} />
            </label>
          </div>
          <label className="space-y-1.5">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Text fields</span>
            <textarea
              aria-label="Text fields"
              className={textareaClassName}
              disabled={disabled || isSubmitting}
              onChange={(event) => setTextFields(event.target.value)}
              placeholder="title, body, content"
              value={textFields}
            />
            <span className="text-xs text-slate-500 dark:text-slate-400">Use commas or new lines. These fields are read by enrichment jobs.</span>
          </label>
          <MappingFieldSuggestions
            isLoading={mappingQuery.isLoading}
            errorMessage={getErrorMessage(mappingQuery.error)}
            fields={textCandidates}
            label="Discovered text fields"
            onUseFields={(fields) => setTextFields(mergeTextFields(textFields, fields))}
          />
          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Document discriminator field</span>
              <Input disabled={disabled || isSubmitting} list="create-es-discriminator-fields" onChange={(event) => setDiscriminatorField(event.target.value)} placeholder="team" value={discriminatorField} />
              <FieldsDatalist id="create-es-discriminator-fields" fields={discriminatorCandidates} />
            </label>
            <label className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Value for this profile</span>
              <Input disabled={disabled || isSubmitting} onChange={(event) => setDiscriminatorValue(event.target.value)} placeholder="infra" value={discriminatorValue} />
            </label>
          </div>
          <MappingFieldSuggestions
            fields={discriminatorCandidates}
            label="Discovered discriminator fields"
            onUseFields={(fields) => setDiscriminatorField(fields[0] ?? discriminatorField)}
          />
          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Timestamp field</span>
              <Input disabled={disabled || isSubmitting} list="create-es-timestamp-fields" onChange={(event) => setTimestampField(event.target.value)} placeholder="@timestamp" value={timestampField} />
              <FieldsDatalist id="create-es-timestamp-fields" fields={timestampCandidates} />
            </label>
            <label className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Time window</span>
              <select className={selectClassName} disabled={disabled || isSubmitting} onChange={(event) => setTimeWindow(event.target.value as TimeWindowValue)} value={timeWindow}>
                {timeWindowOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
          </div>
          {timeWindow === "custom" ? (
            <label className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Custom time window days</span>
              <Input disabled={disabled || isSubmitting} max={3650} min={1} onChange={(event) => setCustomTimeWindowDays(event.target.value)} type="number" value={customTimeWindowDays} />
            </label>
          ) : null}
          <MappingFieldSuggestions
            fields={timestampCandidates}
            label="Discovered timestamp fields"
            onUseFields={(fields) => setTimestampField(fields[0] ?? timestampField)}
          />
          <TimeFilterValidationMessage hasInvalidCustomTimeWindow={hasInvalidCustomTimeWindow} hasTimeWindowWithoutTimestamp={hasTimeWindowWithoutTimestamp} />
          <BindingValidationMessages validation={validation} />
          <div className="flex flex-wrap items-center gap-4">
            <label className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Mode</span>
              <select className={selectClassName} disabled={disabled || isSubmitting} onChange={(event) => setMode(event.target.value as ElasticsearchBindingMode)} value={mode}>
                {bindingModes.map((bindingMode) => <option key={bindingMode} value={bindingMode}>{bindingMode}</option>)}
              </select>
            </label>
            <label className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Write strategy</span>
              <select className={selectClassName} disabled={disabled || isSubmitting} onChange={(event) => setWriteStrategy(event.target.value as ElasticsearchBindingWriteStrategy)} value={writeStrategy}>
                {bindingWriteStrategies.map((strategy) => <option key={strategy} value={strategy}>{strategy}</option>)}
              </select>
            </label>
            <label className="mt-6 flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
              <input checked={isEnabled} disabled={disabled || isSubmitting} onChange={(event) => setIsEnabled(event.target.checked)} type="checkbox" />
              Enabled binding
            </label>
          </div>
          {errorMessage ? <InlineError message={errorMessage} /> : null}
          <Button disabled={!canSubmit} type="submit">{isSubmitting ? "Creating..." : "Create binding"}</Button>
        </form>
      </CardContent>
    </Card>
  );
}

function BindingsTable({
  bindings,
  isLoading,
  loadErrorMessage,
  onSelectBinding,
  selectedBindingId,
}: {
  bindings: ElasticsearchBinding[];
  isLoading: boolean;
  loadErrorMessage?: string | null;
  onSelectBinding: (binding: ElasticsearchBinding) => void;
  selectedBindingId: number | null;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Saved bindings</CardTitle>
        <CardDescription>Each row describes one profile-to-index enrichment rule.</CardDescription>
      </CardHeader>
      <CardContent>
        {loadErrorMessage ? <InlineError message={loadErrorMessage} /> : null}
        {isLoading ? <p className="text-sm text-slate-500 dark:text-slate-400">Loading bindings...</p> : null}
        <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800">
          <table className="w-full border-collapse text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-950 dark:text-slate-400">
              <tr>
                <th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">Binding</th>
                <th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">Profile</th>
                <th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">Index</th>
                <th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">Discriminator</th>
                <th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">Strategy</th>
                <th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">Status</th>
              </tr>
            </thead>
            <tbody>
              {bindings.map((binding) => (
                <tr
                  className={`cursor-pointer transition-colors hover:bg-slate-50 dark:hover:bg-slate-900 ${selectedBindingId === binding.id ? "bg-slate-50 dark:bg-slate-900" : ""}`}
                  key={binding.id}
                  onClick={() => onSelectBinding(binding)}
                >
                  <td className="border-b border-slate-100 px-5 py-4 dark:border-slate-800"><span className="font-medium text-slate-950 dark:text-slate-50">{binding.name}</span></td>
                  <td className="border-b border-slate-100 px-5 py-4 dark:border-slate-800">{binding.profile_name}</td>
                  <td className="border-b border-slate-100 px-5 py-4 dark:border-slate-800"><code>{binding.index_name}</code></td>
                  <td className="border-b border-slate-100 px-5 py-4 dark:border-slate-800">{formatDiscriminator(binding)}</td>
                  <td className="border-b border-slate-100 px-5 py-4 dark:border-slate-800"><BindingWriteStrategyBadge strategy={binding.write_strategy} /></td>
                  <td className="border-b border-slate-100 px-5 py-4 dark:border-slate-800"><BindingStatusBadge isEnabled={binding.is_enabled} /></td>
                </tr>
              ))}
              {bindings.length === 0 ? (
                <tr>
                  <td className="px-5 py-8 text-center text-sm text-slate-500 dark:text-slate-400" colSpan={6}>No bindings found for this profile.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function BindingDetailsPanel({
  allBindings,
  binding,
  canManage,
  deleteErrorMessage,
  discoveredIndices,
  discoveryEnabled,
  dryRunErrorMessage,
  dryRunResult,
  isDeleting,
  isDryRunning,
  isCancellingJob,
  isLoadingJobs,
  isStartingJob,
  isUpdating,
  jobDetails,
  jobErrorMessage,
  jobs,
  onCancelJob,
  onDelete,
  onDryRun,
  onSelectJob,
  onStartJob,
  onUpdate,
  profiles,
  selectedJobId,
  updateErrorMessage,
}: {
  allBindings: ElasticsearchBinding[];
  binding: ElasticsearchBinding | null;
  canManage: boolean;
  deleteErrorMessage?: string | null;
  discoveredIndices: ElasticsearchIndex[];
  discoveryEnabled: boolean;
  dryRunErrorMessage?: string | null;
  dryRunResult: ElasticsearchBindingDryRunResponse | null;
  isDeleting: boolean;
  isDryRunning: boolean;
  isCancellingJob: boolean;
  isLoadingJobs: boolean;
  isStartingJob: boolean;
  isUpdating: boolean;
  jobDetails: ElasticsearchEnrichmentJob | null;
  jobErrorMessage?: string | null;
  jobs: ElasticsearchEnrichmentJob[];
  onCancelJob: (jobId: number) => Promise<void> | void;
  onDelete: (bindingId: number) => Promise<void> | void;
  onDryRun: (bindingId: number) => Promise<void> | void;
  onSelectJob: (jobId: number) => void;
  onStartJob: (bindingId: number, payload: ElasticsearchEnrichmentJobCreateRequest) => Promise<void> | void;
  onUpdate: (bindingId: number, payload: ElasticsearchBindingUpdateRequest) => Promise<void> | void;
  profiles: Profile[];
  selectedJobId: number | null;
  updateErrorMessage?: string | null;
}) {
  const [name, setName] = useState("");
  const [profileName, setProfileName] = useState("");
  const [description, setDescription] = useState("");
  const [indexName, setIndexName] = useState("");
  const [textFields, setTextFields] = useState("");
  const [targetField, setTargetField] = useState("");
  const [discriminatorField, setDiscriminatorField] = useState("");
  const [discriminatorValue, setDiscriminatorValue] = useState("");
  const [timestampField, setTimestampField] = useState("");
  const [timeWindow, setTimeWindow] = useState<TimeWindowValue>("all");
  const [customTimeWindowDays, setCustomTimeWindowDays] = useState("90");
  const [mode, setMode] = useState<ElasticsearchBindingMode>("dry_run");
  const [writeStrategy, setWriteStrategy] = useState<ElasticsearchBindingWriteStrategy>("reindex_alias_swap");
  const [isEnabled, setIsEnabled] = useState(true);

  useEffect(() => {
    if (!binding) return;
    setName(binding.name);
    setProfileName(binding.profile_name);
    setDescription(binding.description ?? "");
    setIndexName(binding.index_name);
    setTextFields(binding.text_fields.join(", "));
    setTargetField(binding.target_field);
    setDiscriminatorField(binding.filter_field ?? "");
    setDiscriminatorValue(binding.filter_value ?? "");
    setTimestampField(binding.timestamp_field ?? "");
    setTimeWindow(timeWindowValueFromDays(binding.time_window_days));
    setCustomTimeWindowDays(binding.time_window_days ? String(binding.time_window_days) : "90");
    setMode(binding.mode);
    setWriteStrategy(binding.write_strategy);
    setIsEnabled(binding.is_enabled);
  }, [binding]);

  const mappingQuery = useQuery({
    queryKey: ["elasticsearch", "mapping", indexName.trim()],
    queryFn: () => getElasticsearchIndexMapping(indexName.trim()),
    enabled: discoveryEnabled && Boolean(binding) && indexName.trim().length > 0,
  });
  const mappingFields = mappingQuery.data?.fields ?? [];
  const textCandidates = mappingFields.filter((field) => field.is_text_candidate);
  const discriminatorCandidates = mappingFields.filter((field) => field.is_discriminator_candidate);
  const timestampCandidates = mappingFields.filter((field) => field.type === "date" || field.type === "date_nanos");

  if (!binding) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Binding details</CardTitle>
          <CardDescription>Select a binding to inspect or edit its Elasticsearch configuration.</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-slate-500 dark:text-slate-400">No binding selected.</p>
        </CardContent>
      </Card>
    );
  }

  const selectedBinding = binding;
  const parsedTextFields = parseTextFields(textFields);
  const timeWindowDays = timeWindowDaysFromDraft(timeWindow, customTimeWindowDays);
  const hasInvalidCustomTimeWindow = timeWindow === "custom" && timeWindowDays === null;
  const hasTimeWindowWithoutTimestamp = timeWindowDays !== null && timestampField.trim().length === 0;
  const validation = validateBindingDraft(allBindings, {
    id: selectedBinding.id,
    profileName,
    indexName,
    filterField: discriminatorField,
    filterValue: discriminatorValue,
  });
  const canSave = canManage && !isUpdating && !isDeleting && name.trim().length > 0 && profileName.trim().length > 0 && indexName.trim().length > 0 && targetField.trim().length > 0 && parsedTextFields.length > 0 && !hasInvalidCustomTimeWindow && !hasTimeWindowWithoutTimestamp && !validation.hasPartialFilter && !validation.missingDiscriminator;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSave) return;
    await onUpdate(selectedBinding.id, {
      name: name.trim(),
      profile_name: profileName.trim(),
      description: description.trim() || null,
      index_name: indexName.trim(),
      text_fields: parsedTextFields,
      target_field: targetField.trim(),
      filter_field: discriminatorField.trim() || null,
      filter_value: discriminatorValue.trim() || null,
      timestamp_field: timestampField.trim() || null,
      time_window_days: timeWindowDays,
      mode,
      write_strategy: writeStrategy,
      is_enabled: isEnabled,
    });
  }

  async function handleDelete() {
    if (!canManage || isDeleting) return;
    if (!window.confirm(`Delete Elasticsearch binding ${selectedBinding.name}?`)) return;
    await onDelete(selectedBinding.id);
  }

  async function handleDryRun() {
    if (isDryRunning) return;
    await onDryRun(selectedBinding.id);
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>{binding.name}</CardTitle>
            <CardDescription>{binding.index_name} → {binding.target_field}</CardDescription>
          </div>
          <BindingStatusBadge isEnabled={binding.is_enabled} />
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        {!canManage ? (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
            Contributors can inspect bindings, but only admins and moderators can update Elasticsearch integration configs.
          </div>
        ) : null}
        <form className="space-y-4" onSubmit={handleSubmit}>
          <label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit binding name</span><Input disabled={!canManage || isUpdating || isDeleting} onChange={(event) => setName(event.target.value)} value={name} /></label>
          <label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit profile</span><select className={selectClassName} disabled={!canManage || isUpdating || isDeleting || profiles.length === 0} onChange={(event) => setProfileName(event.target.value)} value={profileName}>{profiles.map((profile) => <option key={profile.id} value={profile.name}>{profile.name}</option>)}</select></label>
          <label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit description</span><Input disabled={!canManage || isUpdating || isDeleting} onChange={(event) => setDescription(event.target.value)} placeholder="Optional binding note" value={description} /></label>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit index</span><Input disabled={!canManage || isUpdating || isDeleting} list="edit-es-indices" onChange={(event) => setIndexName(event.target.value)} value={indexName} /><IndexDatalist id="edit-es-indices" indices={discoveredIndices} /></label>
            <label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit target field</span><Input disabled={!canManage || isUpdating || isDeleting} list="edit-es-target-fields" onChange={(event) => setTargetField(event.target.value)} value={targetField} /><FieldsDatalist id="edit-es-target-fields" fields={mappingFields} /></label>
          </div>
          <label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit text fields</span><textarea aria-label="Edit text fields" className={textareaClassName} disabled={!canManage || isUpdating || isDeleting} onChange={(event) => setTextFields(event.target.value)} value={textFields} /></label>
          <MappingFieldSuggestions isLoading={mappingQuery.isLoading} errorMessage={getErrorMessage(mappingQuery.error)} fields={textCandidates} label="Discovered text fields" onUseFields={(fields) => setTextFields(mergeTextFields(textFields, fields))} />
          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit document discriminator field</span><Input disabled={!canManage || isUpdating || isDeleting} list="edit-es-discriminator-fields" onChange={(event) => setDiscriminatorField(event.target.value)} placeholder="Optional" value={discriminatorField} /><FieldsDatalist id="edit-es-discriminator-fields" fields={discriminatorCandidates} /></label>
            <label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit value for this profile</span><Input disabled={!canManage || isUpdating || isDeleting} onChange={(event) => setDiscriminatorValue(event.target.value)} placeholder="Optional" value={discriminatorValue} /></label>
          </div>
          <MappingFieldSuggestions fields={discriminatorCandidates} label="Discovered discriminator fields" onUseFields={(fields) => setDiscriminatorField(fields[0] ?? discriminatorField)} />
          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit timestamp field</span><Input disabled={!canManage || isUpdating || isDeleting} list="edit-es-timestamp-fields" onChange={(event) => setTimestampField(event.target.value)} placeholder="Optional" value={timestampField} /><FieldsDatalist id="edit-es-timestamp-fields" fields={timestampCandidates} /></label>
            <label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit time window</span><select className={selectClassName} disabled={!canManage || isUpdating || isDeleting} onChange={(event) => setTimeWindow(event.target.value as TimeWindowValue)} value={timeWindow}>{timeWindowOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
          </div>
          {timeWindow === "custom" ? <label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit custom time window days</span><Input disabled={!canManage || isUpdating || isDeleting} max={3650} min={1} onChange={(event) => setCustomTimeWindowDays(event.target.value)} type="number" value={customTimeWindowDays} /></label> : null}
          <MappingFieldSuggestions fields={timestampCandidates} label="Discovered timestamp fields" onUseFields={(fields) => setTimestampField(fields[0] ?? timestampField)} />
          <TimeFilterValidationMessage hasInvalidCustomTimeWindow={hasInvalidCustomTimeWindow} hasTimeWindowWithoutTimestamp={hasTimeWindowWithoutTimestamp} />
          <BindingValidationMessages validation={validation} />
          <div className="flex flex-wrap items-center gap-4"><label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit mode</span><select className={selectClassName} disabled={!canManage || isUpdating || isDeleting} onChange={(event) => setMode(event.target.value as ElasticsearchBindingMode)} value={mode}>{bindingModes.map((bindingMode) => <option key={bindingMode} value={bindingMode}>{bindingMode}</option>)}</select></label><label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit write strategy</span><select className={selectClassName} disabled={!canManage || isUpdating || isDeleting} onChange={(event) => setWriteStrategy(event.target.value as ElasticsearchBindingWriteStrategy)} value={writeStrategy}>{bindingWriteStrategies.map((strategy) => <option key={strategy} value={strategy}>{strategy}</option>)}</select></label><label className="mt-6 flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200"><input checked={isEnabled} disabled={!canManage || isUpdating || isDeleting} onChange={(event) => setIsEnabled(event.target.checked)} type="checkbox" />Edit enabled binding</label></div>
          {updateErrorMessage ? <InlineError message={updateErrorMessage} /> : null}{deleteErrorMessage ? <InlineError message={deleteErrorMessage} /> : null}
          <div className="flex flex-wrap gap-2"><Button disabled={!canSave} type="submit">{isUpdating ? "Saving..." : "Save binding"}</Button><Button disabled={!canManage || isUpdating || isDeleting} onClick={handleDelete} type="button" variant="secondary">{isDeleting ? "Deleting..." : "Delete binding"}</Button></div>
        </form>

        <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <div className="font-medium text-slate-950 dark:text-slate-50">Dry-run preview</div>
              <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Read sample documents, match active aliases, and preview the payload that would be written to the target field. No Elasticsearch writes are performed.</p>
            </div>
            <Button disabled={isDryRunning || !binding.is_enabled} onClick={handleDryRun} type="button" variant="secondary">{isDryRunning ? "Running..." : "Run dry-run"}</Button>
          </div>
          {dryRunErrorMessage ? <div className="mt-3"><InlineError message={dryRunErrorMessage} /></div> : null}
          {dryRunResult && dryRunResult.binding.id === binding.id ? <DryRunPreview result={dryRunResult} /> : null}
        </div>

        <EnrichmentJobsPanel
          binding={binding}
          canManage={canManage}
          errorMessage={jobErrorMessage}
          isCancelling={isCancellingJob}
          isLoading={isLoadingJobs}
          isStarting={isStartingJob}
          jobDetails={jobDetails}
          jobs={jobs}
          onCancelJob={onCancelJob}
          onSelectJob={onSelectJob}
          onStartJob={onStartJob}
          selectedJobId={selectedJobId}
        />
      </CardContent>
    </Card>
  );
}


function EnrichmentJobsPanel({
  binding,
  canManage,
  errorMessage,
  isCancelling,
  isLoading,
  isStarting,
  jobDetails,
  jobs,
  onCancelJob,
  onSelectJob,
  onStartJob,
  selectedJobId,
}: {
  binding: ElasticsearchBinding;
  canManage: boolean;
  errorMessage?: string | null;
  isCancelling: boolean;
  isLoading: boolean;
  isStarting: boolean;
  jobDetails: ElasticsearchEnrichmentJob | null;
  jobs: ElasticsearchEnrichmentJob[];
  onCancelJob: (jobId: number) => Promise<void> | void;
  onSelectJob: (jobId: number) => void;
  onStartJob: (bindingId: number, payload: ElasticsearchEnrichmentJobCreateRequest) => Promise<void> | void;
  selectedJobId: number | null;
}) {
  const [targetIndexName, setTargetIndexName] = useState("");
  const [aliasName, setAliasName] = useState("");
  const [maxDocuments, setMaxDocuments] = useState("1000");

  useEffect(() => {
    setTargetIndexName("");
    setAliasName("");
    setMaxDocuments("1000");
  }, [binding.id]);

  const isReindexAliasSwap = binding.write_strategy === "reindex_alias_swap";
  const maxDocumentCount = Number(maxDocuments);
  const canStartJob =
    canManage &&
    binding.is_enabled &&
    binding.mode === "write" &&
    !isStarting &&
    !isCancelling &&
    Number.isInteger(maxDocumentCount) &&
    maxDocumentCount >= 1 &&
    maxDocumentCount <= 10000;

  async function handleStartJob(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canStartJob) return;

    const payload: ElasticsearchEnrichmentJobCreateRequest = {
      max_documents: maxDocumentCount,
    };
    if (isReindexAliasSwap) {
      payload.target_index_name = targetIndexName.trim() || null;
      payload.alias_name = aliasName.trim() || null;
    }
    await onStartJob(binding.id, payload);
  }

  return (
    <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="font-medium text-slate-950 dark:text-slate-50">Enrichment jobs</div>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Start a write-mode enrichment job and track queued/running/cancelled/succeeded/failed status for this binding.
          </p>
        </div>
        <BindingWriteStrategyBadge strategy={binding.write_strategy} />
      </div>

      {!canManage ? (
        <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
          Contributors can inspect enrichment jobs, but only admins and moderators can run them.
        </div>
      ) : null}
      {binding.mode !== "write" ? (
        <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
          Switch this binding to write mode before starting an enrichment job.
        </div>
      ) : null}
      {binding.write_strategy === "in_place" ? (
        <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
          This job will update the existing index in place.
        </div>
      ) : (
        <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
          This job will create an enriched target index and swap the alias after enrichment.
        </div>
      )}
      <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
        Time filter: {formatTimeFilter(binding)}. Max documents is still a safety limit inside that window.
      </div>

      <form className="mt-4 space-y-3" onSubmit={handleStartJob}>
        {isReindexAliasSwap ? (
          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Job target index</span>
              <Input disabled={!canManage || isStarting || binding.mode !== "write"} onChange={(event) => setTargetIndexName(event.target.value)} placeholder={`${binding.index_name}__skeinrank_job_<id>`} value={targetIndexName} />
            </label>
            <label className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Job alias name</span>
              <Input disabled={!canManage || isStarting || binding.mode !== "write"} onChange={(event) => setAliasName(event.target.value)} placeholder={binding.index_name} value={aliasName} />
            </label>
          </div>
        ) : null}
        <label className="space-y-1.5">
          <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Max documents</span>
          <Input disabled={!canManage || isStarting || binding.mode !== "write"} max={10000} min={1} onChange={(event) => setMaxDocuments(event.target.value)} type="number" value={maxDocuments} />
        </label>
        <Button disabled={!canStartJob} type="submit">{isStarting ? "Starting..." : "Run enrichment job"}</Button>
      </form>

      {errorMessage ? <div className="mt-3"><InlineError message={errorMessage} /></div> : null}

      <div className="mt-5 space-y-3">
        <div className="text-sm font-medium text-slate-700 dark:text-slate-200">Job history</div>
        {isLoading ? <p className="text-sm text-slate-500 dark:text-slate-400">Loading enrichment jobs...</p> : null}
        {!isLoading && jobs.length === 0 ? <p className="text-sm text-slate-500 dark:text-slate-400">No enrichment jobs for this binding yet.</p> : null}
        {jobs.length > 0 ? (
          <div className="overflow-hidden rounded-lg border border-slate-200 dark:border-slate-800">
            <table className="w-full border-collapse text-left text-xs">
              <thead className="bg-slate-50 uppercase tracking-wide text-slate-500 dark:bg-slate-950 dark:text-slate-400">
                <tr>
                  <th className="border-b border-slate-200 px-3 py-2 font-semibold dark:border-slate-800">Job</th>
                  <th className="border-b border-slate-200 px-3 py-2 font-semibold dark:border-slate-800">Status</th>
                  <th className="border-b border-slate-200 px-3 py-2 font-semibold dark:border-slate-800">Docs</th>
                  <th className="border-b border-slate-200 px-3 py-2 font-semibold dark:border-slate-800">Finished</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr className={selectedJobId === job.id ? "bg-slate-50 dark:bg-slate-900" : ""} key={job.id}>
                    <td className="border-b border-slate-100 px-3 py-2 dark:border-slate-800"><button className="font-medium text-slate-950 underline-offset-2 hover:underline dark:text-slate-50" onClick={() => onSelectJob(job.id)} type="button">#{job.id}</button></td>
                    <td className="border-b border-slate-100 px-3 py-2 dark:border-slate-800"><JobStatusBadge status={job.status} /></td>
                    <td className="border-b border-slate-100 px-3 py-2 dark:border-slate-800">{job.documents_enriched}/{job.documents_seen}</td>
                    <td className="border-b border-slate-100 px-3 py-2 dark:border-slate-800">{formatDateTime(job.finished_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>

      {jobDetails ? (
        <JobDetails
          canCancel={canManage && ["queued", "running", "cancel_requested"].includes(jobDetails.status)}
          isCancelling={isCancelling}
          job={jobDetails}
          onCancelJob={onCancelJob}
        />
      ) : null}
    </div>
  );
}

function JobDetails({
  canCancel,
  isCancelling,
  job,
  onCancelJob,
}: {
  canCancel: boolean;
  isCancelling: boolean;
  job: ElasticsearchEnrichmentJob;
  onCancelJob: (jobId: number) => Promise<void> | void;
}) {
  const cancellation = job.result_json?.cancellation as Record<string, unknown> | undefined;
  const rollout = job.result_json?.rollout as Record<string, unknown> | undefined;

  return (
    <div className="mt-5 space-y-3 rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-800">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium text-slate-950 dark:text-slate-50">Job #{job.id}</span>
          <JobStatusBadge status={job.status} />
        </div>
        {canCancel ? (
          <Button
            disabled={isCancelling || job.status === "cancel_requested"}
            onClick={() => { void onCancelJob(job.id); }}
            type="button"
            variant="secondary"
          >
            {job.status === "cancel_requested" ? "Cancellation requested" : isCancelling ? "Cancelling..." : "Cancel job"}
          </Button>
        ) : null}
      </div>
      <div className="grid gap-2 text-slate-600 dark:text-slate-300 sm:grid-cols-2">
        <div><span className="font-medium text-slate-700 dark:text-slate-200">Binding:</span> {job.binding_name}</div>
        <div><span className="font-medium text-slate-700 dark:text-slate-200">Profile:</span> {job.profile_name}</div>
        <div><span className="font-medium text-slate-700 dark:text-slate-200">Strategy:</span> {job.write_strategy}</div>
        <div><span className="font-medium text-slate-700 dark:text-slate-200">Requested by:</span> {job.requested_by ?? "—"}</div>
        <div><span className="font-medium text-slate-700 dark:text-slate-200">Source index:</span> <code>{job.source_index}</code></div>
        <div><span className="font-medium text-slate-700 dark:text-slate-200">Target index:</span> {job.target_index ? <code>{job.target_index}</code> : "—"}</div>
        <div><span className="font-medium text-slate-700 dark:text-slate-200">Alias:</span> {job.alias_name ? <code>{job.alias_name}</code> : "—"}</div>
        <div><span className="font-medium text-slate-700 dark:text-slate-200">Failed docs:</span> {job.documents_failed}</div>
        <div><span className="font-medium text-slate-700 dark:text-slate-200">Started:</span> {formatDateTime(job.started_at)}</div>
        <div><span className="font-medium text-slate-700 dark:text-slate-200">Finished:</span> {formatDateTime(job.finished_at)}</div>
      </div>
      {cancellation ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
          Cancellation requested{typeof cancellation.requested_by === "string" ? ` by ${cancellation.requested_by}` : ""}
          {typeof cancellation.cancelled_at === "string" ? ` · cancelled at ${formatDateTime(cancellation.cancelled_at)}` : ""}.
        </div>
      ) : null}
      {rollout ? <RolloutMetadataPanel rollout={rollout} /> : null}
      {job.error_message ? <InlineError message={job.error_message} /> : null}
      <div>
        <div className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">Result JSON</div>
        <pre className="max-h-56 overflow-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-100">{JSON.stringify(job.result_json, null, 2)}</pre>
      </div>
    </div>
  );
}

function RolloutMetadataPanel({ rollout }: { rollout: Record<string, unknown> }) {
  const previousAliasIndices = stringifyList(rollout.previous_alias_indices);
  const newAliasIndices = stringifyList(rollout.new_alias_indices);
  const rollbackCandidate = typeof rollout.rollback_candidate_index === "string" && rollout.rollback_candidate_index ? rollout.rollback_candidate_index : "—";
  const aliasSwapCompleted = rollout.alias_swap_completed === true;

  return (
    <div className="space-y-2 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-900 dark:border-blue-900/60 dark:bg-blue-950/40 dark:text-blue-100">
      <div className="font-medium">Rollout metadata</div>
      <div className="grid gap-2 sm:grid-cols-2">
        <div><span className="font-medium">Status:</span> {String(rollout.status ?? "—")}</div>
        <div><span className="font-medium">Alias swap:</span> {aliasSwapCompleted ? "completed" : "not completed"}</div>
        <div><span className="font-medium">Previous alias indices:</span> <code>{previousAliasIndices}</code></div>
        <div><span className="font-medium">New alias indices:</span> <code>{newAliasIndices}</code></div>
        <div><span className="font-medium">Rollback candidate:</span> <code>{rollbackCandidate}</code></div>
        <div><span className="font-medium">Swapped at:</span> {typeof rollout.alias_swapped_at === "string" ? formatDateTime(rollout.alias_swapped_at) : "—"}</div>
      </div>
      {typeof rollout.rollback_hint === "string" ? <p>{rollout.rollback_hint}</p> : null}
      {typeof rollout.cleanup_hint === "string" ? <p>{rollout.cleanup_hint}</p> : null}
    </div>
  );
}

function stringifyList(value: unknown): string {
  return Array.isArray(value) && value.length > 0 ? value.map((item) => String(item)).join(", ") : "—";
}


function DryRunPreview({ result }: { result: ElasticsearchBindingDryRunResponse }) {
  return (
    <div className="mt-4 space-y-3">
      {result.warnings.length > 0 ? (
        <div className="space-y-1 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
          {result.warnings.map((warning) => <div key={warning}>{warning}</div>)}
        </div>
      ) : null}
      {result.documents.length === 0 ? (
        <p className="text-sm text-slate-500 dark:text-slate-400">No sample documents returned.</p>
      ) : (
        result.documents.map((document) => (
          <div className="rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-800" key={`${document.index_name}-${document.document_id}`}>
            <div className="flex flex-wrap items-center gap-2">
              <Badge>{document.index_name}</Badge>
              <span className="font-medium text-slate-950 dark:text-slate-50">{document.document_id}</span>
              <span className="text-slate-500 dark:text-slate-400">→ {result.binding.target_field}</span>
            </div>
            <p className="mt-2 line-clamp-3 text-slate-600 dark:text-slate-300">{document.text_preview || "No text extracted from configured fields."}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {document.matched_aliases.length > 0 ? document.matched_aliases.map((match) => (
                <Badge className="bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-200" key={`${document.document_id}-${match.alias_value}-${match.canonical_value}`}>{match.alias_value} → {match.canonical_value}</Badge>
              )) : <Badge className="bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">No alias matches</Badge>}
            </div>
            <pre className="mt-3 max-h-56 overflow-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-100">{JSON.stringify(document.would_write, null, 2)}</pre>
          </div>
        ))
      )}
    </div>
  );
}

function MappingFieldSuggestions({
  errorMessage,
  fields,
  isLoading = false,
  label,
  onUseFields,
}: {
  errorMessage?: string | null;
  fields: ElasticsearchMappingField[];
  isLoading?: boolean;
  label: string;
  onUseFields: (fields: string[]) => void;
}) {
  if (errorMessage) {
    return <InlineError message={errorMessage} />;
  }
  if (isLoading) {
    return <p className="text-xs text-slate-500 dark:text-slate-400">Loading mapping fields...</p>;
  }
  if (fields.length === 0) {
    return null;
  }
  return (
    <div className="space-y-2">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</div>
      <div className="flex flex-wrap gap-2">
        {fields.map((field) => (
          <button
            className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300 dark:hover:bg-slate-900"
            key={`${label}-${field.name}`}
            onClick={() => onUseFields([field.name])}
            type="button"
          >
            {field.name} · {field.type}
          </button>
        ))}
      </div>
    </div>
  );
}

function IndexDatalist({ id, indices }: { id: string; indices: ElasticsearchIndex[] }) {
  return (
    <datalist id={id}>
      {indices.map((index) => <option key={index.name} value={index.name} />)}
    </datalist>
  );
}

function FieldsDatalist({ id, fields }: { id: string; fields: ElasticsearchMappingField[] }) {
  return (
    <datalist id={id}>
      {fields.map((field) => <option key={field.name} value={field.name} />)}
    </datalist>
  );
}

function TimeFilterValidationMessage({
  hasInvalidCustomTimeWindow,
  hasTimeWindowWithoutTimestamp,
}: {
  hasInvalidCustomTimeWindow: boolean;
  hasTimeWindowWithoutTimestamp: boolean;
}) {
  if (hasInvalidCustomTimeWindow) {
    return <InlineError message="Custom time window must be between 1 and 3650 days." />;
  }

  if (hasTimeWindowWithoutTimestamp) {
    return <InlineError message="Time window requires a timestamp field." />;
  }

  return null;
}

function BindingValidationMessages({ validation }: { validation: BindingValidation }) {
  if (validation.hasPartialFilter) {
    return <InlineError message="Document discriminator field and value must be provided together." />;
  }

  if (validation.missingDiscriminator) {
    return <InlineError message={`This index is already used by another profile (${validation.sharedProfiles.join(", ")}). Add a document discriminator field and value to avoid mixing documents.`} />;
  }

  if (validation.isSharedIndex) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
        This index is shared with {validation.sharedProfiles.join(", ")}. The discriminator keeps this profile scoped to the intended documents.
      </div>
    );
  }

  return null;
}

function BindingStatusBadge({ isEnabled }: { isEnabled: boolean }) {
  return isEnabled ? <Badge className="bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200">enabled</Badge> : <Badge className="bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">disabled</Badge>;
}

function BindingWriteStrategyBadge({ strategy }: { strategy: ElasticsearchBindingWriteStrategy }) {
  return strategy === "reindex_alias_swap" ? <Badge className="bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-200">reindex + alias swap</Badge> : <Badge className="bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">in place</Badge>;
}

function JobStatusBadge({ status }: { status: ElasticsearchEnrichmentJob["status"] }) {
  const className =
    status === "succeeded"
      ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200"
      : status === "failed"
        ? "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-200"
        : status === "running"
          ? "bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-200"
          : status === "cancel_requested" || status === "cancelled"
            ? "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-200"
            : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300";
  return <Badge className={className}>{status}</Badge>;
}

function InlineError({ message }: { message: string }) {
  return <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200">{message}</div>;
}

function formatDateTime(value: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function getErrorMessage(error: unknown) {
  if (!error) return null;
  return error instanceof Error ? error.message : "Request failed. Check the governance API and try again.";
}

function parseTextFields(value: string) {
  const fields = value.split(/[\n,]/).map((field) => field.trim()).filter(Boolean);
  return Array.from(new Set(fields));
}

function mergeTextFields(currentValue: string, nextFields: string[]) {
  return Array.from(new Set([...parseTextFields(currentValue), ...nextFields])).join(", ");
}

function timeWindowDaysFromDraft(timeWindow: TimeWindowValue, customValue: string) {
  if (timeWindow === "all") {
    return null;
  }
  const rawValue = timeWindow === "custom" ? customValue : timeWindow;
  const parsedValue = Number(rawValue);
  if (!Number.isInteger(parsedValue) || parsedValue < 1 || parsedValue > 3650) {
    return null;
  }
  return parsedValue;
}

function timeWindowValueFromDays(days: number | null): TimeWindowValue {
  if (days === 30 || days === 365 || days === 1825) {
    return String(days) as TimeWindowValue;
  }
  return days ? "custom" : "all";
}

function formatTimeWindowDays(days: number | null) {
  if (!days) return "all documents";
  if (days === 30) return "last 30 days";
  if (days === 365) return "last 1 year";
  if (days === 1825) return "last 5 years";
  return `last ${days} days`;
}

function formatTimeFilter(binding: ElasticsearchBinding) {
  if (!binding.timestamp_field || !binding.time_window_days) {
    return "all documents";
  }
  return `${binding.timestamp_field} · ${formatTimeWindowDays(binding.time_window_days)}`;
}

function formatDiscriminator(binding: ElasticsearchBinding) {
  if (!binding.filter_field || !binding.filter_value) {
    return <span className="text-slate-400 dark:text-slate-500">None</span>;
  }
  return <code>{binding.filter_field} = {binding.filter_value}</code>;
}

function validateBindingDraft(allBindings: ElasticsearchBinding[], draft: BindingDraft): BindingValidation {
  const indexName = normalizeConfigValue(draft.indexName);
  const profileName = normalizeConfigValue(draft.profileName);
  const hasFilterField = Boolean(draft.filterField.trim());
  const hasFilterValue = Boolean(draft.filterValue.trim());
  const hasPartialFilter = hasFilterField !== hasFilterValue;

  if (!indexName || !profileName) {
    return { hasPartialFilter, isSharedIndex: false, missingDiscriminator: false, sharedProfiles: [] };
  }

  const sharedProfiles = Array.from(new Set(
    allBindings
      .filter((binding) => binding.id !== draft.id)
      .filter((binding) => normalizeConfigValue(binding.index_name) === indexName)
      .map((binding) => binding.profile_name)
      .filter((bindingProfileName) => normalizeConfigValue(bindingProfileName) !== profileName),
  )).sort();
  const isSharedIndex = sharedProfiles.length > 0;
  const missingDiscriminator = isSharedIndex && (!hasFilterField || !hasFilterValue);

  return { hasPartialFilter, isSharedIndex, missingDiscriminator, sharedProfiles };
}

function normalizeConfigValue(value: string) {
  return value.trim().toLowerCase();
}

function upsertElasticsearchBinding(queryClient: ReturnType<typeof useQueryClient>, cacheProfileName: string | null, binding: ElasticsearchBinding) {
  queryClient.setQueryData<ElasticsearchBinding[]>(["elasticsearch-bindings", cacheProfileName], (bindings = []) => {
    const shouldInclude = cacheProfileName === "all" || cacheProfileName === binding.profile_name;
    const withoutBinding = bindings.filter((current) => current.id !== binding.id);
    return (shouldInclude ? [binding, ...withoutBinding] : withoutBinding).sort(sortBindings);
  });
}

function removeElasticsearchBinding(queryClient: ReturnType<typeof useQueryClient>, cacheProfileName: string | null, bindingId: number) {
  queryClient.setQueryData<ElasticsearchBinding[]>(["elasticsearch-bindings", cacheProfileName], (bindings = []) => bindings.filter((binding) => binding.id !== bindingId));
}

function sortJobs(left: ElasticsearchEnrichmentJob, right: ElasticsearchEnrichmentJob) {
  return right.created_at.localeCompare(left.created_at) || right.id - left.id;
}

function sortBindings(left: ElasticsearchBinding, right: ElasticsearchBinding) {
  if (left.is_enabled !== right.is_enabled) return Number(right.is_enabled) - Number(left.is_enabled);
  return left.normalized_name.localeCompare(right.normalized_name);
}

const selectClassName = "h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100 disabled:cursor-not-allowed disabled:bg-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:disabled:bg-slate-900 dark:focus:border-slate-500 dark:focus:ring-slate-800";
const textareaClassName = "min-h-20 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-slate-400 focus:ring-2 focus:ring-slate-100 disabled:cursor-not-allowed disabled:bg-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-500 dark:disabled:bg-slate-900 dark:focus:border-slate-500 dark:focus:ring-slate-800";
