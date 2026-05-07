import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useMemo, useState } from "react";

import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { createElasticsearchBinding, deleteElasticsearchBinding, listElasticsearchBindings, listProfiles, updateElasticsearchBinding } from "../lib/api";
import { permissionsForUser } from "../permissions";
import type { AuthUser, ElasticsearchBinding, ElasticsearchBindingCreateRequest, ElasticsearchBindingMode, ElasticsearchBindingUpdateRequest, Profile } from "../types";

const bindingModes: ElasticsearchBindingMode[] = ["dry_run", "write"];

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
      upsertElasticsearchBinding(queryClient, binding.profile_name, binding);
      void queryClient.invalidateQueries({ queryKey: ["elasticsearch-bindings", binding.profile_name] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ bindingId, payload }: { bindingId: number; payload: ElasticsearchBindingUpdateRequest }) => updateElasticsearchBinding(bindingId, payload),
    onSuccess: (binding) => {
      setSelectedProfile(binding.profile_name);
      setSelectedBindingId(binding.id);
      upsertElasticsearchBinding(queryClient, binding.profile_name, binding);
      void queryClient.invalidateQueries({ queryKey: ["elasticsearch-bindings"] });
      void queryClient.invalidateQueries({ queryKey: ["elasticsearch-bindings", binding.profile_name] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (bindingId: number) => deleteElasticsearchBinding(bindingId),
    onSuccess: (_result, bindingId) => {
      setSelectedBindingId(null);
      removeElasticsearchBinding(queryClient, selectedProfile, bindingId);
      void queryClient.invalidateQueries({ queryKey: ["elasticsearch-bindings", selectedProfile] });
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

  return (
    <div className="space-y-6">
      <section className="grid gap-4 md:grid-cols-3">
        <StatCard description="Terminology namespace applied by bindings." title="Profile" value={selectedProfile ?? "None"} />
        <StatCard description="Saved Elasticsearch enrichment configs." title="Bindings" value={String(bindingsQuery.data?.length ?? 0)} />
        <Card>
          <CardHeader>
            <CardTitle>Binding model</CardTitle>
            <CardDescription>Connect profiles to indices, text fields, target fields, and optional filters.</CardDescription>
          </CardHeader>
          <CardContent><Badge>Profile → Binding → Elasticsearch</Badge></CardContent>
        </Card>
      </section>

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
            }}
            profiles={profilesQuery.data ?? []}
            selectedProfile={selectedProfile}
          />

          <CreateBindingForm
            disabled={!selectedProfile || !permissions.canManageBindings}
            errorMessage={errorMessage(createMutation.error)}
            isSubmitting={createMutation.isPending}
            onSubmit={handleCreateBinding}
            profiles={profilesQuery.data ?? []}
            readOnlyMessage={permissions.canManageBindings ? null : "Your role can inspect Elasticsearch bindings, but only admins and moderators can update integrations."}
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
            }}
            selectedBindingId={selectedBindingId}
          />
        </div>

        <BindingDetailsPanel
          binding={selectedBinding}
          canManage={permissions.canManageBindings}
          deleteErrorMessage={errorMessage(deleteMutation.error)}
          isDeleting={deleteMutation.isPending}
          isUpdating={updateMutation.isPending}
          onDelete={handleDeleteBinding}
          onUpdate={handleUpdateBinding}
          profiles={profilesQuery.data ?? []}
          updateErrorMessage={errorMessage(updateMutation.error)}
        />
      </section>
    </div>
  );
}

function StatCard({ description, title, value }: { description: string; title: string; value: string }) {
  return (
    <Card><CardHeader><CardTitle>{title}</CardTitle><CardDescription>{description}</CardDescription></CardHeader><CardContent><div className="text-3xl font-semibold">{value}</div></CardContent></Card>
  );
}

