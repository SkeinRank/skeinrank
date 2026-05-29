import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  CircleDashed,
  Database,
  FileJson,
  GitBranch,
  History,
  Layers3,
  Network,
  Plug,
  RotateCcw,
  Search,
  ShieldCheck,
  Sparkles,
  Tags,
  TriangleAlert,
} from "lucide-react";

import { areLegacyWriteToolsEnabled, LEGACY_WRITE_TOOLS_LOCKED_MESSAGE } from "../config";
import type { AppSection } from "../components/layout/AppShell";
import {
  ConsolePage,
  EntityDetailPanel,
  MasterDetailLayout,
  MetricPill,
  SectionCard,
  WorkspaceHeader,
  getConsoleToneForStatus,
} from "../components/layout/ConsolePrimitives";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { getSnapshotSummary, listElasticsearchBindings, listProfiles, listTerms } from "../lib/api";
import type { CanonicalTerm, ElasticsearchBinding, Profile, SnapshotBindingState, SnapshotHistoryItem, SnapshotSummary, TermAlias } from "../types";

type RuntimeAuditLevel = "ready" | "attention" | "empty";
type SchemaTreeMode = "schema" | "snapshots";
type SchemaNode =
  | { kind: "profile"; profile: Profile }
  | { kind: "binding"; binding: ElasticsearchBinding }
  | { kind: "category"; profileName: string; slot: string; terms: CanonicalTerm[] }
  | { kind: "term"; term: CanonicalTerm; profileName: string }
  | { kind: "alias"; alias: TermAlias; term: CanonicalTerm; profileName: string }
  | { kind: "snapshot"; binding: SnapshotBindingState };

export function SnapshotsPage({ onNavigate }: { onNavigate: (section: AppSection) => void }) {
  const summaryQuery = useQuery({
    queryKey: ["snapshots", "summary"],
    queryFn: getSnapshotSummary,
  });
  const [selectedBindingId, setSelectedBindingId] = useState<number | null>(null);

  if (summaryQuery.isLoading) {
    return (
      <SectionCard title="Runtime snapshots">
        <div className="text-sm text-slate-500 dark:text-slate-400">Loading runtime snapshots...</div>
      </SectionCard>
    );
  }

  if (summaryQuery.isError) {
    return (
      <SectionCard
        className="border-red-200 bg-red-50 dark:border-red-900/60 dark:bg-red-950/40"
        title="Unable to load runtime snapshots"
      >
        <div className="flex items-start gap-3 text-sm text-red-700 dark:text-red-200">
          <AlertCircle className="mt-0.5 h-4 w-4 flex-none" />
          <div>
            {summaryQuery.error instanceof Error ? summaryQuery.error.message : "Check the governance API and try again."}
          </div>
        </div>
      </SectionCard>
    );
  }

  const summary = summaryQuery.data;
  if (!summary) {
    return null;
  }

  const attentionBinding = getAttentionBinding(summary.bindings);
  const selectedBinding =
    summary.bindings.find((binding) => binding.id === selectedBindingId) ??
    attentionBinding ??
    summary.bindings[0] ??
    null;

  return (
    <ConsolePage>
      <RuntimeSnapshotsHeader summary={summary} onNavigate={onNavigate} />

      <SchemaSnapshotsTree summary={summary} onNavigate={onNavigate} />

      <MasterDetailLayout asideWidthClassName="xl:grid-cols-[minmax(0,1fr)_390px] 2xl:grid-cols-[minmax(0,1fr)_430px]">
        <RuntimeBindingsTable
          bindings={summary.bindings}
          onNavigate={onNavigate}
          onSelectBinding={setSelectedBindingId}
          selectedBindingId={selectedBinding?.id ?? null}
        />
        <SnapshotDetailPanel binding={selectedBinding} summary={summary} onNavigate={onNavigate} />
      </MasterDetailLayout>

      <SnapshotHistory history={summary.history} onNavigate={onNavigate} />
    </ConsolePage>
  );
}


