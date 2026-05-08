import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useMemo, useState } from "react";

import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";
import {
  createElasticsearchBinding,
  deleteElasticsearchBinding,
  dryRunElasticsearchBinding,
  getElasticsearchConnectionStatus,
  getElasticsearchIndexMapping,
  listElasticsearchBindings,
  listElasticsearchIndices,
  listProfiles,
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
  ElasticsearchConnectionStatus,
  ElasticsearchIndex,
  ElasticsearchMappingField,
  Profile,
} from "../types";

const bindingModes: ElasticsearchBindingMode[] = ["dry_run", "write"];

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

  useEffect(() => {
    if (!profilesQuery.data || profilesQuery.data.length === 0) {
      setSelectedProfile(null);
      setSelectedBindingId(null);
      return;
    }

    if (!selectedProfile || !profilesQuery.data.some((profile) => profile.name === selectedProfile)) {
      setSelectedProfile(profilesQuery.data[0].name);
      setSelectedBindingId(null);
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

  const createMutation = useMutation({
    mutationFn: (payload: ElasticsearchBindingCreateRequest) => createElasticsearchBinding(payload),
    onSuccess: (binding) => {
      setSelectedProfile(binding.profile_name);
      setSelectedBindingId(binding.id);
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
      removeElasticsearchBinding(queryClient, "all", bindingId);
      removeElasticsearchBinding(queryClient, selectedProfile, bindingId);
      void queryClient.invalidateQueries({ queryKey: ["elasticsearch-bindings"] });
    },
  });

  const dryRunMutation = useMutation({
    mutationFn: (bindingId: number) => dryRunElasticsearchBinding(bindingId, { limit: 3 }),
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
              createMutation.reset();
              updateMutation.reset();
              deleteMutation.reset();
              dryRunMutation.reset();
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
          isUpdating={updateMutation.isPending}
          onDelete={handleDeleteBinding}
          onDryRun={handleDryRunBinding}
          onUpdate={handleUpdateBinding}
          profiles={profilesQuery.data ?? []}
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
  const [mode, setMode] = useState<ElasticsearchBindingMode>("dry_run");
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

  const parsedTextFields = parseTextFields(textFields);
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
      mode,
      is_enabled: isEnabled,
    });
    setName("");
    setDescription("");
    setIndexName("");
    setTextFields("");
    setTargetField("skeinrank");
    setDiscriminatorField("");
    setDiscriminatorValue("");
    setMode("dry_run");
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
          <BindingValidationMessages validation={validation} />
          <div className="flex flex-wrap items-center gap-4">
            <label className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Mode</span>
              <select className={selectClassName} disabled={disabled || isSubmitting} onChange={(event) => setMode(event.target.value as ElasticsearchBindingMode)} value={mode}>
                {bindingModes.map((bindingMode) => <option key={bindingMode} value={bindingMode}>{bindingMode}</option>)}
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
                  <td className="border-b border-slate-100 px-5 py-4 dark:border-slate-800"><BindingStatusBadge isEnabled={binding.is_enabled} /></td>
                </tr>
              ))}
              {bindings.length === 0 ? (
                <tr>
                  <td className="px-5 py-8 text-center text-sm text-slate-500 dark:text-slate-400" colSpan={5}>No bindings found for this profile.</td>
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
  isUpdating,
  onDelete,
  onDryRun,
  onUpdate,
  profiles,
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
  isUpdating: boolean;
  onDelete: (bindingId: number) => Promise<void> | void;
  onDryRun: (bindingId: number) => Promise<void> | void;
  onUpdate: (bindingId: number, payload: ElasticsearchBindingUpdateRequest) => Promise<void> | void;
  profiles: Profile[];
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
  const [mode, setMode] = useState<ElasticsearchBindingMode>("dry_run");
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
    setMode(binding.mode);
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
  const validation = validateBindingDraft(allBindings, {
    id: selectedBinding.id,
    profileName,
    indexName,
    filterField: discriminatorField,
    filterValue: discriminatorValue,
  });
  const canSave = canManage && !isUpdating && !isDeleting && name.trim().length > 0 && profileName.trim().length > 0 && indexName.trim().length > 0 && targetField.trim().length > 0 && parsedTextFields.length > 0 && !validation.hasPartialFilter && !validation.missingDiscriminator;

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
      mode,
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
          <BindingValidationMessages validation={validation} />
          <div className="flex flex-wrap items-center gap-4"><label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit mode</span><select className={selectClassName} disabled={!canManage || isUpdating || isDeleting} onChange={(event) => setMode(event.target.value as ElasticsearchBindingMode)} value={mode}>{bindingModes.map((bindingMode) => <option key={bindingMode} value={bindingMode}>{bindingMode}</option>)}</select></label><label className="mt-6 flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200"><input checked={isEnabled} disabled={!canManage || isUpdating || isDeleting} onChange={(event) => setIsEnabled(event.target.checked)} type="checkbox" />Edit enabled binding</label></div>
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
      </CardContent>
    </Card>
  );
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

function InlineError({ message }: { message: string }) {
  return <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200">{message}</div>;
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

function sortBindings(left: ElasticsearchBinding, right: ElasticsearchBinding) {
  if (left.is_enabled !== right.is_enabled) return Number(right.is_enabled) - Number(left.is_enabled);
  return left.normalized_name.localeCompare(right.normalized_name);
}

const selectClassName = "h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100 disabled:cursor-not-allowed disabled:bg-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:disabled:bg-slate-900 dark:focus:border-slate-500 dark:focus:ring-slate-800";
const textareaClassName = "min-h-20 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-slate-400 focus:ring-2 focus:ring-slate-100 disabled:cursor-not-allowed disabled:bg-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-500 dark:disabled:bg-slate-900 dark:focus:border-slate-500 dark:focus:ring-slate-800";