function IntegrationsToolbar({ isLoading, loadErrorMessage, onSelectProfile, profiles, selectedProfile }: { isLoading: boolean; loadErrorMessage?: string | null; onSelectProfile: (profileName: string) => void; profiles: Profile[]; selectedProfile: string | null }) {
  return (
    <Card>
      <CardHeader><CardTitle>Elasticsearch bindings</CardTitle><CardDescription>Configure where each terminology profile should be applied during enrichment jobs.</CardDescription></CardHeader>
      <CardContent className="space-y-4">
        {loadErrorMessage ? <InlineError message={loadErrorMessage} /> : null}
        {isLoading ? <p className="text-sm text-slate-500 dark:text-slate-400">Loading profiles...</p> : null}
        {profiles.length > 0 ? (
          <div className="space-y-2">
            <div className="text-sm font-medium text-slate-700 dark:text-slate-200">Filter by profile</div>
            <div className="flex flex-wrap gap-2">
              {profiles.map((profile) => (
                <button className={`rounded-full border px-3 py-1.5 text-sm font-medium transition-colors ${selectedProfile === profile.name ? "border-slate-950 bg-slate-950 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-950" : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300 dark:hover:bg-slate-900"}`} key={profile.id} onClick={() => onSelectProfile(profile.name)} type="button">{profile.name}</button>
              ))}
            </div>
          </div>
        ) : (
          <p className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">No profiles found. Create a terminology profile before adding Elasticsearch bindings.</p>
        )}
      </CardContent>
    </Card>
  );
}

function CreateBindingForm({ disabled = false, errorMessage, isSubmitting = false, onSubmit, profiles, readOnlyMessage, selectedProfile }: { disabled?: boolean; errorMessage?: string | null; isSubmitting?: boolean; onSubmit: (payload: ElasticsearchBindingCreateRequest) => Promise<void> | void; profiles: Profile[]; readOnlyMessage?: string | null; selectedProfile: string | null }) {
  const [name, setName] = useState("");
  const [profileName, setProfileName] = useState(selectedProfile ?? "");
  const [description, setDescription] = useState("");
  const [indexName, setIndexName] = useState("");
  const [textFields, setTextFields] = useState("");
  const [targetField, setTargetField] = useState("skeinrank");
  const [filterField, setFilterField] = useState("");
  const [filterValue, setFilterValue] = useState("");
  const [mode, setMode] = useState<ElasticsearchBindingMode>("dry_run");
  const [isEnabled, setIsEnabled] = useState(true);

  useEffect(() => { setProfileName(selectedProfile ?? ""); }, [selectedProfile]);

  const parsedTextFields = parseTextFields(textFields);
  const hasPartialFilter = Boolean(filterField.trim()) !== Boolean(filterValue.trim());
  const canSubmit = !disabled && !isSubmitting && name.trim().length > 0 && profileName.trim().length > 0 && indexName.trim().length > 0 && targetField.trim().length > 0 && parsedTextFields.length > 0 && !hasPartialFilter;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    await onSubmit({ name: name.trim(), profile_name: profileName.trim(), description: description.trim() || null, index_name: indexName.trim(), text_fields: parsedTextFields, target_field: targetField.trim(), filter_field: filterField.trim() || null, filter_value: filterValue.trim() || null, mode, is_enabled: isEnabled });
    setName(""); setDescription(""); setIndexName(""); setTextFields(""); setTargetField("skeinrank"); setFilterField(""); setFilterValue(""); setMode("dry_run"); setIsEnabled(true);
  }

  return (
    <Card>
      <CardHeader><CardTitle>Create Elasticsearch binding</CardTitle><CardDescription>Save a manual config that maps one profile to one Elasticsearch index or filtered document subset.</CardDescription></CardHeader>
      <CardContent className="space-y-4">
        {readOnlyMessage ? <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">{readOnlyMessage}</div> : null}
        <form className="space-y-4" onSubmit={handleSubmit}>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Binding name</span><Input disabled={disabled || isSubmitting} onChange={(event) => setName(event.target.value)} placeholder="infra docs" value={name} /></label>
            <label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Profile</span><select className={selectClassName} disabled={disabled || isSubmitting || profiles.length === 0} onChange={(event) => setProfileName(event.target.value)} value={profileName}>{profiles.map((profile) => <option key={profile.id} value={profile.name}>{profile.name}</option>)}</select></label>
          </div>
          <label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Description</span><Input disabled={disabled || isSubmitting} onChange={(event) => setDescription(event.target.value)} placeholder="Optional binding note" value={description} /></label>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Index</span><Input disabled={disabled || isSubmitting} onChange={(event) => setIndexName(event.target.value)} placeholder="docs" value={indexName} /></label>
            <label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Target field</span><Input disabled={disabled || isSubmitting} onChange={(event) => setTargetField(event.target.value)} placeholder="skeinrank" value={targetField} /></label>
          </div>
          <label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Text fields</span><textarea className="min-h-20 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-slate-400 focus:ring-2 focus:ring-slate-100 disabled:cursor-not-allowed disabled:bg-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-500 dark:disabled:bg-slate-900 dark:focus:border-slate-500 dark:focus:ring-slate-800" disabled={disabled || isSubmitting} onChange={(event) => setTextFields(event.target.value)} placeholder="title, body, content" value={textFields} /><span className="text-xs text-slate-500 dark:text-slate-400">Use commas or new lines. These fields are read by enrichment jobs.</span></label>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Filter field</span><Input disabled={disabled || isSubmitting} onChange={(event) => setFilterField(event.target.value)} placeholder="team" value={filterField} /></label>
            <label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Filter value</span><Input disabled={disabled || isSubmitting} onChange={(event) => setFilterValue(event.target.value)} placeholder="infra" value={filterValue} /></label>
          </div>
          {hasPartialFilter ? <InlineError message="Filter field and filter value must be provided together." /> : null}
          <div className="flex flex-wrap items-center gap-4">
            <label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Mode</span><select className={selectClassName} disabled={disabled || isSubmitting} onChange={(event) => setMode(event.target.value as ElasticsearchBindingMode)} value={mode}>{bindingModes.map((bindingMode) => <option key={bindingMode} value={bindingMode}>{bindingMode}</option>)}</select></label>
            <label className="mt-6 flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200"><input checked={isEnabled} disabled={disabled || isSubmitting} onChange={(event) => setIsEnabled(event.target.checked)} type="checkbox" />Enabled</label>
          </div>
          {errorMessage ? <InlineError message={errorMessage} /> : null}
          <Button disabled={!canSubmit} type="submit">{isSubmitting ? "Creating..." : "Create binding"}</Button>
        </form>
      </CardContent>
    </Card>
  );
}