function SchemaSnapshotsTree({ summary, onNavigate }: { summary: SnapshotSummary; onNavigate: (section: AppSection) => void }) {
  const profilesQuery = useQuery({ queryKey: ["schema-snapshots", "profiles"], queryFn: listProfiles });
  const bindingsQuery = useQuery({ queryKey: ["schema-snapshots", "bindings"], queryFn: () => listElasticsearchBindings() });
  const profiles = profilesQuery.data ?? [];
  const bindings = bindingsQuery.data ?? [];
  const [selectedProfileName, setSelectedProfileName] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<SchemaNode | null>(null);
  const [mode, setMode] = useState<SchemaTreeMode>("schema");

  useEffect(() => {
    if (!selectedProfileName && profiles.length > 0) {
      setSelectedProfileName(profiles[0].name);
    }
  }, [profiles, selectedProfileName]);

  const termsQuery = useQuery({
    queryKey: ["schema-snapshots", "terms", selectedProfileName],
    queryFn: () => listTerms(selectedProfileName ?? ""),
    enabled: Boolean(selectedProfileName),
  });

  const selectedProfile = useMemo(
    () => profiles.find((profile) => profile.name === selectedProfileName) ?? profiles[0] ?? null,
    [profiles, selectedProfileName],
  );
  const terms = termsQuery.data ?? [];
  const bindingsForProfile = bindings.filter((binding) => binding.profile_name === selectedProfile?.name);
  const snapshotBindingsForProfile = summary.bindings.filter((binding) => binding.profile_name === selectedProfile?.name);
  const categories = useMemo(() => groupTermsBySlot(terms), [terms]);
  const ambiguityCount = countDuplicateAliases(terms);

  useEffect(() => {
    if (!selectedNode && selectedProfile) {
      setSelectedNode({ kind: "profile", profile: selectedProfile });
    }
  }, [selectedNode, selectedProfile]);

  const loading = profilesQuery.isLoading || bindingsQuery.isLoading;
  const error = profilesQuery.error ?? bindingsQuery.error ?? termsQuery.error;

  return (
    <SectionCard
      actions={(
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => setMode("schema")} variant={mode === "schema" ? "primary" : "secondary"}>
            <Network className="mr-2 h-4 w-4" />
            Schema tree
          </Button>
          <Button onClick={() => setMode("snapshots")} variant={mode === "snapshots" ? "primary" : "secondary"}>
            <History className="mr-2 h-4 w-4" />
            Snapshot timeline
          </Button>
        </div>
      )}
      description="Read-only tree view for binding → profile → category → canonical terms → aliases, with snapshot status kept next to the schema."
      title="Schema & snapshots workspace"
    >
      {loading ? (
        <div className="text-sm text-slate-500 dark:text-slate-400">Loading schema tree...</div>
      ) : error ? (
        <div className="flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200">
          <AlertCircle className="mt-0.5 h-4 w-4 flex-none" />
          <div>{error instanceof Error ? error.message : "Unable to load schema tree."}</div>
        </div>
      ) : profiles.length === 0 ? (
        <EmptyState
          actionLabel={areLegacyWriteToolsEnabled() ? "Open Terms" : "Use GitOps/import flow"}
          description={areLegacyWriteToolsEnabled() ? "Create or import a profile before the schema tree can show canonical terms, aliases, and runtime bindings." : "No profiles are available yet. Import terminology through GitOps/API runbooks or review agent proposals before inspecting the schema tree."}
          onAction={areLegacyWriteToolsEnabled() ? () => onNavigate("terms") : undefined}
          title="No profiles yet"
        />
      ) : (
        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <MetricPill helper="governance scopes" icon={Database} label="Profiles" tone="cyan" value={profiles.length} />
            <MetricPill helper="runtime contexts" icon={Plug} label="Bindings" tone={bindings.length > 0 ? "emerald" : "slate"} value={bindings.length} />
            <MetricPill helper="selected profile" icon={Tags} label="Canonical terms" tone={terms.length > 0 ? "violet" : "slate"} value={terms.length} />
            <MetricPill helper="duplicate alias values" icon={TriangleAlert} label="Ambiguities" tone={ambiguityCount > 0 ? "amber" : "emerald"} value={ambiguityCount} />
          </div>

          <div className="grid gap-4 xl:grid-cols-[minmax(320px,0.92fr)_minmax(0,1.08fr)]">
            <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-3 dark:border-slate-800 dark:bg-slate-900/35">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Selected profile</div>
                  <div className="mt-1 text-sm font-medium text-slate-950 dark:text-slate-50">{selectedProfile?.name}</div>
                </div>
                <select
                  className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 shadow-sm dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100"
                  onChange={(event) => {
                    const nextProfile = profiles.find((profile) => profile.name === event.target.value) ?? null;
                    setSelectedProfileName(event.target.value);
                    setSelectedNode(nextProfile ? { kind: "profile", profile: nextProfile } : null);
                  }}
                  value={selectedProfile?.name ?? ""}
                >
                  {profiles.map((profile) => (
                    <option key={profile.id} value={profile.name}>{profile.name}</option>
                  ))}
                </select>
              </div>

              <div className="mt-4 max-h-[640px] overflow-auto rounded-2xl border border-slate-200 bg-white p-2 dark:border-slate-800 dark:bg-slate-950">
                {mode === "schema" ? (
                  <SchemaTree
                    bindings={bindingsForProfile}
                    categories={categories}
                    profile={selectedProfile}
                    selectedNode={selectedNode}
                    setSelectedNode={setSelectedNode}
                  />
                ) : (
                  <SnapshotTree
                    bindings={snapshotBindingsForProfile}
                    selectedNode={selectedNode}
                    setSelectedNode={setSelectedNode}
                  />
                )}
              </div>
            </div>

            <SchemaNodeDetail node={selectedNode} onNavigate={onNavigate} summary={summary} />
          </div>
        </div>
      )}
    </SectionCard>
  );
}