function BindingsTable({ bindings, isLoading, loadErrorMessage, onSelectBinding, selectedBindingId }: { bindings: ElasticsearchBinding[]; isLoading: boolean; loadErrorMessage?: string | null; onSelectBinding: (binding: ElasticsearchBinding) => void; selectedBindingId: number | null }) {
  return (
    <Card>
      <CardHeader><CardTitle>Saved bindings</CardTitle><CardDescription>Manual configs for future Elasticsearch enrichment jobs. These do not connect to Elasticsearch yet.</CardDescription></CardHeader>
      <CardContent className="p-0">
        {loadErrorMessage ? <div className="p-5"><InlineError message={loadErrorMessage} /></div> : null}
        {isLoading ? <p className="p-5 text-sm text-slate-500 dark:text-slate-400">Loading Elasticsearch bindings...</p> : null}
        <div className="overflow-x-auto"><table className="w-full border-collapse text-left text-sm"><thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-950 dark:text-slate-400"><tr><th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">Name</th><th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">Index</th><th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">Text fields</th><th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">Mode</th><th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">Status</th></tr></thead><tbody>{bindings.length === 0 ? (<tr><td className="px-5 py-8 text-center text-sm text-slate-500 dark:text-slate-400" colSpan={5}>No Elasticsearch bindings yet.</td></tr>) : bindings.map((binding) => (<tr className={`cursor-pointer transition-colors ${selectedBindingId === binding.id ? "bg-slate-100 dark:bg-slate-800/70" : "hover:bg-slate-50 dark:hover:bg-slate-900"}`} key={binding.id} onClick={() => onSelectBinding(binding)}><td className="border-b border-slate-100 px-5 py-4 dark:border-slate-800"><div className="font-medium text-slate-950 dark:text-slate-50">{binding.name}</div><div className="text-xs text-slate-500 dark:text-slate-400">{binding.profile_name}</div></td><td className="border-b border-slate-100 px-5 py-4 dark:border-slate-800"><code>{binding.index_name}</code></td><td className="border-b border-slate-100 px-5 py-4 dark:border-slate-800">{binding.text_fields.join(", ")}</td><td className="border-b border-slate-100 px-5 py-4 dark:border-slate-800"><Badge>{binding.mode}</Badge></td><td className="border-b border-slate-100 px-5 py-4 dark:border-slate-800"><BindingStatusBadge isEnabled={binding.is_enabled} /></td></tr>))}</tbody></table></div>
      </CardContent>
    </Card>
  );
}

function BindingDetailsPanel({ binding, canManage, deleteErrorMessage, isDeleting = false, isUpdating = false, onDelete, onUpdate, profiles, updateErrorMessage }: { binding: ElasticsearchBinding | null; canManage: boolean; deleteErrorMessage?: string | null; isDeleting?: boolean; isUpdating?: boolean; onDelete: (bindingId: number) => Promise<void> | void; onUpdate: (bindingId: number, payload: ElasticsearchBindingUpdateRequest) => Promise<void> | void; profiles: Profile[]; updateErrorMessage?: string | null }) {
  const [name, setName] = useState(""); const [profileName, setProfileName] = useState(""); const [description, setDescription] = useState(""); const [indexName, setIndexName] = useState(""); const [textFields, setTextFields] = useState(""); const [targetField, setTargetField] = useState(""); const [filterField, setFilterField] = useState(""); const [filterValue, setFilterValue] = useState(""); const [mode, setMode] = useState<ElasticsearchBindingMode>("dry_run"); const [isEnabled, setIsEnabled] = useState(true);
  useEffect(() => { setName(binding?.name ?? ""); setProfileName(binding?.profile_name ?? ""); setDescription(binding?.description ?? ""); setIndexName(binding?.index_name ?? ""); setTextFields(binding?.text_fields.join(", ") ?? ""); setTargetField(binding?.target_field ?? ""); setFilterField(binding?.filter_field ?? ""); setFilterValue(binding?.filter_value ?? ""); setMode(binding?.mode ?? "dry_run"); setIsEnabled(binding?.is_enabled ?? true); }, [binding?.description, binding?.filter_field, binding?.filter_value, binding?.id, binding?.index_name, binding?.is_enabled, binding?.mode, binding?.name, binding?.profile_name, binding?.target_field, binding?.text_fields]);

  if (!binding) {
    return <Card><CardHeader><CardTitle>Binding details</CardTitle><CardDescription>Select a binding to inspect or update its enrichment configuration.</CardDescription></CardHeader><CardContent><p className="text-sm text-slate-500 dark:text-slate-400">No Elasticsearch binding selected.</p></CardContent></Card>;
  }

  const selectedBinding = binding;
  const parsedTextFields = parseTextFields(textFields);
  const hasPartialFilter = Boolean(filterField.trim()) !== Boolean(filterValue.trim());
  const canSave = canManage && !isUpdating && !isDeleting && name.trim().length > 0 && profileName.trim().length > 0 && indexName.trim().length > 0 && targetField.trim().length > 0 && parsedTextFields.length > 0 && !hasPartialFilter;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSave) return;
    await onUpdate(selectedBinding.id, { name: name.trim(), profile_name: profileName.trim(), description: description.trim() || null, index_name: indexName.trim(), text_fields: parsedTextFields, target_field: targetField.trim(), filter_field: filterField.trim() || null, filter_value: filterValue.trim() || null, mode, is_enabled: isEnabled });
  }

  async function handleDelete() {
    if (!canManage || isDeleting) return;
    if (!window.confirm(`Delete Elasticsearch binding ${selectedBinding.name}?`)) return;
    await onDelete(selectedBinding.id);
  }

  return (
    <Card>
      <CardHeader><div className="flex items-start justify-between gap-3"><div><CardTitle>{binding.name}</CardTitle><CardDescription>{binding.index_name} → {binding.target_field}</CardDescription></div><BindingStatusBadge isEnabled={binding.is_enabled} /></div></CardHeader>
      <CardContent className="space-y-5">
        {!canManage ? <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">Contributors can inspect bindings, but only admins and moderators can update Elasticsearch integration configs.</div> : null}
        <form className="space-y-4" onSubmit={handleSubmit}>
          <label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit binding name</span><Input disabled={!canManage || isUpdating || isDeleting} onChange={(event) => setName(event.target.value)} value={name} /></label>
          <label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit profile</span><select className={selectClassName} disabled={!canManage || isUpdating || isDeleting || profiles.length === 0} onChange={(event) => setProfileName(event.target.value)} value={profileName}>{profiles.map((profile) => <option key={profile.id} value={profile.name}>{profile.name}</option>)}</select></label>
          <label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit description</span><Input disabled={!canManage || isUpdating || isDeleting} onChange={(event) => setDescription(event.target.value)} placeholder="Optional binding note" value={description} /></label>
          <div className="grid gap-4 md:grid-cols-2"><label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit index</span><Input disabled={!canManage || isUpdating || isDeleting} onChange={(event) => setIndexName(event.target.value)} value={indexName} /></label><label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit target field</span><Input disabled={!canManage || isUpdating || isDeleting} onChange={(event) => setTargetField(event.target.value)} value={targetField} /></label></div>
          <label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit text fields</span><textarea className="min-h-20 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-slate-400 focus:ring-2 focus:ring-slate-100 disabled:cursor-not-allowed disabled:bg-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-500 dark:disabled:bg-slate-900 dark:focus:border-slate-500 dark:focus:ring-slate-800" disabled={!canManage || isUpdating || isDeleting} onChange={(event) => setTextFields(event.target.value)} value={textFields} /></label>
          <div className="grid gap-4 md:grid-cols-2"><label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit filter field</span><Input disabled={!canManage || isUpdating || isDeleting} onChange={(event) => setFilterField(event.target.value)} placeholder="Optional" value={filterField} /></label><label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit filter value</span><Input disabled={!canManage || isUpdating || isDeleting} onChange={(event) => setFilterValue(event.target.value)} placeholder="Optional" value={filterValue} /></label></div>
          {hasPartialFilter ? <InlineError message="Filter field and filter value must be provided together." /> : null}
          <div className="flex flex-wrap items-center gap-4"><label className="space-y-1.5"><span className="text-sm font-medium text-slate-700 dark:text-slate-200">Edit mode</span><select className={selectClassName} disabled={!canManage || isUpdating || isDeleting} onChange={(event) => setMode(event.target.value as ElasticsearchBindingMode)} value={mode}>{bindingModes.map((bindingMode) => <option key={bindingMode} value={bindingMode}>{bindingMode}</option>)}</select></label><label className="mt-6 flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200"><input checked={isEnabled} disabled={!canManage || isUpdating || isDeleting} onChange={(event) => setIsEnabled(event.target.checked)} type="checkbox" />Enabled binding</label></div>
          {updateErrorMessage ? <InlineError message={updateErrorMessage} /> : null}{deleteErrorMessage ? <InlineError message={deleteErrorMessage} /> : null}
          <div className="flex flex-wrap gap-2"><Button disabled={!canSave} type="submit">{isUpdating ? "Saving..." : "Save binding"}</Button><Button disabled={!canManage || isUpdating || isDeleting} onClick={handleDelete} type="button" variant="secondary">{isDeleting ? "Deleting..." : "Delete binding"}</Button></div>
        </form>
      </CardContent>
    </Card>
  );
}