function SchemaTree({ bindings, categories, profile, selectedNode, setSelectedNode }: {
  bindings: ElasticsearchBinding[];
  categories: Array<{ slot: string; terms: CanonicalTerm[] }>;
  profile: Profile | null;
  selectedNode: SchemaNode | null;
  setSelectedNode: (node: SchemaNode) => void;
}) {
  if (!profile) {
    return <div className="p-4 text-sm text-slate-500 dark:text-slate-400">No profile selected.</div>;
  }

  return (
    <div className="space-y-2 text-sm">
      <TreeButton
        active={selectedNode?.kind === "profile" && selectedNode.profile.id === profile.id}
        depth={0}
        icon={<Database className="h-4 w-4" />}
        label={`Profile: ${profile.name}`}
        meta={`${categories.reduce((total, category) => total + category.terms.length, 0)} terms`}
        onClick={() => setSelectedNode({ kind: "profile", profile })}
      />

      <div className="space-y-1">
        <div className="px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400 dark:text-slate-500">Runtime bindings</div>
        {bindings.length === 0 ? (
          <TreeEmptyLine depth={1} label="No bindings for this profile" />
        ) : bindings.map((binding) => (
          <TreeButton
            active={selectedNode?.kind === "binding" && selectedNode.binding.id === binding.id}
            depth={1}
            icon={<Plug className="h-4 w-4" />}
            key={binding.id}
            label={`Binding: ${binding.name}`}
            meta={binding.index_name}
            onClick={() => setSelectedNode({ kind: "binding", binding })}
          />
        ))}
      </div>

      <div className="space-y-1">
        <div className="px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400 dark:text-slate-500">Terminology tree</div>
        {categories.length === 0 ? (
          <TreeEmptyLine depth={1} label="No canonical terms yet" />
        ) : categories.map((category) => (
          <div key={category.slot}>
            <TreeButton
              active={selectedNode?.kind === "category" && selectedNode.slot === category.slot}
              depth={1}
              icon={<Tags className="h-4 w-4" />}
              label={`Category: ${category.slot}`}
              meta={`${category.terms.length} terms`}
              onClick={() => setSelectedNode({ kind: "category", profileName: profile.name, slot: category.slot, terms: category.terms })}
            />
            <div className="space-y-1">
              {category.terms.map((term) => (
                <div key={term.id}>
                  <TreeButton
                    active={selectedNode?.kind === "term" && selectedNode.term.id === term.id}
                    depth={2}
                    icon={<CircleDashed className="h-4 w-4" />}
                    label={`Canonical: ${term.canonical_value}`}
                    meta={`${term.aliases.length} aliases`}
                    onClick={() => setSelectedNode({ kind: "term", profileName: profile.name, term })}
                  />
                  {term.aliases.length === 0 ? <TreeEmptyLine depth={3} label="No aliases" /> : term.aliases.map((alias) => (
                    <TreeButton
                      active={selectedNode?.kind === "alias" && selectedNode.alias.id === alias.id}
                      depth={3}
                      icon={<CheckCircle2 className="h-4 w-4" />}
                      key={alias.id}
                      label={`Alias: ${alias.alias_value}`}
                      meta={`${Math.round(alias.confidence * 100)}%`}
                      onClick={() => setSelectedNode({ kind: "alias", profileName: profile.name, term, alias })}
                    />
                  ))}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function SnapshotTree({ bindings, selectedNode, setSelectedNode }: {
  bindings: SnapshotBindingState[];
  selectedNode: SchemaNode | null;
  setSelectedNode: (node: SchemaNode) => void;
}) {
  if (bindings.length === 0) {
    return <div className="p-4 text-sm text-slate-500 dark:text-slate-400">No snapshot-tracked bindings for this profile.</div>;
  }
  return (
    <div className="space-y-2 text-sm">
      {bindings.map((binding) => (
        <TreeButton
          active={selectedNode?.kind === "snapshot" && selectedNode.binding.id === binding.id}
          depth={0}
          icon={<GitBranch className="h-4 w-4" />}
          key={binding.id}
          label={`Snapshot: ${binding.name}`}
          meta={binding.active_snapshot_version ?? binding.status}
          onClick={() => setSelectedNode({ kind: "snapshot", binding })}
        />
      ))}
    </div>
  );
}

function SchemaNodeDetail({ node, onNavigate, summary }: { node: SchemaNode | null; onNavigate: (section: AppSection) => void; summary: SnapshotSummary }) {
  if (!node) {
    return (
      <EntityDetailPanel title="Schema detail" description="Select a profile, binding, category, canonical term, alias, or snapshot node.">
        <div className="text-sm text-slate-500 dark:text-slate-400">Nothing selected yet.</div>
      </EntityDetailPanel>
    );
  }

  if (node.kind === "profile") {
    const snapshotBindings = summary.bindings.filter((binding) => binding.profile_name === node.profile.name);
    return (
      <EntityDetailPanel badge={<StatusBadge status="read only" />} title={`Profile: ${node.profile.name}`} description={node.profile.description ?? "Read-only governance profile."}>
        <div className="grid gap-3 sm:grid-cols-2">
          <SnapshotFact label="Normalized" value={node.profile.normalized_name} />
          <SnapshotFact label="Runtime bindings" value={String(snapshotBindings.length)} />
          <SnapshotFact label="Created" value={formatDate(node.profile.created_at)} />
          <SnapshotFact label="Updated" value={formatDate(node.profile.updated_at)} />
        </div>
        <DetailCallout tone="cyan" title="Terminology-as-Code boundary">
          This UI is read-heavy: inspect schema and snapshot state here, but keep canonical edits in agent proposals, API workflows, or GitOps-controlled imports.
        </DetailCallout>
      </EntityDetailPanel>
    );
  }

  if (node.kind === "binding") {
    return (
      <EntityDetailPanel badge={<StatusBadge status={node.binding.snapshot_status ?? node.binding.mode} />} title={`Binding: ${node.binding.name}`} description={`${node.binding.profile_name} → ${node.binding.index_name}`}>
        <div className="grid gap-3 sm:grid-cols-2">
          <SnapshotFact label="Provider" value={node.binding.provider} />
          <SnapshotFact label="Mode" value={node.binding.mode} />
          <SnapshotFact label="Text fields" value={node.binding.text_fields.join(", ")} />
          <SnapshotFact label="Target field" value={node.binding.target_field} />
          <SnapshotFact label="Active snapshot" mono value={node.binding.last_successful_snapshot_version ?? "none"} />
          <SnapshotFact label="Pending snapshot" mono value={node.binding.pending_snapshot_version ?? "none"} />
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => onNavigate("search-playground")} variant="secondary"><Search className="mr-2 h-4 w-4" /> Test in Playground</Button>
          <Button onClick={() => onNavigate("integrations")} variant="secondary"><Plug className="mr-2 h-4 w-4" /> Open integrations</Button>
        </div>
      </EntityDetailPanel>
    );
  }

  if (node.kind === "category") {
    const aliasCount = node.terms.reduce((total, term) => total + term.aliases.length, 0);
    return (
      <EntityDetailPanel badge={<Badge>{node.terms.length} terms</Badge>} title={`Category: ${node.slot}`} description={`Virtual folder for ${node.profileName}.`}>
        <div className="grid gap-3 sm:grid-cols-3">
          <SnapshotFact label="Terms" value={String(node.terms.length)} />
          <SnapshotFact label="Aliases" value={String(aliasCount)} />
          <SnapshotFact label="Profile" value={node.profileName} />
        </div>
        <div className="rounded-2xl border border-slate-200 dark:border-slate-800">
          {node.terms.slice(0, 8).map((term) => (
            <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-3 py-2 text-sm last:border-b-0 dark:border-slate-800" key={term.id}>
              <span className="font-medium text-slate-950 dark:text-slate-50">{term.canonical_value}</span>
              <span className="text-xs text-slate-500 dark:text-slate-400">{term.aliases.length} aliases</span>
            </div>
          ))}
        </div>
      </EntityDetailPanel>
    );
  }

  if (node.kind === "term") {
    return (
      <EntityDetailPanel badge={<StatusBadge status={node.term.status} />} title={`Canonical: ${node.term.canonical_value}`} description={node.term.description ?? `Slot ${node.term.slot} in ${node.profileName}.`}>
        <div className="grid gap-3 sm:grid-cols-2">
          <SnapshotFact label="Slot" value={node.term.slot} />
          <SnapshotFact label="Aliases" value={String(node.term.aliases.length)} />
          <SnapshotFact label="Normalized" value={node.term.normalized_value} />
          <SnapshotFact label="Updated" value={formatDate(node.term.updated_at)} />
        </div>
        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Aliases</div>
          <div className="flex flex-wrap gap-2">
            {node.term.aliases.length === 0 ? <Badge>No aliases</Badge> : node.term.aliases.map((alias) => (
              <Badge className="bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" key={alias.id}>{alias.alias_value}</Badge>
            ))}
          </div>
        </div>
      </EntityDetailPanel>
    );
  }

  if (node.kind === "alias") {
    return (
      <EntityDetailPanel badge={<StatusBadge status={node.alias.status} />} title={`Alias: ${node.alias.alias_value}`} description={`Maps to ${node.term.canonical_value}.`}>
        <div className="grid gap-3 sm:grid-cols-2">
          <SnapshotFact label="Canonical" value={node.term.canonical_value} />
          <SnapshotFact label="Slot" value={node.term.slot} />
          <SnapshotFact label="Confidence" value={`${Math.round(node.alias.confidence * 100)}%`} />
          <SnapshotFact label="Normalized" value={node.alias.normalized_alias} />
        </div>
        {node.alias.notes ? <DetailCallout title="Notes">{node.alias.notes}</DetailCallout> : null}
      </EntityDetailPanel>
    );
  }

  return (
    <EntityDetailPanel badge={<StatusBadge status={node.binding.status} />} title={`Snapshot: ${node.binding.name}`} description={`${node.binding.profile_name} → ${node.binding.index_name}`}>
      <div className="grid gap-3 sm:grid-cols-2">
        <SnapshotFact label="Active version" mono value={node.binding.active_snapshot_version ?? "none"} />
        <SnapshotFact label="Pending version" mono value={node.binding.pending_snapshot_version ?? "none"} />
        <SnapshotFact label="Snapshot aliases" value={String(node.binding.snapshot_aliases_total)} />
        <SnapshotFact label="Current aliases" value={String(node.binding.current_aliases_total)} />
        <SnapshotFact label="Added / removed" value={`+${node.binding.diff.added_aliases} / -${node.binding.diff.removed_aliases}`} />
        <SnapshotFact label="Rollback" value={node.binding.rollback_available ? "available" : "not available"} />
      </div>
      {node.binding.diff.changed ? (
        <DetailCallout tone="amber" title="Profile drift detected">
          This binding has schema changes that are not represented by the active runtime snapshot yet. Use Playground compare before release.
        </DetailCallout>
      ) : (
        <DetailCallout tone="emerald" title="Snapshot aligned">
          Active runtime snapshot matches the current profile alias checksum for this binding.
        </DetailCallout>
      )}
    </EntityDetailPanel>
  );
}

function TreeButton({ active, depth, icon, label, meta, onClick }: { active: boolean; depth: number; icon: ReactNode; label: string; meta?: string; onClick: () => void }) {
  return (
    <button
      className={`flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2 text-left transition-colors ${active ? "bg-slate-950 text-white dark:bg-slate-100 dark:text-slate-950" : "text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-900"}`}
      onClick={onClick}
      style={{ paddingLeft: `${0.75 + depth * 1.1}rem` }}
      type="button"
    >
      <span className="flex min-w-0 items-center gap-2">
        <span className="shrink-0 opacity-80">{icon}</span>
        <span className="truncate font-medium">{label}</span>
      </span>
      {meta ? <span className={`shrink-0 text-xs ${active ? "text-white/75 dark:text-slate-950/65" : "text-slate-500 dark:text-slate-400"}`}>{meta}</span> : null}
    </button>
  );
}

function TreeEmptyLine({ depth, label }: { depth: number; label: string }) {
  return (
    <div className="rounded-xl px-3 py-2 text-xs text-slate-400 dark:text-slate-500" style={{ paddingLeft: `${0.75 + depth * 1.1}rem` }}>
      {label}
    </div>
  );
}

function DetailCallout({ children, title, tone = "slate" }: { children: ReactNode; title: string; tone?: "slate" | "cyan" | "emerald" | "amber" }) {
  const classes = tone === "emerald"
    ? "border-emerald-100 bg-emerald-50 text-emerald-800 dark:border-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-200"
    : tone === "amber"
      ? "border-amber-100 bg-amber-50 text-amber-800 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-200"
      : tone === "cyan"
        ? "border-cyan-100 bg-cyan-50 text-cyan-800 dark:border-cyan-500/20 dark:bg-cyan-500/10 dark:text-cyan-200"
        : "border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-800 dark:bg-slate-900/60 dark:text-slate-300";
  return (
    <div className={`rounded-2xl border p-4 text-sm ${classes}`}>
      <div className="font-semibold">{title}</div>
      <div className="mt-1 leading-6">{children}</div>
    </div>
  );
}

function groupTermsBySlot(terms: CanonicalTerm[]) {
  const groups = new Map<string, CanonicalTerm[]>();
  for (const term of terms) {
    const slot = term.slot || "Uncategorized";
    groups.set(slot, [...(groups.get(slot) ?? []), term]);
  }
  return Array.from(groups.entries())
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([slot, groupedTerms]) => ({
      slot,
      terms: [...groupedTerms].sort((left, right) => left.canonical_value.localeCompare(right.canonical_value)),
    }));
}

function countDuplicateAliases(terms: CanonicalTerm[]) {
  const aliases = new Map<string, Set<string>>();
  for (const term of terms) {
    for (const alias of term.aliases) {
      const key = alias.normalized_alias || alias.alias_value.toLowerCase();
      const values = aliases.get(key) ?? new Set<string>();
      values.add(term.canonical_value);
      aliases.set(key, values);
    }
  }
  return Array.from(aliases.values()).filter((values) => values.size > 1).length;
}

function formatDate(value: string | null) {
  if (!value) {
    return "—";
  }
  return new Date(value).toLocaleString();
}


function RuntimeSnapshotsHeader({ summary, onNavigate }: { summary: SnapshotSummary; onNavigate: (section: AppSection) => void }) {
  const auditLevel = getAuditLevel(summary);
  const progress = summary.counts.bindings > 0
    ? Math.round((summary.counts.active_snapshots / summary.counts.bindings) * 100)
    : 0;
  const pendingTotal = summary.counts.stale_snapshots + summary.counts.pending_snapshots;

  return (
    <WorkspaceHeader
      actions={(
        <>
          <Button onClick={() => onNavigate("integrations")} variant="secondary">
            <Plug className="mr-2 h-4 w-4" />
            Manage bindings
          </Button>
          <Button onClick={() => onNavigate("search-playground")} variant="secondary">
            <GitBranch className="mr-2 h-4 w-4" />
            Test runtime
          </Button>
        </>
      )}
      description="Audit immutable terminology versions, profile drift, and enrichment rollouts before runtime search or RAG traffic uses them."
      eyebrow="Runtime audit"
      meta={(
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <MetricPill
            helper="runtime contexts"
            icon={Layers3}
            label="Tracked bindings"
            tone="cyan"
            value={summary.counts.bindings}
          />
          <MetricPill
            helper={`${progress}% with snapshots`}
            icon={ShieldCheck}
            label="Ready snapshots"
            tone={progress === 100 && summary.counts.bindings > 0 ? "emerald" : "amber"}
            value={summary.counts.active_snapshots}
          />
          <MetricPill
            helper="needs rollout"
            icon={TriangleAlert}
            label="Stale / pending"
            tone={pendingTotal > 0 ? "amber" : "slate"}
            value={pendingTotal}
          />
          <MetricPill
            helper="available jobs"
            icon={RotateCcw}
            label="Rollback"
            tone={summary.counts.rollback_available > 0 ? "violet" : "slate"}
            value={summary.counts.rollback_available}
          />
        </div>
      )}
      title="Snapshot release cockpit"
    >
      <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50/80 p-4 dark:border-slate-800 dark:bg-slate-900/45">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex min-w-0 items-start gap-3">
            <div className="flex h-10 w-10 flex-none items-center justify-center rounded-2xl bg-slate-950 text-white dark:bg-slate-50 dark:text-slate-950">
              <Sparkles className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-sm font-semibold text-slate-950 dark:text-slate-50">Release safety</h3>
                <AuditBadge level={auditLevel} />
              </div>
              <p className="mt-1 text-sm leading-6 text-slate-600 dark:text-slate-300">
                Profile → snapshot → binding → runtime search. Search keeps using the last successful snapshot until a new enrichment job activates one.
              </p>
            </div>
          </div>
          <div className="min-w-[180px] shrink-0">
            <div className="flex items-center justify-between text-xs font-medium text-slate-500 dark:text-slate-400">
              <span>Runtime readiness</span>
              <span>{progress}%</span>
            </div>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-white dark:bg-slate-800">
              <div className="h-full rounded-full bg-emerald-500 transition-[width]" style={{ width: `${progress}%` }} />
            </div>
          </div>
        </div>
      </div>
    </WorkspaceHeader>
  );
}

function RuntimeBindingsTable({
  bindings,
  onNavigate,
  onSelectBinding,
  selectedBindingId,
}: {
  bindings: SnapshotBindingState[];
  onNavigate: (section: AppSection) => void;
  onSelectBinding: (bindingId: number) => void;
  selectedBindingId: number | null;
}) {
  return (
    <SectionCard
      actions={<Badge className="bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">{bindings.length} bindings</Badge>}
      description="Active snapshot, drift, and latest rollout per search context."
      title="Runtime bindings"
    >
      {bindings.length === 0 ? (
        <EmptyState
          actionLabel="Create binding"
          description="Create an Elasticsearch binding before runtime snapshots can be tracked."
          onAction={() => onNavigate("integrations")}
          title="No runtime contexts yet"
        />
      ) : (
        <div className="overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-800">
          <div className="max-h-[560px] overflow-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
              <thead className="sticky top-0 z-10 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-950 dark:text-slate-400">
                <tr>
                  <th className="px-4 py-3 font-medium">Binding</th>
                  <th className="px-4 py-3 font-medium">Runtime snapshot</th>
                  <th className="px-4 py-3 font-medium">Drift</th>
                  <th className="px-4 py-3 font-medium">Latest job</th>
                  <th className="px-4 py-3 font-medium">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white dark:divide-slate-800 dark:bg-slate-900">
                {bindings.map((binding) => {
                  const selected = binding.id === selectedBindingId;
                  return (
                    <tr
                      className={selected ? "bg-cyan-50/70 dark:bg-cyan-500/10" : undefined}
                      key={binding.id}
                    >
                      <td className="px-4 py-3 align-top">
                        <button
                          className="block w-full rounded-xl text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500"
                          onClick={() => onSelectBinding(binding.id)}
                          type="button"
                        >
                          <div className="flex flex-wrap items-center gap-2">
                            <div className="font-medium text-slate-950 dark:text-slate-50">{binding.name}</div>
                            <StatusBadge status={binding.status} />
                          </div>
                          <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                            {binding.profile_name} → {binding.index_name}
                          </div>
                          {binding.filter_field && binding.filter_value ? (
                            <div className="mt-1 text-xs text-slate-400 dark:text-slate-500">
                              scope: {binding.filter_field} = {binding.filter_value}
                            </div>
                          ) : null}
                        </button>
                      </td>
                      <td className="max-w-[300px] px-4 py-3 align-top text-xs text-slate-500 dark:text-slate-400">
                        <div className="truncate font-mono text-slate-700 dark:text-slate-300" title={binding.active_snapshot_version ?? "Not created"}>
                          {binding.active_snapshot_version ?? "Not created"}
                        </div>
                        {binding.pending_snapshot_version ? (
                          <div className="mt-1 truncate" title={binding.pending_snapshot_version}>Pending: {binding.pending_snapshot_version}</div>
                        ) : null}
                        <div className="mt-1">Aliases: {binding.snapshot_aliases_total} active / {binding.current_aliases_total} current</div>
                      </td>
                      <td className="px-4 py-3 align-top">
                        <DiffBadge binding={binding} />
                      </td>
                      <td className="px-4 py-3 align-top text-xs text-slate-500 dark:text-slate-400">
                        {binding.latest_job_id ? (
                          <div className="space-y-1">
                            <div>Job #{binding.latest_job_id}</div>
                            <StatusBadge status={binding.latest_job_status ?? "unknown"} />
                            {binding.latest_job_error ? <div className="text-red-600 dark:text-red-300">{binding.latest_job_error}</div> : null}
                          </div>
                        ) : (
                          "No jobs"
                        )}
                      </td>
                      <td className="px-4 py-3 align-top">
                        {binding.rollback_available ? (
                          <Badge className="whitespace-nowrap bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
                            <RotateCcw className="mr-1 h-3 w-3" /> rollback
                          </Badge>
                        ) : binding.status === "stale" || binding.pending_snapshot_version ? (
                          <Button onClick={() => onNavigate("integrations")} variant="secondary">
                            Roll out
                          </Button>
                        ) : (
                          <Button onClick={() => onNavigate("search-playground")} variant="ghost">
                            Test
                          </Button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </SectionCard>
  );
}

function SnapshotDetailPanel({
  binding,
  onNavigate,
  summary,
}: {
  binding: SnapshotBindingState | null;
  onNavigate: (section: AppSection) => void;
  summary: SnapshotSummary;
}) {
  if (!binding) {
    return (
      <EntityDetailPanel
        footer={(
          areLegacyWriteToolsEnabled() ? (
          <Button className="w-full" onClick={() => onNavigate("integrations")} variant="secondary">
            Create binding
          </Button>
        ) : (
          <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
            {LEGACY_WRITE_TOOLS_LOCKED_MESSAGE}
          </div>
        )
        )}
        title="Snapshot release detail"
      >
        {summary.counts.bindings === 0 ? (
          <EmptyState
            actionLabel={areLegacyWriteToolsEnabled() ? "Create binding" : "Binding setup is GitOps-managed"}
            description={areLegacyWriteToolsEnabled() ? "Snapshots start after a profile is bound to an Elasticsearch search context." : "Snapshots start after a binding is provisioned by the deployment/API runbook. Manual binding creation is locked in the Control Plane UI."}
            onAction={areLegacyWriteToolsEnabled() ? () => onNavigate("integrations") : undefined}
            title="No bindings yet"
          />
        ) : null}
      </EntityDetailPanel>
    );
  }

  const needsAttention = binding.status === "failed" ||
    binding.status === "stale" ||
    binding.status === "updating" ||
    binding.status === "never_enriched" ||
    Boolean(binding.pending_snapshot_version);

  return (
    <EntityDetailPanel
      badge={<StatusBadge status={binding.status} />}
      description={`${binding.profile_name} → ${binding.index_name}`}
      footer={(
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
          <Button onClick={() => onNavigate("integrations")} variant={needsAttention ? "primary" : "secondary"}>
            <Plug className="mr-2 h-4 w-4" />
            Open jobs
          </Button>
          <Button onClick={() => onNavigate("search-playground")} variant="secondary">
            <GitBranch className="mr-2 h-4 w-4" />
            Test query
          </Button>
        </div>
      )}
      title={binding.name}
    >
      {needsAttention ? (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-amber-700 dark:text-amber-200">Needs attention</div>
          <div className="mt-2 flex items-center gap-2 font-semibold">
            <TriangleAlert className="h-4 w-4" />
            {binding.name} needs runtime attention
          </div>
          <div className="mt-2 text-xs leading-5">
            Status: {binding.status.replace(/_/g, " ")}. Search keeps using the active snapshot until a successful enrichment job activates a new one.
          </div>
        </div>
      ) : (
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/40 dark:text-emerald-200">
          <div className="flex items-center gap-2 font-semibold">
            <CheckCircle2 className="h-4 w-4" />
            Runtime state looks clean
          </div>
          <div className="mt-2 text-xs leading-5">The binding is serving the current active snapshot without known drift.</div>
        </div>
      )}

      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
        <SnapshotFact label="Profile" value={binding.profile_name} />
        <SnapshotFact label="Index" value={binding.index_name} />
        <SnapshotFact label="Active snapshot" value={binding.active_snapshot_version ?? "Not created"} mono />
        <SnapshotFact label="Pending snapshot" value={binding.pending_snapshot_version ?? "None"} mono />
        <SnapshotFact label="Snapshot aliases" value={String(binding.snapshot_aliases_total)} />
        <SnapshotFact label="Current aliases" value={String(binding.current_aliases_total)} />
      </div>

      <div className="rounded-2xl border border-slate-200 p-4 text-sm dark:border-slate-800">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="font-semibold text-slate-950 dark:text-slate-50">Profile drift</div>
            <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">Compare the active runtime snapshot with the current profile state.</div>
          </div>
          <DiffBadge binding={binding} />
        </div>
        <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
          <div className="rounded-xl bg-emerald-50 px-2 py-2 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-200">
            +{binding.diff.added_aliases}
            <div className="mt-1 text-[10px] uppercase tracking-wide">added</div>
          </div>
          <div className="rounded-xl bg-red-50 px-2 py-2 text-red-700 dark:bg-red-500/10 dark:text-red-200">
            -{binding.diff.removed_aliases}
            <div className="mt-1 text-[10px] uppercase tracking-wide">removed</div>
          </div>
          <div className="rounded-xl bg-amber-50 px-2 py-2 text-amber-700 dark:bg-amber-500/10 dark:text-amber-200">
            {binding.diff.changed_aliases}
            <div className="mt-1 text-[10px] uppercase tracking-wide">changed</div>
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 p-4 text-sm dark:border-slate-800">
        <div className="font-semibold text-slate-950 dark:text-slate-50">Latest job</div>
        {binding.latest_job_id ? (
          <div className="mt-3 space-y-2 text-xs text-slate-500 dark:text-slate-400">
            <div className="flex items-center justify-between gap-3">
              <span>Job</span>
              <span className="font-medium text-slate-800 dark:text-slate-200">#{binding.latest_job_id}</span>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span>Status</span>
              <StatusBadge status={binding.latest_job_status ?? "unknown"} />
            </div>
            {binding.latest_job_error ? <div className="text-red-600 dark:text-red-300">{binding.latest_job_error}</div> : null}
          </div>
        ) : (
          <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">No enrichment jobs have published a snapshot for this binding yet.</p>
        )}
      </div>
    </EntityDetailPanel>
  );
}

function DiffBadge({ binding }: { binding: SnapshotBindingState }) {
  if (!binding.active_snapshot_version) {
    return (
      <div className="flex items-center gap-2 whitespace-nowrap text-xs text-slate-500 dark:text-slate-400">
        <CircleDashed className="h-4 w-4" />
        no active snapshot
      </div>
    );
  }
  if (!binding.diff.changed) {
    return (
      <div className="flex items-center gap-2 whitespace-nowrap text-xs text-emerald-700 dark:text-emerald-300">
        <CheckCircle2 className="h-4 w-4" />
        matches current profile
      </div>
    );
  }
  return (
    <div className="space-y-1 text-xs text-amber-700 dark:text-amber-300">
      <div className="flex items-center gap-2 whitespace-nowrap font-medium">
        <TriangleAlert className="h-4 w-4" />
        profile changed
      </div>
      <div className="whitespace-nowrap">+{binding.diff.added_aliases} / -{binding.diff.removed_aliases} / changed {binding.diff.changed_aliases}</div>
    </div>
  );
}

function SnapshotHistory({ history, onNavigate }: { history: SnapshotHistoryItem[]; onNavigate: (section: AppSection) => void }) {
  return (
    <SectionCard
      actions={(
        <Button onClick={() => onNavigate(areLegacyWriteToolsEnabled() ? "integrations" : "search-playground")} variant="secondary">
          <History className="mr-2 h-4 w-4" />
          {areLegacyWriteToolsEnabled() ? "View jobs" : "Test runtime"}
        </Button>
      )}
      description="Last enrichment jobs that produced, activated, or failed runtime versions."
      title="Recent snapshot events"
    >
      {history.length === 0 ? (
        <EmptyState
          actionLabel={areLegacyWriteToolsEnabled() ? "Run enrichment" : "Open Playground"}
          description={areLegacyWriteToolsEnabled() ? "No snapshot-producing enrichment jobs have run yet. Start a job from Integrations after switching a binding to write mode." : "No snapshot-producing jobs have run yet. Trigger enrichment through a controlled runbook/CI flow, then verify canonicalization in Playground."}
          onAction={() => onNavigate(areLegacyWriteToolsEnabled() ? "integrations" : "search-playground")}
          title="No snapshot history yet"
        />
      ) : (
        <div className="overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-800">
          <div className="max-h-[480px] overflow-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
              <thead className="sticky top-0 z-10 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-950 dark:text-slate-400">
                <tr>
                  <th className="px-4 py-3 font-medium">Job</th>
                  <th className="px-4 py-3 font-medium">Binding</th>
                  <th className="px-4 py-3 font-medium">Snapshot</th>
                  <th className="px-4 py-3 font-medium">Docs</th>
                  <th className="px-4 py-3 font-medium">Rollout</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white dark:divide-slate-800 dark:bg-slate-900">
                {history.map((item) => (
                  <tr key={item.job_id}>
                    <td className="px-4 py-3 align-top">
                      <div className="font-medium text-slate-950 dark:text-slate-50">Job #{item.job_id}</div>
                      <div className="mt-1"><StatusBadge status={item.status} /></div>
                      {item.error_message ? <div className="mt-2 text-xs text-red-600 dark:text-red-300">{item.error_message}</div> : null}
                    </td>
                    <td className="px-4 py-3 align-top">
                      <div className="font-medium text-slate-950 dark:text-slate-50">{item.binding_name}</div>
                      <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{item.profile_name}</div>
                    </td>
                    <td className="max-w-[300px] px-4 py-3 align-top text-xs text-slate-500 dark:text-slate-400">
                      <div className="truncate font-mono text-slate-700 dark:text-slate-300" title={item.snapshot_version ?? "No snapshot version"}>
                        {item.snapshot_version ?? "No snapshot version"}
                      </div>
                      {item.previous_snapshot_version ? <div className="mt-1 truncate" title={item.previous_snapshot_version}>Previous: {item.previous_snapshot_version}</div> : null}
                      {item.checksum ? <div className="mt-1">checksum {item.checksum.slice(0, 12)}</div> : null}
                    </td>
                    <td className="px-4 py-3 align-top text-xs text-slate-500 dark:text-slate-400">
                      <div>Seen: {item.documents_seen}</div>
                      <div>Enriched: {item.documents_enriched}</div>
                      <div>Failed: {item.documents_failed}</div>
                    </td>
                    <td className="px-4 py-3 align-top text-xs text-slate-500 dark:text-slate-400">
                      {item.rollback_available ? <StatusBadge status="rollback available" /> : null}
                      {item.alias_name ? <div className="mt-1 truncate" title={item.alias_name}>Alias: {item.alias_name}</div> : null}
                      {item.target_index ? <div className="truncate" title={item.target_index}>Target: {item.target_index}</div> : null}
                      <div className="mt-1">Aliases: {item.alias_entries_total}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </SectionCard>
  );
}

function EmptyState({ actionLabel, description, onAction, title }: { actionLabel: string; description: string; onAction?: () => void; title: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 p-6 text-center dark:border-slate-700">
      <FileJson className="mx-auto h-6 w-6 text-slate-400" />
      <div className="mt-2 text-sm font-medium text-slate-950 dark:text-slate-50">{title}</div>
      <p className="mx-auto mt-1 max-w-md text-sm text-slate-500 dark:text-slate-400">{description}</p>
      {onAction ? (
        <Button className="mt-4" onClick={onAction} variant="secondary">
          {actionLabel}
        </Button>
      ) : (
        <div className="mx-auto mt-4 max-w-lg rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
          {actionLabel}
        </div>
      )}
    </div>
  );
}

function SnapshotFact({ label, mono = false, value }: { label: string; mono?: boolean; value: string }) {
  return (
    <div className="min-w-0 rounded-xl border border-slate-200 px-3 py-2 dark:border-slate-800">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</div>
      <div
        className={
          mono
            ? "mt-1 truncate font-mono text-xs text-slate-800 dark:text-slate-200"
            : "mt-1 truncate text-sm font-medium text-slate-950 dark:text-slate-50"
        }
        title={value}
      >
        {value}
      </div>
    </div>
  );
}

function AuditBadge({ level }: { level: RuntimeAuditLevel }) {
  if (level === "ready") {
    return <Badge className="whitespace-nowrap bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">clean</Badge>;
  }
  if (level === "attention") {
    return <Badge className="whitespace-nowrap bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300">needs attention</Badge>;
  }
  return <Badge className="whitespace-nowrap">not started</Badge>;
}

function StatusBadge({ status }: { status: string }) {
  const normalized = status.replace(/_/g, " ");
  const tone = status === "rollback available" ? "amber" : getConsoleToneForStatus(status);
  const className =
    tone === "emerald"
      ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
      : tone === "red"
        ? "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300"
        : tone === "amber"
          ? "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
          : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300";

  return <Badge className={`${className} whitespace-nowrap`}>{normalized}</Badge>;
}

function getAuditLevel(summary: SnapshotSummary): RuntimeAuditLevel {
  if (summary.counts.bindings === 0) {
    return "empty";
  }
  if (summary.counts.stale_snapshots > 0 || summary.counts.pending_snapshots > 0 || summary.counts.failed_updates > 0 || summary.counts.never_enriched > 0) {
    return "attention";
  }
  return "ready";
}

function getAttentionBinding(bindings: SnapshotBindingState[]) {
  return bindings.find((binding) =>
    binding.status === "failed" ||
    binding.status === "stale" ||
    binding.status === "updating" ||
    binding.status === "never_enriched" ||
    Boolean(binding.pending_snapshot_version),
  );
}