function BindingStatusBadge({ isEnabled }: { isEnabled: boolean }) { return isEnabled ? <Badge className="bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200">enabled</Badge> : <Badge className="bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">disabled</Badge>; }
function InlineError({ message }: { message: string }) { return <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200">{message}</div>; }
function errorMessage(error: unknown) { if (!error) return null; return error instanceof Error ? error.message : "Request failed. Check the governance API and try again."; }
function parseTextFields(value: string) { const fields = value.split(/[\n,]/).map((field) => field.trim()).filter(Boolean); return Array.from(new Set(fields)); }
function upsertElasticsearchBinding(queryClient: ReturnType<typeof useQueryClient>, profileName: string | null, binding: ElasticsearchBinding) { queryClient.setQueryData<ElasticsearchBinding[]>(["elasticsearch-bindings", profileName], (bindings = []) => { const withoutBinding = bindings.filter((current) => current.id !== binding.id); return [binding, ...withoutBinding].sort(sortBindings); }); }
function removeElasticsearchBinding(queryClient: ReturnType<typeof useQueryClient>, profileName: string | null, bindingId: number) { queryClient.setQueryData<ElasticsearchBinding[]>(["elasticsearch-bindings", profileName], (bindings = []) => bindings.filter((binding) => binding.id !== bindingId)); }
function sortBindings(left: ElasticsearchBinding, right: ElasticsearchBinding) { if (left.is_enabled !== right.is_enabled) return Number(right.is_enabled) - Number(left.is_enabled); return left.normalized_name.localeCompare(right.normalized_name); }
const selectClassName = "h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100 disabled:cursor-not-allowed disabled:bg-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:disabled:bg-slate-900 dark:focus:border-slate-500 dark:focus:ring-slate-800";
