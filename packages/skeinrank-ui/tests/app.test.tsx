import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/App";
import type {
  ApiToken,
  AuthUser,
  CanonicalTerm,
  DashboardSummary,
  ElasticsearchBinding,
  ElasticsearchBindingDryRunResponse,
  ElasticsearchEnrichmentJob,
  ElasticsearchEvidenceResponse,
  ElasticsearchIndex,
  ElasticsearchIndexMapping,
  GlobalStopListEntry,
  GovernanceSuggestion,
  Profile,
  RuntimeQueryPlanResponse,
  RuntimeSearchResponse,
  ServiceAccount,
  SnapshotSummary,
  StopListEntry,
  TermAlias,
} from "../src/types";

const adminUser: AuthUser = {
  id: 1,
  username: "admin",
  normalized_username: "admin",
  display_name: "Admin User",
  role: "admin",
  status: "active",
  is_active: true,
  created_at: "2026-05-05T00:00:00Z",
  updated_at: "2026-05-05T00:00:00Z",
  last_login_at: "2026-05-05T00:00:00Z",
};

const moderatorUser: AuthUser = {
  ...adminUser,
  id: 2,
  username: "moderator",
  normalized_username: "moderator",
  display_name: "Moderator User",
  role: "moderator",
};

const contributorUser: AuthUser = {
  ...adminUser,
  id: 3,
  username: "contributor",
  normalized_username: "contributor",
  display_name: "Contributor User",
  role: "contributor",
};

const personalApiTokens: ApiToken[] = [
  {
    id: 1,
    name: "Existing Jupyter token",
    token_prefix: "sk_pat_existing",
    scopes: ["migration:validate", "migration:export"],
    owner_type: "personal",
    owner_name: "admin",
    expires_at: "2026-08-01T00:00:00Z",
    revoked_at: null,
    last_used_at: "2026-05-08T00:00:00Z",
    created_by: "admin",
    created_at: "2026-05-07T00:00:00Z",
    updated_at: "2026-05-07T00:00:00Z",
  },
];

const serviceAccounts: ServiceAccount[] = [
  {
    id: 1,
    name: "migration-bot",
    normalized_name: "migration_bot",
    display_name: "Migration Bot",
    description: "Dictionary migration automation account",
    role: "admin",
    is_active: true,
    created_by: "admin",
    last_used_at: null,
    created_at: "2026-05-09T00:00:00Z",
    updated_at: "2026-05-09T00:00:00Z",
  },
];

const serviceAccountTokens: ApiToken[] = [
  {
    id: 11,
    name: "CI import token",
    token_prefix: "sk_sat_existing",
    scopes: ["migration:validate", "migration:apply", "migration:export"],
    owner_type: "service_account",
    owner_name: "migration-bot",
    expires_at: "2026-08-01T00:00:00Z",
    revoked_at: null,
    last_used_at: null,
    created_by: "admin",
    created_at: "2026-05-09T00:00:00Z",
    updated_at: "2026-05-09T00:00:00Z",
  },
];

const profiles: Profile[] = [
  {
    id: 1,
    name: "default_it",
    normalized_name: "default_it",
    description: "Default IT terms",
    created_at: "2026-05-04T00:00:00Z",
    updated_at: "2026-05-04T00:00:00Z",
  },
  {
    id: 2,
    name: "ml_platform",
    normalized_name: "ml_platform",
    description: "ML platform terminology",
    created_at: "2026-05-04T00:00:00Z",
    updated_at: "2026-05-04T00:00:00Z",
  },
];

const terms: CanonicalTerm[] = [
  {
    id: 1,
    canonical_value: "kubernetes",
    normalized_value: "kubernetes",
    slot: "TOOL",
    status: "active",
    description: null,
    aliases: [
      {
        id: 1,
        alias_value: "k8s",
        normalized_alias: "k8s",
        status: "active",
        confidence: 0.97,
        notes: null,
        created_at: "2026-05-04T00:00:00Z",
        updated_at: "2026-05-04T00:00:00Z",
      },
    ],
    created_at: "2026-05-04T00:00:00Z",
    updated_at: "2026-05-04T00:00:00Z",
  },
];

const globalStopListEntries: GlobalStopListEntry[] = [
  {
    id: 1,
    value: "unknown",
    normalized_value: "unknown",
    target: "both",
    reason: "Too generic across every profile",
    is_active: true,
    created_at: "2026-05-08T00:00:00Z",
    updated_at: "2026-05-08T00:00:00Z",
  },
  {
    id: 2,
    value: "tmp",
    normalized_value: "tmp",
    target: "alias",
    reason: "Temporary placeholder",
    is_active: false,
    created_at: "2026-05-08T00:00:00Z",
    updated_at: "2026-05-08T00:00:00Z",
  },
];

const stopListEntries: StopListEntry[] = [
  {
    id: 1,
    profile_id: 1,
    value: "service",
    normalized_value: "service",
    target: "alias",
    reason: "Too generic for incident search",
    is_active: true,
    created_at: "2026-05-07T00:00:00Z",
    updated_at: "2026-05-07T00:00:00Z",
  },
];

const elasticsearchBindings: ElasticsearchBinding[] = [
  {
    id: 1,
    profile_id: 1,
    profile_name: "default_it",
    name: "infra docs",
    normalized_name: "infra_docs",
    description: "Apply default IT terms to docs.",
    provider: "elasticsearch",
    index_name: "docs",
    text_fields: ["title", "body"],
    target_field: "skeinrank",
    filter_field: "team",
    filter_value: "infra",
    timestamp_field: "created_at",
    time_window_days: 1825,
    mode: "write",
    write_strategy: "reindex_alias_swap",
    is_enabled: true,
    last_successful_snapshot_version: "default_it@abc123",
    last_successful_snapshot_at: "2026-05-08T10:01:00Z",
    last_successful_job_id: 101,
    pending_snapshot_version: null,
    snapshot_status: "ready",
    created_at: "2026-05-07T00:00:00Z",
    updated_at: "2026-05-07T00:00:00Z",
  },
  {
    id: 2,
    profile_id: 2,
    profile_name: "ml_platform",
    name: "ml docs",
    normalized_name: "ml_docs",
    description: "Apply ML terms to docs.",
    provider: "elasticsearch",
    index_name: "docs",
    text_fields: ["title", "body"],
    target_field: "skeinrank",
    filter_field: "team",
    filter_value: "ml-platform",
    timestamp_field: null,
    time_window_days: null,
    mode: "dry_run",
    write_strategy: "reindex_alias_swap",
    is_enabled: true,
    last_successful_snapshot_version: "ml_platform@old456",
    last_successful_snapshot_at: "2026-05-07T10:01:00Z",
    last_successful_job_id: null,
    pending_snapshot_version: "ml_platform@new789",
    snapshot_status: "stale",
    created_at: "2026-05-07T00:00:00Z",
    updated_at: "2026-05-07T00:00:00Z",
  },
];

const runtimeQueryPlanResponse: RuntimeQueryPlanResponse = {
  profile_name: "default_it",
  normalized_profile_name: "default_it",
  query: "k8s pg timeout",
  canonical_query: "kubernetes postgresql timeout",
  changed: true,
  text_fields: ["title", "body"],
  target_field: "skeinrank",
  binding_id: 1,
  snapshot_version: "default_it@abc123",
  snapshot_source: "binding_runtime_snapshot",
  canonical_values: ["kubernetes", "postgresql"],
  slots: { TOOL: ["kubernetes"], DATABASE: ["postgresql"] },
  matched_aliases: ["k8s", "pg"],
  replacements: [
    {
      alias_value: "k8s",
      canonical_value: "kubernetes",
      slot: "TOOL",
      matched_text: "k8s",
      start: 0,
      end: 3,
      confidence: 0.97,
    },
    {
      alias_value: "pg",
      canonical_value: "postgresql",
      slot: "DATABASE",
      matched_text: "pg",
      start: 4,
      end: 6,
      confidence: 0.92,
    },
  ],
  evidence: [],
  elasticsearch: {
    query: {
      bool: {
        should: [
          {
            multi_match: {
              query: "k8s pg timeout",
              fields: ["title", "body"],
              type: "best_fields",
            },
          },
          {
            terms: {
              "skeinrank.canonical_values": ["kubernetes", "postgresql"],
              boost: 3,
            },
          },
        ],
        minimum_should_match: 1,
      },
    },
    size: 10,
    track_total_hits: true,
  },
  warnings: [],
};

const runtimeSearchResponse: RuntimeSearchResponse = {
  ...runtimeQueryPlanResponse,
  index_name: "docs",
  total: { value: 1, relation: "eq" },
  hits: [
    {
      id: "doc-1",
      index: "docs",
      score: 12.4,
      source: {
        title: "K8s pg timeout incident",
        body: "K8s rollout failed because postgres timed out.",
        skeinrank: {
          canonical_values: ["kubernetes", "postgresql"],
          matched_aliases: ["k8s", "pg"],
        },
      },
      skeinrank: {
        canonical_values: ["kubernetes", "postgresql"],
        matched_aliases: ["k8s", "pg"],
      },
    },
  ],
};

const elasticsearchDryRunResponse: ElasticsearchBindingDryRunResponse = {
  binding: elasticsearchBindings[0],
  limit: 3,
  warnings: [],
  documents: [
    {
      document_id: "doc-1",
      index_name: "docs",
      text_preview: "K8s rollout failed in the infra namespace.",
      source_preview: {
        title: ["K8s rollout failed"],
        body: ["Kube rollout failed"],
        team: ["infra"],
        created_at: ["2026-05-08T00:00:00Z"],
      },
      matched_aliases: [
        {
          alias_value: "k8s",
          canonical_value: "kubernetes",
          slot: "TOOL",
          matched_text: "k8s",
          confidence: 0.97,
        },
      ],
      would_write: {
        skeinrank: {
          profile_id: "default_it",
          binding_id: 1,
          binding_name: "infra docs",
          canonical_values: ["kubernetes"],
          slots: { TOOL: ["kubernetes"] },
          matched_aliases: ["k8s"],
          matched_aliases_by_value: { kubernetes: ["k8s"] },
        },
      },
    },
  ],
};

const elasticsearchJobs: ElasticsearchEnrichmentJob[] = [
  {
    id: 101,
    binding_id: 1,
    profile_id: 1,
    binding_name: "infra docs",
    profile_name: "default_it",
    status: "succeeded",
    write_strategy: "reindex_alias_swap",
    source_index: "docs",
    target_index: "docs__skeinrank_job_101",
    alias_name: "docs",
    snapshot_version: "default_it@abc123",
    previous_snapshot_version: "default_it@old001",
    requested_by: "admin",
    documents_seen: 12,
    documents_enriched: 10,
    documents_failed: 2,
    result_json: {
      updated_document_ids: ["doc-1"],
      errors: ["doc-2 failed"],
      timestamp_field: "created_at",
      time_window_days: 1825,
      chunked_enrichment: {
        chunks_total: 4,
        chunks_completed: 4,
        chunks_failed: 0,
        chunks_cancelled: 0,
      },
      rollout: {
        strategy: "reindex_alias_swap",
        status: "alias_swapped",
        alias_name: "docs",
        source_index: "docs",
        target_index: "docs__skeinrank_job_101",
        previous_alias_indices: ["docs_v1"],
        new_alias_indices: ["docs__skeinrank_job_101"],
        rollback_candidate_index: "docs_v1",
        rollback_available: true,
        alias_swap_completed: true,
        alias_swap_started_at: "2026-05-08T10:00:50Z",
        alias_swapped_at: "2026-05-08T10:00:55Z",
        rollback_hint:
          "Manual rollback candidate: repoint alias docs to docs_v1.",
        cleanup_hint:
          "If this rollout is cancelled or fails before alias swap, review or delete target index docs__skeinrank_job_101.",
      },
    },
    error_message: null,
    started_at: "2026-05-08T10:00:00Z",
    finished_at: "2026-05-08T10:01:00Z",
    created_at: "2026-05-08T10:00:00Z",
    updated_at: "2026-05-08T10:01:00Z",
  },
];

const elasticsearchIndices: ElasticsearchIndex[] = [
  { name: "docs", health: "green", status: "open", docs_count: 42 },
  { name: "runbooks", health: "yellow", status: "open", docs_count: 7 },
];

const elasticsearchMapping: ElasticsearchIndexMapping = {
  index_name: "docs",
  fields: [
    {
      name: "title",
      type: "text",
      is_text_candidate: true,
      is_discriminator_candidate: false,
    },
    {
      name: "body",
      type: "text",
      is_text_candidate: true,
      is_discriminator_candidate: false,
    },
    {
      name: "summary",
      type: "text",
      is_text_candidate: true,
      is_discriminator_candidate: false,
    },
    {
      name: "team",
      type: "keyword",
      is_text_candidate: false,
      is_discriminator_candidate: true,
    },
    {
      name: "space",
      type: "keyword",
      is_text_candidate: false,
      is_discriminator_candidate: true,
    },
    {
      name: "created_at",
      type: "date",
      is_text_candidate: false,
      is_discriminator_candidate: true,
    },
  ],
};

const suggestions: GovernanceSuggestion[] = [
  {
    id: 1,
    profile_id: 1,
    term_id: 1,
    alias_id: null,
    suggestion_type: "alias",
    canonical_value: "kubernetes",
    normalized_canonical: "kubernetes",
    alias_value: "kube",
    normalized_alias: "kube",
    slot: "TOOL",
    description: null,
    confidence: 0.82,
    source: "manual",
    context: "People search for kube in incident docs.",
    status: "pending",
    created_by: "contributor",
    reviewed_by: null,
    review_comment: null,
    reviewed_at: null,
    evidence_snapshot: null,
    evidence_checked_by: null,
    evidence_checked_at: null,
    created_at: "2026-05-06T00:00:00Z",
    updated_at: "2026-05-06T00:00:00Z",
  },
];

const elasticsearchEvidenceResponse: ElasticsearchEvidenceResponse = {
  binding: elasticsearchBindings[0],
  query: "kube",
  normalized_query: "kube",
  canonical_value: "kubernetes",
  max_documents: 5,
  warnings: [],
  documents: [
    {
      document_id: "doc-1",
      index_name: "docs",
      field: "body",
      fragment: "This runbook explains kube rollout failures.",
      highlighted_fragment:
        "This runbook explains <mark>kube</mark> rollout failures.",
      matched_text: "kube",
      match_start: 22,
      match_end: 26,
    },
  ],
};

type StubOptions = {
  authRequired?: boolean;
  currentUser?: AuthUser;
  duplicateTerm?: boolean;
};

function clonePersonalApiTokens() {
  return JSON.parse(JSON.stringify(personalApiTokens)) as ApiToken[];
}

function cloneServiceAccounts() {
  return JSON.parse(JSON.stringify(serviceAccounts)) as ServiceAccount[];
}

function cloneServiceAccountTokens() {
  return JSON.parse(JSON.stringify(serviceAccountTokens)) as ApiToken[];
}

function cloneProfiles() {
  return JSON.parse(JSON.stringify(profiles)) as Profile[];
}

function cloneTerms() {
  return JSON.parse(JSON.stringify(terms)) as CanonicalTerm[];
}

function cloneSuggestions() {
  return JSON.parse(JSON.stringify(suggestions)) as GovernanceSuggestion[];
}

function cloneGlobalStopListEntries() {
  return JSON.parse(
    JSON.stringify(globalStopListEntries),
  ) as GlobalStopListEntry[];
}

function cloneStopListEntries() {
  return JSON.parse(JSON.stringify(stopListEntries)) as StopListEntry[];
}

function cloneElasticsearchBindings() {
  return JSON.parse(
    JSON.stringify(elasticsearchBindings),
  ) as ElasticsearchBinding[];
}

function cloneElasticsearchJobs() {
  return JSON.parse(
    JSON.stringify(elasticsearchJobs),
  ) as ElasticsearchEnrichmentJob[];
}

function dashboardSummaryFromState(
  currentProfiles: Profile[],
  currentTerms: CanonicalTerm[],
  currentElasticsearchBindings: ElasticsearchBinding[],
  currentElasticsearchJobs: ElasticsearchEnrichmentJob[],
): DashboardSummary {
  const latestJobByBinding = new Map<number, ElasticsearchEnrichmentJob>();
  for (const job of currentElasticsearchJobs) {
    if (!latestJobByBinding.has(job.binding_id)) {
      latestJobByBinding.set(job.binding_id, job);
    }
  }

  const bindings = currentElasticsearchBindings.map((binding) => {
    const latestJob = latestJobByBinding.get(binding.id) ?? null;
    const status = dashboardBindingStatus(binding, latestJob);
    return {
      id: binding.id,
      name: binding.name,
      profile_name: binding.profile_name,
      index_name: binding.index_name,
      is_enabled: binding.is_enabled,
      status,
      snapshot_version: binding.last_successful_snapshot_version ?? null,
      pending_snapshot_version: binding.pending_snapshot_version ?? null,
      last_successful_job_id: binding.last_successful_job_id ?? null,
      latest_job: latestJob ? dashboardRecentJob(latestJob) : null,
      updated_at: binding.updated_at,
    };
  });

  const succeededJobs = currentElasticsearchJobs.filter(
    (job) => job.status === "succeeded",
  ).length;
  const readyBindings = bindings.filter(
    (binding) => binding.status === "ready",
  ).length;

  return {
    readiness: {
      database: {
        status: "ok",
        configured: true,
        message: "Database is reachable.",
        url: "sqlite:///test.db",
        name: null,
        version: null,
      },
      elasticsearch: {
        status: "ok",
        configured: true,
        message: "Elasticsearch is reachable.",
        url: "http://localhost:9200",
        name: "skeinrank-dev",
        version: "8.13.4",
      },
      rabbitmq: {
        status: "not_required",
        configured: false,
        message: "Synchronous enrichment backend is active.",
        url: null,
        name: null,
        version: null,
      },
      worker: {
        status: "not_required",
        configured: false,
        message: "Worker is not required for synchronous enrichment jobs.",
        url: null,
        name: null,
        version: null,
      },
      auth: {
        status: "enabled",
        configured: true,
        message: "Authentication is enabled.",
        url: null,
        name: null,
        version: null,
      },
    },
    counts: {
      profiles: currentProfiles.length,
      canonical_terms: currentTerms.length,
      aliases: currentTerms.reduce(
        (total, term) => total + term.aliases.length,
        0,
      ),
      bindings: bindings.length,
      ready_bindings: readyBindings,
      stale_bindings: bindings.filter((binding) => binding.status === "stale")
        .length,
      updating_bindings: bindings.filter(
        (binding) => binding.status === "updating",
      ).length,
      failed_bindings: bindings.filter((binding) => binding.status === "failed")
        .length,
      never_enriched_bindings: bindings.filter(
        (binding) => binding.status === "never_enriched",
      ).length,
      running_jobs: currentElasticsearchJobs.filter((job) =>
        ["queued", "running", "cancel_requested"].includes(job.status),
      ).length,
      failed_jobs: currentElasticsearchJobs.filter(
        (job) => job.status === "failed",
      ).length,
    },
    setup: {
      has_profile: currentProfiles.length > 0,
      has_terms: currentTerms.length > 0,
      has_binding: bindings.length > 0,
      has_successful_enrichment: succeededJobs > 0,
      has_runtime_snapshot: readyBindings > 0,
    },
    bindings,
    recent_jobs: currentElasticsearchJobs.slice(0, 5).map(dashboardRecentJob),
  };
}

function dashboardBindingStatus(
  binding: ElasticsearchBinding,
  latestJob: ElasticsearchEnrichmentJob | null,
) {
  if (!binding.is_enabled) return "disabled";
  if (
    latestJob &&
    ["queued", "running", "cancel_requested"].includes(latestJob.status)
  )
    return "updating";
  if (latestJob?.status === "failed") return "failed";
  if (
    binding.pending_snapshot_version &&
    binding.last_successful_snapshot_version
  )
    return "stale";
  if (binding.pending_snapshot_version) return "updating";
  if (binding.last_successful_snapshot_version) return "ready";
  return "never_enriched";
}

function dashboardRecentJob(job: ElasticsearchEnrichmentJob) {
  return {
    id: job.id,
    binding_id: job.binding_id,
    binding_name: job.binding_name,
    profile_name: job.profile_name,
    status: job.status,
    source_index: job.source_index,
    target_index: job.target_index,
    alias_name: job.alias_name,
    snapshot_version: job.snapshot_version ?? null,
    documents_seen: job.documents_seen,
    documents_enriched: job.documents_enriched,
    documents_failed: job.documents_failed,
    error_message: job.error_message,
    started_at: job.started_at,
    finished_at: job.finished_at,
    created_at: job.created_at,
    updated_at: job.updated_at,
  };
}

function snapshotSummaryFromState(
  currentElasticsearchBindings: ElasticsearchBinding[],
  currentElasticsearchJobs: ElasticsearchEnrichmentJob[],
): SnapshotSummary {
  const latestJobByBinding = new Map<number, ElasticsearchEnrichmentJob>();
  for (const job of currentElasticsearchJobs) {
    if (!latestJobByBinding.has(job.binding_id)) {
      latestJobByBinding.set(job.binding_id, job);
    }
  }

  const bindings = currentElasticsearchBindings.map((binding) => {
    const latestJob = latestJobByBinding.get(binding.id) ?? null;
    const activeSnapshotVersion =
      binding.last_successful_snapshot_version ?? null;
    const isStale =
      Boolean(binding.pending_snapshot_version) ||
      binding.snapshot_status === "stale";
    const status = !binding.is_enabled
      ? "disabled"
      : latestJob?.status === "failed" && !activeSnapshotVersion
        ? "failed"
        : !activeSnapshotVersion
          ? "never_enriched"
          : isStale
            ? "stale"
            : latestJob?.status === "failed"
              ? "failed"
              : "ready";
    const rollbackAvailable = Boolean(
      latestJob?.status === "succeeded" &&
      (
        latestJob.result_json.rollout as
          | { rollback_available?: boolean }
          | undefined
      )?.rollback_available,
    );
    return {
      id: binding.id,
      name: binding.name,
      profile_name: binding.profile_name,
      index_name: binding.index_name,
      filter_field: binding.filter_field,
      filter_value: binding.filter_value,
      is_enabled: binding.is_enabled,
      status,
      active_snapshot_version: activeSnapshotVersion,
      pending_snapshot_version: binding.pending_snapshot_version ?? null,
      last_successful_snapshot_at: binding.last_successful_snapshot_at ?? null,
      last_successful_job_id: binding.last_successful_job_id ?? null,
      latest_job_id: latestJob?.id ?? null,
      latest_job_status: latestJob?.status ?? null,
      latest_job_error: latestJob?.error_message ?? null,
      rollback_available: rollbackAvailable,
      snapshot_aliases_total: activeSnapshotVersion ? 1 : 0,
      current_aliases_total:
        binding.id === 2 ? 2 : activeSnapshotVersion ? 1 : 0,
      diff: {
        active_checksum: activeSnapshotVersion ? "abc123" : null,
        current_checksum:
          binding.id === 2 ? "new789" : activeSnapshotVersion ? "abc123" : null,
        active_aliases: activeSnapshotVersion ? 1 : 0,
        current_aliases: binding.id === 2 ? 2 : activeSnapshotVersion ? 1 : 0,
        added_aliases: binding.id === 2 ? 1 : 0,
        removed_aliases: 0,
        changed_aliases: 0,
        changed: binding.id === 2,
      },
      updated_at: binding.updated_at,
    };
  });

  const history = currentElasticsearchJobs.slice(0, 25).map((job) => ({
    job_id: job.id,
    binding_id: job.binding_id,
    binding_name: job.binding_name,
    profile_name: job.profile_name,
    status: job.status,
    snapshot_version: job.snapshot_version ?? null,
    previous_snapshot_version: job.previous_snapshot_version ?? null,
    checksum: "abc123",
    alias_entries_total: job.snapshot_version ? 1 : 0,
    documents_seen: job.documents_seen,
    documents_enriched: job.documents_enriched,
    documents_failed: job.documents_failed,
    target_index: job.target_index,
    alias_name: job.alias_name,
    rollback_available: Boolean(
      job.status === "succeeded" &&
      (job.result_json.rollout as { rollback_available?: boolean } | undefined)
        ?.rollback_available,
    ),
    error_message: job.error_message,
    created_at: job.created_at,
    finished_at: job.finished_at,
  }));

  return {
    counts: {
      bindings: bindings.length,
      active_snapshots: bindings.filter(
        (binding) => binding.active_snapshot_version,
      ).length,
      stale_snapshots: bindings.filter((binding) => binding.status === "stale")
        .length,
      pending_snapshots: bindings.filter(
        (binding) => binding.pending_snapshot_version,
      ).length,
      failed_updates: bindings.filter((binding) => binding.status === "failed")
        .length,
      never_enriched: bindings.filter(
        (binding) => binding.status === "never_enriched",
      ).length,
      rollback_available: bindings.filter(
        (binding) => binding.rollback_available,
      ).length,
    },
    bindings,
    history,
  };
}

function cloneElasticsearchIndices() {
  return JSON.parse(
    JSON.stringify(elasticsearchIndices),
  ) as ElasticsearchIndex[];
}

function cloneElasticsearchMapping(indexName = "docs") {
  const mapping = JSON.parse(
    JSON.stringify(elasticsearchMapping),
  ) as ElasticsearchIndexMapping;
  mapping.index_name = indexName;
  return mapping;
}

function stubGovernanceApi(options: StubOptions = {}) {
  let currentProfiles = cloneProfiles();
  let currentUser = options.currentUser ?? adminUser;
  let currentUsers: AuthUser[] = [adminUser, moderatorUser, contributorUser];
  let currentPersonalApiTokens = clonePersonalApiTokens();
  let currentServiceAccounts = cloneServiceAccounts();
  let currentServiceAccountTokens = cloneServiceAccountTokens();
  let currentTerms = cloneTerms();
  let currentSuggestions = cloneSuggestions();
  let currentGlobalStopListEntries = cloneGlobalStopListEntries();
  let currentStopListEntries = cloneStopListEntries();
  let currentElasticsearchBindings = cloneElasticsearchBindings();
  let currentElasticsearchJobs = cloneElasticsearchJobs();
  let nextPersonalTokenId = 20;
  let nextServiceAccountId = 20;
  let nextServiceAccountTokenId = 30;
  let nextProfileId = 10;
  let nextTermId = 10;
  let nextAliasId = 20;
  let nextSuggestionId = 10;
  let nextGlobalStopListEntryId = 10;
  let nextStopListEntryId = 10;
  let nextElasticsearchBindingId = 10;
  let nextElasticsearchJobId = 102;

  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = input.toString();
      const method = init?.method ?? "GET";
      const headers = new Headers(init?.headers);

      if (url.endsWith("/v1/auth/me") && method === "GET") {
        if (
          options.authRequired &&
          headers.get("Authorization") !== "Bearer test-token"
        ) {
          return Response.json(
            { detail: "Missing bearer token" },
            { status: 401 },
          );
        }
        return Response.json(currentUser);
      }

      if (url.endsWith("/v1/auth/login") && method === "POST") {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          username: string;
          password: string;
        };
        if (payload.username !== "admin" || payload.password !== "change-me") {
          return Response.json(
            { detail: "Invalid username or password" },
            { status: 401 },
          );
        }
        currentUser = adminUser;
        return Response.json({
          access_token: "test-token",
          token_type: "bearer",
          expires_at: "2026-05-06T00:00:00Z",
          user: adminUser,
        });
      }

      if (url.endsWith("/v1/auth/logout") && method === "POST") {
        return new Response(null, { status: 204 });
      }

      if (url.endsWith("/v1/auth/users") && method === "GET") {
        return Response.json(currentUsers);
      }

      if (url.endsWith("/v1/auth/users") && method === "POST") {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          display_name?: string | null;
          role: AuthUser["role"];
          status?: AuthUser["status"];
          username: string;
        };
        const user: AuthUser = {
          id: 20,
          username: payload.username,
          normalized_username: payload.username.toLowerCase(),
          display_name: payload.display_name ?? null,
          role: payload.role,
          status: payload.status ?? "active",
          is_active: (payload.status ?? "active") === "active",
          created_at: "2026-05-05T00:00:00Z",
          updated_at: "2026-05-05T00:00:00Z",
          last_login_at: null,
        };
        currentUsers = [...currentUsers, user];
        return Response.json(user, { status: 201 });
      }

      if (url.endsWith("/v1/auth/users/contributor") && method === "PATCH") {
        const payload = JSON.parse(
          init?.body?.toString() ?? "{}",
        ) as Partial<AuthUser> & { password?: string | null };
        const updated: AuthUser = {
          ...contributorUser,
          username: payload.username ?? contributorUser.username,
          normalized_username: (
            payload.username ?? contributorUser.username
          ).toLowerCase(),
          display_name: payload.display_name ?? null,
          role: payload.role ?? contributorUser.role,
          status: payload.status ?? contributorUser.status,
          is_active:
            payload.is_active ??
            (payload.status ?? contributorUser.status) === "active",
          updated_at: "2026-05-06T00:00:00Z",
        };
        currentUsers = currentUsers.map((user) =>
          user.username === "contributor" ? updated : user,
        );
        return Response.json(updated);
      }

      if (
        url.endsWith("/v1/auth/users/contributor/status") &&
        method === "PATCH"
      ) {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          status: AuthUser["status"];
        };
        const updated: AuthUser = {
          ...contributorUser,
          status: payload.status,
          is_active: payload.status === "active",
          updated_at: "2026-05-06T00:00:00Z",
        };
        currentUsers = currentUsers.map((user) =>
          user.username === "contributor" ? updated : user,
        );
        return Response.json(updated);
      }

      if (
        url.endsWith("/v1/auth/users/contributor/revoke-api-tokens") &&
        method === "POST"
      ) {
        return Response.json({
          username: "contributor",
          revoked_api_tokens: 2,
        });
      }

      if (url.endsWith("/v1/auth/users/contributor") && method === "DELETE") {
        currentUsers = currentUsers.filter(
          (user) => user.username !== "contributor",
        );
        return new Response(null, { status: 204 });
      }

      if (url.endsWith("/v1/auth/api-tokens") && method === "GET") {
        return Response.json(currentPersonalApiTokens);
      }

      if (url.endsWith("/v1/auth/api-tokens") && method === "POST") {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          expires_in_days?: number | null;
          name: string;
          scopes: string[];
        };
        const token: ApiToken & { access_token: string; token_type: "bearer" } =
          {
            id: nextPersonalTokenId++,
            name: payload.name,
            token_prefix: "sk_pat_new",
            scopes: payload.scopes,
            owner_type: "personal",
            owner_name: currentUser.username,
            expires_at: payload.expires_in_days ? "2026-08-01T00:00:00Z" : null,
            revoked_at: null,
            last_used_at: null,
            created_by: currentUser.username,
            created_at: "2026-05-09T00:00:00Z",
            updated_at: "2026-05-09T00:00:00Z",
            access_token: "sk_pat_plaintext",
            token_type: "bearer",
          };
        currentPersonalApiTokens = [token, ...currentPersonalApiTokens];
        return Response.json(token, { status: 201 });
      }

      if (url.match(/\/v1\/auth\/api-tokens\/(\d+)$/) && method === "DELETE") {
        const tokenId = Number(
          url.match(/\/v1\/auth\/api-tokens\/(\d+)$/)?.[1] ?? "0",
        );
        currentPersonalApiTokens = currentPersonalApiTokens.map((token) =>
          token.id === tokenId
            ? { ...token, revoked_at: "2026-05-09T00:00:00Z" }
            : token,
        );
        return new Response(null, { status: 204 });
      }

      if (url.endsWith("/v1/auth/service-accounts") && method === "GET") {
        if (currentUser.role !== "admin") {
          return Response.json({ detail: "Forbidden" }, { status: 403 });
        }
        return Response.json(currentServiceAccounts);
      }

      if (url.endsWith("/v1/auth/service-accounts") && method === "POST") {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          description?: string | null;
          display_name?: string | null;
          is_active?: boolean;
          name: string;
          role: AuthUser["role"];
        };
        const account: ServiceAccount = {
          id: nextServiceAccountId++,
          name: payload.name,
          normalized_name: payload.name.toLowerCase().replace(/-/g, "_"),
          display_name: payload.display_name ?? null,
          description: payload.description ?? null,
          role: payload.role,
          is_active: payload.is_active ?? true,
          created_by: currentUser.username,
          last_used_at: null,
          created_at: "2026-05-09T00:00:00Z",
          updated_at: "2026-05-09T00:00:00Z",
        };
        currentServiceAccounts = [account, ...currentServiceAccounts];
        return Response.json(account, { status: 201 });
      }

      if (
        url.endsWith("/v1/auth/service-accounts/migration-bot") &&
        method === "PATCH"
      ) {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          is_active?: boolean | null;
        };
        const account = currentServiceAccounts.find(
          (item) => item.name === "migration-bot",
        );
        if (!account) {
          return Response.json({ detail: "not found" }, { status: 404 });
        }
        const updated: ServiceAccount = {
          ...account,
          is_active: payload.is_active ?? account.is_active,
          updated_at: "2026-05-09T00:00:00Z",
        };
        currentServiceAccounts = currentServiceAccounts.map((item) =>
          item.name === "migration-bot" ? updated : item,
        );
        return Response.json(updated);
      }

      if (
        url.match(/\/v1\/auth\/service-accounts\/[^/]+\/tokens$/) &&
        method === "GET"
      ) {
        const accountName = decodeURIComponent(
          url.match(/\/v1\/auth\/service-accounts\/([^/]+)\/tokens$/)?.[1] ??
            "",
        );
        return Response.json(
          accountName === "migration-bot" ? currentServiceAccountTokens : [],
        );
      }

      if (
        url.match(/\/v1\/auth\/service-accounts\/[^/]+\/tokens$/) &&
        method === "POST"
      ) {
        const accountName = decodeURIComponent(
          url.match(/\/v1\/auth\/service-accounts\/([^/]+)\/tokens$/)?.[1] ??
            "migration-bot",
        );
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          expires_in_days?: number | null;
          name: string;
          scopes: string[];
        };
        const token: ApiToken & { access_token: string; token_type: "bearer" } =
          {
            id: nextServiceAccountTokenId++,
            name: payload.name,
            token_prefix: "sk_sat_new",
            scopes: payload.scopes,
            owner_type: "service_account",
            owner_name: accountName,
            expires_at: payload.expires_in_days ? "2026-08-01T00:00:00Z" : null,
            revoked_at: null,
            last_used_at: null,
            created_by: currentUser.username,
            created_at: "2026-05-09T00:00:00Z",
            updated_at: "2026-05-09T00:00:00Z",
            access_token: "sk_sat_plaintext",
            token_type: "bearer",
          };
        if (accountName === "migration-bot") {
          currentServiceAccountTokens = [token, ...currentServiceAccountTokens];
        }
        return Response.json(token, { status: 201 });
      }

      if (
        url.match(/\/v1\/auth\/service-accounts\/[^/]+\/tokens\/(\d+)$/) &&
        method === "DELETE"
      ) {
        const tokenId = Number(
          url.match(
            /\/v1\/auth\/service-accounts\/[^/]+\/tokens\/(\d+)$/,
          )?.[1] ?? "0",
        );
        currentServiceAccountTokens = currentServiceAccountTokens.map(
          (token) =>
            token.id === tokenId
              ? { ...token, revoked_at: "2026-05-09T00:00:00Z" }
              : token,
        );
        return new Response(null, { status: 204 });
      }

      if (url.endsWith("/v1/dashboard/summary") && method === "GET") {
        return Response.json(
          dashboardSummaryFromState(
            currentProfiles,
            currentTerms,
            currentElasticsearchBindings,
            currentElasticsearchJobs,
          ),
        );
      }

      if (url.endsWith("/v1/snapshots/summary") && method === "GET") {
        return Response.json(
          snapshotSummaryFromState(
            currentElasticsearchBindings,
            currentElasticsearchJobs,
          ),
        );
      }

      if (url.endsWith("/v1/query/plan") && method === "POST") {
        return Response.json(runtimeQueryPlanResponse);
      }

      if (url.endsWith("/v1/search") && method === "POST") {
        return Response.json(runtimeSearchResponse);
      }

      if (url.endsWith("/v1/governance/profiles") && method === "GET") {
        return Response.json(currentProfiles);
      }

      if (url.endsWith("/v1/governance/profiles") && method === "POST") {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          description?: string | null;
          name: string;
        };
        const newProfile: Profile = {
          id: nextProfileId++,
          name: payload.name,
          normalized_name: payload.name.toLowerCase(),
          description: payload.description ?? null,
          created_at: "2026-05-05T00:00:00Z",
          updated_at: "2026-05-05T00:00:00Z",
        };
        currentProfiles = [...currentProfiles, newProfile];
        return Response.json(newProfile, { status: 201 });
      }

      if (
        url.endsWith("/v1/governance/profiles/default_it") &&
        method === "PATCH"
      ) {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          description?: string | null;
          name?: string | null;
        };
        const updatedProfile: Profile = {
          ...currentProfiles[0],
          name: payload.name ?? currentProfiles[0].name,
          normalized_name: (
            payload.name ?? currentProfiles[0].name
          ).toLowerCase(),
          description: payload.description ?? null,
          updated_at: "2026-05-05T00:00:00Z",
        };
        currentProfiles = [updatedProfile, ...currentProfiles.slice(1)];
        return Response.json(updatedProfile);
      }

      if (
        url.endsWith("/v1/governance/profiles/default_it") &&
        method === "DELETE"
      ) {
        currentProfiles = currentProfiles.filter(
          (profile) => profile.name !== "default_it",
        );
        currentTerms = [];
        return new Response(null, { status: 204 });
      }

      if (url.endsWith("/v1/governance/global-stop-list") && method === "GET") {
        return Response.json(currentGlobalStopListEntries);
      }

      if (
        url.endsWith("/v1/governance/global-stop-list") &&
        method === "POST"
      ) {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          is_active?: boolean;
          reason?: string | null;
          target: GlobalStopListEntry["target"];
          value: string;
        };
        const entry: GlobalStopListEntry = {
          id: nextGlobalStopListEntryId++,
          value: payload.value,
          normalized_value: payload.value.toLowerCase(),
          target: payload.target,
          reason: payload.reason ?? null,
          is_active: payload.is_active ?? true,
          created_at: "2026-05-08T00:00:00Z",
          updated_at: "2026-05-08T00:00:00Z",
        };
        currentGlobalStopListEntries = [entry, ...currentGlobalStopListEntries];
        return Response.json(entry, { status: 201 });
      }

      if (
        url.endsWith("/v1/governance/global-stop-list/1") &&
        method === "PATCH"
      ) {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          is_active?: boolean | null;
          reason?: string | null;
          target?: GlobalStopListEntry["target"] | null;
          value?: string | null;
        };
        const existingEntry = currentGlobalStopListEntries.find(
          (entry) => entry.id === 1,
        );
        if (!existingEntry) {
          return Response.json({ detail: "not found" }, { status: 404 });
        }
        const updatedEntry: GlobalStopListEntry = {
          ...existingEntry,
          value: payload.value ?? existingEntry.value,
          normalized_value: (
            payload.value ?? existingEntry.value
          ).toLowerCase(),
          target: payload.target ?? existingEntry.target,
          reason: payload.reason ?? null,
          is_active: payload.is_active ?? existingEntry.is_active,
          updated_at: "2026-05-08T00:00:00Z",
        };
        currentGlobalStopListEntries = currentGlobalStopListEntries.map(
          (entry) => (entry.id === 1 ? updatedEntry : entry),
        );
        return Response.json(updatedEntry);
      }

      if (
        url.endsWith("/v1/governance/global-stop-list/1") &&
        method === "DELETE"
      ) {
        currentGlobalStopListEntries = currentGlobalStopListEntries.filter(
          (entry) => entry.id !== 1,
        );
        return new Response(null, { status: 204 });
      }

      if (
        url.endsWith("/v1/governance/profiles/default_it/stop-list") &&
        method === "GET"
      ) {
        return Response.json(currentStopListEntries);
      }

      if (
        url.endsWith("/v1/governance/profiles/default_it/stop-list") &&
        method === "POST"
      ) {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          is_active?: boolean;
          reason?: string | null;
          target: StopListEntry["target"];
          value: string;
        };
        const entry: StopListEntry = {
          id: nextStopListEntryId++,
          profile_id: 1,
          value: payload.value,
          normalized_value: payload.value.toLowerCase(),
          target: payload.target,
          reason: payload.reason ?? null,
          is_active: payload.is_active ?? true,
          created_at: "2026-05-07T00:00:00Z",
          updated_at: "2026-05-07T00:00:00Z",
        };
        currentStopListEntries = [entry, ...currentStopListEntries];
        return Response.json(entry, { status: 201 });
      }

      if (
        url.endsWith("/v1/governance/profiles/default_it/stop-list/1") &&
        method === "PATCH"
      ) {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          is_active?: boolean | null;
          reason?: string | null;
          target?: StopListEntry["target"] | null;
          value?: string | null;
        };
        const existingEntry = currentStopListEntries.find(
          (entry) => entry.id === 1,
        );
        if (!existingEntry) {
          return Response.json({ detail: "not found" }, { status: 404 });
        }
        const updatedEntry: StopListEntry = {
          ...existingEntry,
          value: payload.value ?? existingEntry.value,
          normalized_value: (
            payload.value ?? existingEntry.value
          ).toLowerCase(),
          target: payload.target ?? existingEntry.target,
          reason: payload.reason ?? null,
          is_active: payload.is_active ?? existingEntry.is_active,
          updated_at: "2026-05-07T00:00:00Z",
        };
        currentStopListEntries = currentStopListEntries.map((entry) =>
          entry.id === 1 ? updatedEntry : entry,
        );
        return Response.json(updatedEntry);
      }

      if (
        url.endsWith("/v1/governance/profiles/default_it/stop-list/1") &&
        method === "DELETE"
      ) {
        currentStopListEntries = currentStopListEntries.filter(
          (entry) => entry.id !== 1,
        );
        return new Response(null, { status: 204 });
      }

      if (
        url.endsWith("/v1/governance/elasticsearch/connection/status") &&
        method === "GET"
      ) {
        return Response.json({
          configured: true,
          ok: true,
          url: "http://localhost:9200",
          cluster_name: "skeinrank-dev",
          cluster_version: "8.13.4",
          error: null,
        });
      }

      if (
        url.endsWith("/v1/governance/elasticsearch/indices") &&
        method === "GET"
      ) {
        return Response.json(cloneElasticsearchIndices());
      }

      if (
        url.includes("/v1/governance/elasticsearch/indices/") &&
        url.endsWith("/mapping") &&
        method === "GET"
      ) {
        const indexName = decodeURIComponent(
          url
            .split("/v1/governance/elasticsearch/indices/")[1]
            .replace("/mapping", ""),
        );
        return Response.json(cloneElasticsearchMapping(indexName));
      }

      if (
        url.includes("/v1/governance/elasticsearch/bindings") &&
        method === "GET"
      ) {
        const profileName = new URL(url).searchParams.get("profile_name");
        const visibleBindings = profileName
          ? currentElasticsearchBindings.filter(
              (binding) => binding.profile_name === profileName,
            )
          : currentElasticsearchBindings;
        return Response.json(visibleBindings);
      }

      if (
        url.endsWith("/v1/governance/elasticsearch/bindings") &&
        method === "POST"
      ) {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          description?: string | null;
          filter_field?: string | null;
          filter_value?: string | null;
          timestamp_field?: string | null;
          time_window_days?: number | null;
          index_name: string;
          is_enabled?: boolean;
          mode?: ElasticsearchBinding["mode"];
          write_strategy?: ElasticsearchBinding["write_strategy"];
          name: string;
          profile_name: string;
          target_field: string;
          text_fields: string[];
        };
        const binding: ElasticsearchBinding = {
          id: nextElasticsearchBindingId++,
          profile_id: 1,
          profile_name: payload.profile_name,
          name: payload.name,
          normalized_name: payload.name.toLowerCase().replace(/\s+/g, "_"),
          description: payload.description ?? null,
          provider: "elasticsearch",
          index_name: payload.index_name,
          text_fields: payload.text_fields,
          target_field: payload.target_field,
          filter_field: payload.filter_field ?? null,
          filter_value: payload.filter_value ?? null,
          timestamp_field: payload.timestamp_field ?? null,
          time_window_days: payload.time_window_days ?? null,
          mode: payload.mode ?? "dry_run",
          write_strategy: payload.write_strategy ?? "reindex_alias_swap",
          is_enabled: payload.is_enabled ?? true,
          last_successful_snapshot_version: null,
          last_successful_snapshot_at: null,
          last_successful_job_id: null,
          pending_snapshot_version: null,
          snapshot_status: "never_enriched",
          created_at: "2026-05-07T00:00:00Z",
          updated_at: "2026-05-07T00:00:00Z",
        };
        currentElasticsearchBindings = [
          binding,
          ...currentElasticsearchBindings,
        ];
        return Response.json(binding, { status: 201 });
      }

      if (
        url.includes("/v1/governance/elasticsearch/jobs") &&
        method === "GET"
      ) {
        const jobIdMatch = url.match(
          /\/v1\/governance\/elasticsearch\/jobs\/(\d+)$/,
        );
        if (jobIdMatch) {
          const job = currentElasticsearchJobs.find(
            (currentJob) => currentJob.id === Number(jobIdMatch[1]),
          );
          return job
            ? Response.json(job)
            : Response.json({ detail: "not found" }, { status: 404 });
        }
        const bindingId = new URL(url).searchParams.get("binding_id");
        const visibleJobs = bindingId
          ? currentElasticsearchJobs.filter(
              (job) => job.binding_id === Number(bindingId),
            )
          : currentElasticsearchJobs;
        return Response.json(visibleJobs);
      }

      if (
        url.match(/\/v1\/governance\/elasticsearch\/jobs\/(\d+)\/rollback$/) &&
        method === "POST"
      ) {
        const jobId = Number(
          url.match(
            /\/v1\/governance\/elasticsearch\/jobs\/(\d+)\/rollback$/,
          )?.[1],
        );
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          reason?: string | null;
        };
        const job = currentElasticsearchJobs.find(
          (currentJob) => currentJob.id === jobId,
        );
        if (!job) {
          return Response.json({ detail: "not found" }, { status: 404 });
        }
        const rollout = job.result_json.rollout as
          | Record<string, unknown>
          | undefined;
        if (!rollout || job.status !== "succeeded") {
          return Response.json(
            { detail: "Rollback is not available for this job." },
            { status: 409 },
          );
        }
        const nextRollout = {
          ...rollout,
          status: "rolled_back",
          rollback_available: false,
          rollback_completed: true,
          rollback_completed_at: "2026-05-08T11:10:00Z",
          rollback: {
            status: "rolled_back",
            requested_by: currentUser.username,
            requested_at: "2026-05-08T11:10:00Z",
            completed_at: "2026-05-08T11:10:00Z",
            reason: payload.reason ?? "Rollback requested from test",
            alias_name: rollout.alias_name,
            from_indices: rollout.new_alias_indices,
            rollback_candidate_index: rollout.rollback_candidate_index,
            alias_indices_after_rollback: [rollout.rollback_candidate_index],
            alias_result: { acknowledged: true },
          },
          rollback_hint: `Rollback completed: alias ${String(rollout.alias_name)} now points to ${String(rollout.rollback_candidate_index)}.`,
        };
        const nextJob: ElasticsearchEnrichmentJob = {
          ...job,
          result_json: {
            ...job.result_json,
            rollout: nextRollout,
          },
          updated_at: "2026-05-08T11:10:00Z",
        };
        currentElasticsearchJobs = currentElasticsearchJobs.map((currentJob) =>
          currentJob.id === jobId ? nextJob : currentJob,
        );
        return Response.json(nextJob);
      }

      if (
        url.match(/\/v1\/governance\/elasticsearch\/jobs\/(\d+)\/cancel$/) &&
        method === "POST"
      ) {
        const jobId = Number(
          url.match(
            /\/v1\/governance\/elasticsearch\/jobs\/(\d+)\/cancel$/,
          )?.[1],
        );
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          reason?: string | null;
        };
        const job = currentElasticsearchJobs.find(
          (currentJob) => currentJob.id === jobId,
        );
        if (!job) {
          return Response.json({ detail: "not found" }, { status: 404 });
        }
        if (!["queued", "running", "cancel_requested"].includes(job.status)) {
          return Response.json(
            {
              detail: `Cannot cancel enrichment job with status: ${job.status}`,
            },
            { status: 409 },
          );
        }
        const nextJob: ElasticsearchEnrichmentJob = {
          ...job,
          status: job.status === "queued" ? "cancelled" : "cancel_requested",
          result_json: {
            ...job.result_json,
            cancellation: {
              requested_by: currentUser.username,
              requested_at: "2026-05-08T11:02:00Z",
              reason: payload.reason ?? "Cancelled from test",
            },
          },
          updated_at: "2026-05-08T11:02:00Z",
        };
        currentElasticsearchJobs = currentElasticsearchJobs.map((currentJob) =>
          currentJob.id === jobId ? nextJob : currentJob,
        );
        return Response.json(nextJob);
      }

      if (
        url.endsWith("/v1/governance/elasticsearch/bindings/1/jobs") &&
        method === "POST"
      ) {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          alias_name?: string | null;
          max_documents?: number;
          target_index_name?: string | null;
        };
        const existingBinding = currentElasticsearchBindings.find(
          (binding) => binding.id === 1,
        );
        if (!existingBinding) {
          return Response.json({ detail: "not found" }, { status: 404 });
        }
        const jobId = nextElasticsearchJobId++;
        const job: ElasticsearchEnrichmentJob = {
          id: jobId,
          binding_id: existingBinding.id,
          profile_id: existingBinding.profile_id,
          binding_name: existingBinding.name,
          profile_name: existingBinding.profile_name,
          status: "running",
          write_strategy: existingBinding.write_strategy,
          source_index: existingBinding.index_name,
          target_index:
            payload.target_index_name ??
            `${existingBinding.index_name}__skeinrank_job_${jobId}`,
          alias_name: payload.alias_name ?? existingBinding.index_name,
          snapshot_version:
            existingBinding.last_successful_snapshot_version ??
            "default_it@abc123",
          previous_snapshot_version:
            existingBinding.last_successful_snapshot_version ?? null,
          requested_by: currentUser.username,
          documents_seen: payload.max_documents ?? 1000,
          documents_enriched: 3,
          documents_failed: 0,
          result_json: {
            updated_document_ids: ["doc-1", "doc-3"],
            timestamp_field: existingBinding.timestamp_field,
            time_window_days: existingBinding.time_window_days,
            rollout: {
              strategy: "reindex_alias_swap",
              status: "prepared",
              alias_name: payload.alias_name ?? existingBinding.index_name,
              source_index: existingBinding.index_name,
              target_index:
                payload.target_index_name ??
                `${existingBinding.index_name}__skeinrank_job_${jobId}`,
              previous_alias_indices: ["docs_v1"],
              new_alias_indices: [],
              rollback_candidate_index: "docs_v1",
              rollback_available: true,
              alias_swap_completed: false,
              alias_swap_started_at: "2026-05-08T11:00:30Z",
              alias_swapped_at: null,
              rollback_hint:
                "Manual rollback candidate: repoint alias docs to docs_v1.",
              cleanup_hint:
                "If this rollout is cancelled or fails before alias swap, review or delete target index docs__skeinrank_candidate.",
            },
          },
          error_message: null,
          started_at: "2026-05-08T11:00:00Z",
          finished_at: null,
          created_at: "2026-05-08T11:00:00Z",
          updated_at: "2026-05-08T11:01:00Z",
        };
        currentElasticsearchJobs = [job, ...currentElasticsearchJobs];
        return Response.json(job, { status: 201 });
      }

      if (
        url.endsWith("/v1/governance/elasticsearch/bindings/1/dry-run") &&
        method === "POST"
      ) {
        return Response.json(elasticsearchDryRunResponse);
      }

      if (
        url.endsWith("/v1/governance/elasticsearch/bindings/1/evidence") &&
        method === "POST"
      ) {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          query?: string;
          canonical_value?: string | null;
          max_documents?: number;
        };
        const query = payload.query ?? elasticsearchEvidenceResponse.query;
        const fragment = `Evidence mentions ${query} in runbook docs.`;
        const matchStart = "Evidence mentions ".length;
        return Response.json({
          ...elasticsearchEvidenceResponse,
          query,
          normalized_query: query.toLowerCase(),
          canonical_value:
            payload.canonical_value ??
            elasticsearchEvidenceResponse.canonical_value,
          max_documents:
            payload.max_documents ??
            elasticsearchEvidenceResponse.max_documents,
          documents: [
            {
              ...elasticsearchEvidenceResponse.documents[0],
              fragment,
              highlighted_fragment: `Evidence mentions <mark>${query}</mark> in runbook docs.`,
              matched_text: query,
              match_start: matchStart,
              match_end: matchStart + query.length,
            },
          ],
        });
      }

      if (
        url.endsWith("/v1/governance/elasticsearch/bindings/1") &&
        method === "PATCH"
      ) {
        const payload = JSON.parse(
          init?.body?.toString() ?? "{}",
        ) as Partial<ElasticsearchBinding> & {
          profile_name?: string | null;
          text_fields?: string[] | null;
        };
        const existingBinding = currentElasticsearchBindings.find(
          (binding) => binding.id === 1,
        );
        if (!existingBinding) {
          return Response.json({ detail: "not found" }, { status: 404 });
        }
        const updatedBinding: ElasticsearchBinding = {
          ...existingBinding,
          name: payload.name ?? existingBinding.name,
          normalized_name: (payload.name ?? existingBinding.name)
            .toLowerCase()
            .replace(/\s+/g, "_"),
          profile_name: payload.profile_name ?? existingBinding.profile_name,
          description: payload.description ?? null,
          index_name: payload.index_name ?? existingBinding.index_name,
          text_fields: payload.text_fields ?? existingBinding.text_fields,
          target_field: payload.target_field ?? existingBinding.target_field,
          filter_field: payload.filter_field ?? null,
          filter_value: payload.filter_value ?? null,
          timestamp_field: payload.timestamp_field ?? null,
          time_window_days: payload.time_window_days ?? null,
          mode: payload.mode ?? existingBinding.mode,
          write_strategy:
            payload.write_strategy ?? existingBinding.write_strategy,
          is_enabled: payload.is_enabled ?? existingBinding.is_enabled,
          updated_at: "2026-05-07T00:00:00Z",
        };
        currentElasticsearchBindings = currentElasticsearchBindings.map(
          (binding) => (binding.id === 1 ? updatedBinding : binding),
        );
        return Response.json(updatedBinding);
      }

      if (
        url.endsWith("/v1/governance/elasticsearch/bindings/1") &&
        method === "DELETE"
      ) {
        currentElasticsearchBindings = currentElasticsearchBindings.filter(
          (binding) => binding.id !== 1,
        );
        return new Response(null, { status: 204 });
      }

      if (
        (url.endsWith("/v1/governance/profiles/default_it/terms") ||
          url.endsWith("/v1/governance/profiles/platform_terms/terms")) &&
        method === "GET"
      ) {
        return Response.json(currentTerms);
      }

      if (
        url.endsWith("/v1/governance/profiles/default_it/terms") &&
        method === "POST"
      ) {
        if (options.duplicateTerm) {
          return Response.json(
            {
              detail: "Term already exists in profile 'default_it': kubernetes",
            },
            { status: 409 },
          );
        }

        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          canonical_value: string;
          description?: string | null;
          slot: string;
          status?: string;
        };
        const newTerm: CanonicalTerm = {
          id: nextTermId++,
          canonical_value: payload.canonical_value,
          normalized_value: payload.canonical_value.toLowerCase(),
          slot: payload.slot.toUpperCase(),
          status: payload.status ?? "active",
          description: payload.description ?? null,
          aliases: [],
          created_at: "2026-05-05T00:00:00Z",
          updated_at: "2026-05-05T00:00:00Z",
        };
        currentTerms = [...currentTerms, newTerm];
        return Response.json(newTerm, { status: 201 });
      }

      if (
        url.endsWith("/v1/governance/profiles/default_it/terms/kubernetes") &&
        method === "PATCH"
      ) {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          canonical_value?: string | null;
          description?: string | null;
          slot?: string | null;
          status?: string | null;
        };
        const updatedTerm: CanonicalTerm = {
          ...currentTerms[0],
          canonical_value:
            payload.canonical_value ?? currentTerms[0].canonical_value,
          normalized_value: (
            payload.canonical_value ?? currentTerms[0].canonical_value
          ).toLowerCase(),
          slot: payload.slot ?? currentTerms[0].slot,
          status: payload.status ?? currentTerms[0].status,
          description: payload.description ?? null,
          updated_at: "2026-05-05T00:00:00Z",
        };
        currentTerms = [updatedTerm, ...currentTerms.slice(1)];
        return Response.json(updatedTerm);
      }

      if (
        url.endsWith("/v1/governance/profiles/default_it/terms/kubernetes") &&
        method === "DELETE"
      ) {
        currentTerms = currentTerms.filter(
          (term) => term.canonical_value !== "kubernetes",
        );
        return new Response(null, { status: 204 });
      }

      if (
        url.endsWith(
          "/v1/governance/profiles/default_it/terms/kubernetes/aliases",
        ) &&
        method === "POST"
      ) {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          alias_value: string;
          confidence?: number;
          notes?: string | null;
          status?: string;
        };
        const newAlias: TermAlias = {
          id: nextAliasId++,
          alias_value: payload.alias_value,
          normalized_alias: payload.alias_value.toLowerCase(),
          status: payload.status ?? "active",
          confidence: payload.confidence ?? 1,
          notes: payload.notes ?? null,
          created_at: "2026-05-05T00:00:00Z",
          updated_at: "2026-05-05T00:00:00Z",
        };
        currentTerms = currentTerms.map((term) =>
          term.canonical_value === "kubernetes"
            ? { ...term, aliases: [...term.aliases, newAlias] }
            : term,
        );
        return Response.json(newAlias, { status: 201 });
      }

      if (
        url.endsWith(
          "/v1/governance/profiles/default_it/terms/kubernetes/aliases/1",
        ) &&
        method === "PATCH"
      ) {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          alias_value?: string | null;
          confidence?: number | null;
          notes?: string | null;
          status?: string | null;
        };
        const updatedAlias: TermAlias = {
          ...currentTerms[0].aliases[0],
          alias_value:
            payload.alias_value ?? currentTerms[0].aliases[0].alias_value,
          normalized_alias: (
            payload.alias_value ?? currentTerms[0].aliases[0].alias_value
          ).toLowerCase(),
          status: payload.status ?? currentTerms[0].aliases[0].status,
          confidence:
            payload.confidence ?? currentTerms[0].aliases[0].confidence,
          notes: payload.notes ?? null,
          updated_at: "2026-05-05T00:00:00Z",
        };
        currentTerms = currentTerms.map((term) => ({
          ...term,
          aliases: term.aliases.map((alias) =>
            alias.id === 1 ? updatedAlias : alias,
          ),
        }));
        return Response.json(updatedAlias);
      }

      if (
        url.endsWith(
          "/v1/governance/profiles/default_it/terms/kubernetes/aliases/1",
        ) &&
        method === "DELETE"
      ) {
        currentTerms = currentTerms.map((term) => ({
          ...term,
          aliases: term.aliases.filter((alias) => alias.id !== 1),
        }));
        return new Response(null, { status: 204 });
      }

      if (
        url.includes("/v1/governance/profiles/default_it/suggestions") &&
        method === "GET"
      ) {
        const status = new URL(url).searchParams.get("status");
        const visibleSuggestions = status
          ? currentSuggestions.filter(
              (suggestion) => suggestion.status === status,
            )
          : currentSuggestions;
        return Response.json(visibleSuggestions);
      }

      if (
        url.endsWith("/v1/governance/profiles/default_it/suggestions") &&
        method === "POST"
      ) {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          alias_value?: string | null;
          canonical_value: string;
          confidence?: number;
          context?: string | null;
          description?: string | null;
          slot: string;
          source?: GovernanceSuggestion["source"];
          suggestion_type?: GovernanceSuggestion["suggestion_type"];
        };
        const suggestionType = payload.suggestion_type ?? "alias";
        const suggestion: GovernanceSuggestion = {
          id: nextSuggestionId++,
          profile_id: 1,
          term_id:
            suggestionType === "alias"
              ? (currentTerms.find(
                  (term) => term.canonical_value === payload.canonical_value,
                )?.id ?? null)
              : null,
          alias_id: null,
          suggestion_type: suggestionType,
          canonical_value: payload.canonical_value,
          normalized_canonical: payload.canonical_value.toLowerCase(),
          alias_value: payload.alias_value ?? null,
          normalized_alias: payload.alias_value?.toLowerCase() ?? null,
          slot: payload.slot,
          description: payload.description ?? null,
          confidence: payload.confidence ?? 1,
          source: payload.source ?? "manual",
          context: payload.context ?? null,
          status: "pending",
          created_by: currentUser.username,
          reviewed_by: null,
          review_comment: null,
          reviewed_at: null,
          evidence_snapshot: null,
          evidence_checked_by: null,
          evidence_checked_at: null,
          created_at: "2026-05-06T00:00:00Z",
          updated_at: "2026-05-06T00:00:00Z",
        };
        currentSuggestions = [suggestion, ...currentSuggestions];
        return Response.json(suggestion, { status: 201 });
      }

      if (
        url.includes("/v1/governance/profiles/default_it/suggestions/") &&
        url.endsWith("/evidence/refresh") &&
        method === "POST"
      ) {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          binding_id: number;
          query?: string | null;
          max_documents?: number;
        };
        const suggestionId = Number(
          url.match(/suggestions\/(\d+)\/evidence\/refresh/)?.[1] ?? "0",
        );
        const currentSuggestion =
          currentSuggestions.find(
            (suggestion) => suggestion.id === suggestionId,
          ) ?? currentSuggestions[0];
        const query =
          payload.query ??
          currentSuggestion.alias_value ??
          currentSuggestion.canonical_value;
        const updatedSuggestion: GovernanceSuggestion = {
          ...currentSuggestion,
          evidence_snapshot: {
            binding_id: payload.binding_id,
            binding_name: "infra docs",
            index_name: "docs",
            profile_name: "default_it",
            query,
            normalized_query: query.toLowerCase(),
            canonical_value: currentSuggestion.canonical_value,
            max_documents: payload.max_documents ?? 5,
            documents: elasticsearchEvidenceResponse.documents.map(
              (document) => ({ ...document }),
            ),
            warnings: [],
          },
          evidence_checked_by: currentUser.username,
          evidence_checked_at: "2026-05-09T00:00:00Z",
          updated_at: "2026-05-09T00:00:00Z",
        };
        currentSuggestions = currentSuggestions.map((suggestion) =>
          suggestion.id === currentSuggestion.id
            ? updatedSuggestion
            : suggestion,
        );
        return Response.json(updatedSuggestion);
      }

      if (
        url.includes("/v1/governance/profiles/default_it/suggestions/") &&
        url.endsWith("/approve") &&
        method === "POST"
      ) {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          review_comment?: string | null;
        };
        const suggestionId = Number(
          url.match(/suggestions\/(\d+)\/approve/)?.[1] ?? "0",
        );
        const currentSuggestion =
          currentSuggestions.find(
            (suggestion) => suggestion.id === suggestionId,
          ) ?? currentSuggestions[0];
        let aliasId = currentSuggestion.alias_id;
        let termId = currentSuggestion.term_id;
        if (currentSuggestion.suggestion_type === "alias") {
          const newAlias: TermAlias = {
            id: nextAliasId++,
            alias_value: currentSuggestion.alias_value ?? "",
            normalized_alias: currentSuggestion.normalized_alias ?? "",
            status: "active",
            confidence: currentSuggestion.confidence,
            notes: currentSuggestion.context,
            created_at: "2026-05-06T00:00:00Z",
            updated_at: "2026-05-06T00:00:00Z",
          };
          aliasId = newAlias.id;
          currentTerms = currentTerms.map((term) =>
            term.canonical_value === currentSuggestion.canonical_value
              ? { ...term, aliases: [...term.aliases, newAlias] }
              : term,
          );
        } else {
          const newTerm: CanonicalTerm = {
            id: nextTermId++,
            canonical_value: currentSuggestion.canonical_value,
            normalized_value: currentSuggestion.normalized_canonical,
            slot: currentSuggestion.slot,
            status: "active",
            description: currentSuggestion.description,
            aliases: [],
            created_at: "2026-05-06T00:00:00Z",
            updated_at: "2026-05-06T00:00:00Z",
          };
          termId = newTerm.id;
          currentTerms = [...currentTerms, newTerm];
        }
        const updatedSuggestion: GovernanceSuggestion = {
          ...currentSuggestion,
          alias_id: aliasId,
          term_id: termId,
          status: "approved",
          reviewed_by: currentUser.username,
          review_comment: payload.review_comment ?? null,
          reviewed_at: "2026-05-06T00:00:00Z",
          updated_at: "2026-05-06T00:00:00Z",
        };
        currentSuggestions = currentSuggestions.map((suggestion) =>
          suggestion.id === currentSuggestion.id
            ? updatedSuggestion
            : suggestion,
        );
        return Response.json(updatedSuggestion);
      }

      if (
        url.includes("/v1/governance/profiles/default_it/suggestions/") &&
        url.endsWith("/reject") &&
        method === "POST"
      ) {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          review_comment?: string | null;
        };
        const suggestionId = Number(
          url.match(/suggestions\/(\d+)\/reject/)?.[1] ?? "0",
        );
        const currentSuggestion =
          currentSuggestions.find(
            (suggestion) => suggestion.id === suggestionId,
          ) ?? currentSuggestions[0];
        const updatedSuggestion: GovernanceSuggestion = {
          ...currentSuggestion,
          status: "rejected",
          reviewed_by: currentUser.username,
          review_comment: payload.review_comment ?? null,
          reviewed_at: "2026-05-06T00:00:00Z",
          updated_at: "2026-05-06T00:00:00Z",
        };
        currentSuggestions = currentSuggestions.map((suggestion) =>
          suggestion.id === currentSuggestion.id
            ? updatedSuggestion
            : suggestion,
        );
        return Response.json(updatedSuggestion);
      }

      if (
        url.endsWith("/v1/governance/profiles/default_it/snapshot/export") &&
        method === "POST"
      ) {
        return Response.json({
          profile_id: "default_it",
          snapshot: {
            version: "default_it@draft",
            source: "governance-api",
            created_at: "2026-05-05T00:00:00Z",
            description:
              "Runtime snapshot exported from the governance console.",
          },
          alias_matcher: {
            backend: "aho_corasick",
          },
          aliases: [
            {
              slot: "TOOL",
              canonical: "kubernetes",
              aliases: ["k8s"],
            },
          ],
          rules: [],
        });
      }

      return Response.json({ detail: "not found" }, { status: 404 });
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function openTermsPage() {
  fireEvent.click(await screen.findByRole("button", { name: "Terms" }));
  await screen.findByRole("heading", { name: "Terminology control plane" });
}

async function openSnapshotsPage() {
  fireEvent.click(await screen.findByRole("button", { name: "Snapshots" }));
  await screen.findByRole("heading", { name: "Runtime snapshots" });
}

async function openSearchPlaygroundPage() {
  fireEvent.click(
    await screen.findByRole("button", { name: "Search Playground" }),
  );
  await screen.findByRole("heading", { name: "Search Playground" });
}

describe("App", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    window.localStorage.clear();
    document.documentElement.classList.remove("dark");
    document.documentElement.style.colorScheme = "";
  });

  it("renders the governance console with profiles and terms", async () => {
    stubGovernanceApi();

    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "Dashboard" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Runtime control center"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Production search context is ready."),
    ).toBeInTheDocument();
    expect(screen.getByText("Setup progress")).toBeInTheDocument();
    expect(screen.getByText("Pin snapshot")).toBeInTheDocument();
    expect(screen.getByText("Next actions")).toBeInTheDocument();
    const attentionBadge = screen.getByText("1 attention");
    expect(attentionBadge).toHaveClass("shrink-0");
    expect(attentionBadge).toHaveClass("whitespace-nowrap");
    expect(screen.getByText("Ready bindings")).toBeInTheDocument();

    await openTermsPage();

    await waitFor(() => {
      expect(screen.getAllByText("default_it").length).toBeGreaterThan(0);
    });

    await waitFor(() => {
      expect(screen.getAllByText("kubernetes").length).toBeGreaterThan(0);
    });
    expect(screen.getAllByText("k8s").length).toBeGreaterThan(0);
    expect(
      screen.getByText("Governed terminology workspace"),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Terms/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Profiles/ })).toBeInTheDocument();
    expect(screen.getByText("MVP")).toBeInTheDocument();
    expect(screen.queryByText("UI skeleton")).not.toBeInTheDocument();
  });

  it("shows runtime snapshots with active state and history", async () => {
    const fetchMock = stubGovernanceApi();

    render(<App />);

    await openSnapshotsPage();

    expect(await screen.findByText("Runtime audit")).toBeInTheDocument();
    expect(screen.getByText("Runtime bindings")).toBeInTheDocument();
    expect(screen.getByText("Needs attention")).toBeInTheDocument();
    expect(screen.getByText("Recent snapshot events")).toBeInTheDocument();
    expect(screen.getAllByText("default_it@abc123").length).toBeGreaterThan(0);
    expect(screen.getAllByText("ml_platform@old456").length).toBeGreaterThan(0);
    expect(screen.getByText("Pending: ml_platform@new789")).toBeInTheDocument();
    expect(screen.getByText("profile changed")).toBeInTheDocument();
    expect(
      screen.getByText("ml docs needs runtime attention"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Job #101").length).toBeGreaterThan(0);
    expect(screen.getAllByText("rollback available").length).toBeGreaterThan(0);

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8010/v1/snapshots/summary",
      expect.objectContaining({
        headers: expect.any(Headers),
      }),
    );
  });

  it("lets users preview and run runtime search from Search Playground", async () => {
    const fetchMock = stubGovernanceApi();

    render(<App />);

    await openSearchPlaygroundPage();

    expect(
      await screen.findByText("Runtime search playground"),
    ).toBeInTheDocument();
    expect(screen.getByText("Result preview")).toBeInTheDocument();
    expect(screen.getByText("Binding context")).toBeInTheDocument();
    expect(screen.getByText("default_it → docs")).toBeInTheDocument();
    expect(
      screen.getByRole("option", {
        name: "Binding: infra docs · Profile: default_it · Index: docs · Scope: team=infra",
      }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Binding").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Profile").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Index").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Preview query plan" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/query/plan",
        expect.objectContaining({
          body: JSON.stringify({
            binding_id: 1,
            query: "k8s pg timeout",
            size: 10,
            canonical_boost: 3,
            include_evidence: true,
          }),
          method: "POST",
        }),
      );
    });

    expect(await screen.findByText("Query plan")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Result-first view of how SkeinRank rewrites the query for this binding.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("kubernetes postgresql timeout"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("k8s").length).toBeGreaterThan(0);
    expect(screen.getAllByText("pg").length).toBeGreaterThan(0);
    expect(screen.getAllByText("default_it@abc123").length).toBeGreaterThan(0);
    expect(screen.getByText("Alias replacements")).toBeInTheDocument();
    expect(screen.getByText("Advanced details")).toBeInTheDocument();
    expect(screen.getByText("Elasticsearch DSL")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Run search" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/search",
        expect.objectContaining({
          body: JSON.stringify({
            binding_id: 1,
            query: "k8s pg timeout",
            size: 10,
            canonical_boost: 3,
            include_evidence: true,
            include_source: true,
          }),
          method: "POST",
        }),
      );
    });

    expect(await screen.findByText("Search result")).toBeInTheDocument();
    expect(screen.getByText("Search hits")).toBeInTheDocument();
    expect(screen.getByText("doc-1")).toBeInTheDocument();
    expect(screen.getByText("K8s pg timeout incident")).toBeInTheDocument();
  });

  it("collapses the sidebar into a compact rail and keeps navigation accessible", async () => {
    stubGovernanceApi();

    render(<App />);

    const collapseButton = await screen.findByRole("button", {
      name: "Collapse sidebar",
    });
    fireEvent.click(collapseButton);

    expect(window.localStorage.getItem("skeinrank-ui-sidebar-mode")).toBe(
      "collapsed",
    );
    expect(screen.getByRole("img", { name: "SkeinRank logo" })).toHaveAttribute(
      "src",
      "/skeinrank-logo.png",
    );
    expect(
      screen.queryByRole("button", { name: "Pin sidebar open" }),
    ).not.toBeInTheDocument();

    fireEvent.mouseEnter(screen.getByLabelText("Primary navigation"));
    expect(
      screen.getByRole("button", { name: "Pin sidebar open" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Terms" }));
    expect(
      await screen.findByRole("heading", { name: "Terminology control plane" }),
    ).toBeInTheDocument();
  });

  it("cycles the governance console theme", async () => {
    stubGovernanceApi();

    render(<App />);

    const themeButton = await screen.findByRole("button", {
      name: /switch theme/i,
    });
    expect(themeButton).toHaveTextContent("System");

    fireEvent.click(themeButton);
    expect(themeButton).toHaveTextContent("Light");
    expect(document.documentElement).not.toHaveClass("dark");

    fireEvent.click(themeButton);
    expect(themeButton).toHaveTextContent("Dark");
    expect(document.documentElement).toHaveClass("dark");
    expect(window.localStorage.getItem("skeinrank-ui-theme")).toBe("dark");
  });

  it("creates and renames a profile through the governance API", async () => {
    const fetchMock = stubGovernanceApi();

    render(<App />);

    await openTermsPage();
    fireEvent.click(screen.getByRole("tab", { name: /Profiles/ }));
    await screen.findByRole("button", { name: "Create profile" });

    fireEvent.change(screen.getByLabelText("New profile name"), {
      target: { value: "security_docs" },
    });
    fireEvent.change(screen.getByLabelText("New profile description"), {
      target: { value: "Security terminology" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create profile" }));

    await waitFor(() => {
      expect(screen.getAllByText("security_docs").length).toBeGreaterThan(0);
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8010/v1/governance/profiles",
      expect.objectContaining({
        body: JSON.stringify({
          name: "security_docs",
          description: "Security terminology",
        }),
        method: "POST",
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "default_it" }));
    fireEvent.change(screen.getByLabelText("Profile name"), {
      target: { value: "platform_terms" },
    });
    fireEvent.change(screen.getByLabelText("Profile description"), {
      target: { value: "Platform terminology" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));

    await waitFor(() => {
      expect(screen.getAllByText("platform_terms").length).toBeGreaterThan(0);
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8010/v1/governance/profiles/default_it",
      expect.objectContaining({
        body: JSON.stringify({
          name: "platform_terms",
          description: "Platform terminology",
        }),
        method: "PATCH",
      }),
    );
  });

  it("deletes a profile after confirmation", async () => {
    const fetchMock = stubGovernanceApi();
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<App />);

    await openTermsPage();
    fireEvent.click(screen.getByRole("tab", { name: /Profiles/ }));
    fireEvent.click(await screen.findByRole("button", { name: "default_it" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Delete profile" }),
    );

    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: "default_it" }),
      ).not.toBeInTheDocument();
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8010/v1/governance/profiles/default_it",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("adds a canonical term through the governance API", async () => {
    const fetchMock = stubGovernanceApi();

    render(<App />);

    await openTermsPage();
    await screen.findByText("default_it");

    fireEvent.click(screen.getByRole("button", { name: "Add term" }));

    fireEvent.change(screen.getByLabelText("Canonical value"), {
      target: { value: "postgresql" },
    });
    fireEvent.change(screen.getByLabelText("Slot"), {
      target: { value: "DB" },
    });
    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "PostgreSQL database" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create term" }));

    await waitFor(() => {
      expect(screen.getAllByText("postgresql").length).toBeGreaterThan(0);
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8010/v1/governance/profiles/default_it/terms",
      expect.objectContaining({
        body: JSON.stringify({
          canonical_value: "postgresql",
          slot: "DB",
          description: "PostgreSQL database",
          status: "active",
        }),
        method: "POST",
      }),
    );
  });

  it("updates and deletes canonical terms through the governance API", async () => {
    const fetchMock = stubGovernanceApi();
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<App />);

    await openTermsPage();
    await screen.findByText("default_it");
    await screen.findByLabelText("Edit canonical value");

    fireEvent.change(screen.getByLabelText("Edit canonical value"), {
      target: { value: "kubernetes" },
    });
    fireEvent.change(screen.getByLabelText("Edit slot"), {
      target: { value: "PLATFORM" },
    });
    fireEvent.change(screen.getByLabelText("Edit description"), {
      target: { value: "Container orchestration platform" },
    });
    fireEvent.change(screen.getByLabelText("Term status"), {
      target: { value: "deprecated" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save term" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/profiles/default_it/terms/kubernetes",
        expect.objectContaining({
          body: JSON.stringify({
            canonical_value: "kubernetes",
            slot: "PLATFORM",
            description: "Container orchestration platform",
            status: "deprecated",
          }),
          method: "PATCH",
        }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "Delete term" }));

    await waitFor(() => {
      expect(
        screen.getByText("No terms found for this profile."),
      ).toBeInTheDocument();
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8010/v1/governance/profiles/default_it/terms/kubernetes",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("adds an alias to the selected canonical term with manual confidence hidden", async () => {
    const fetchMock = stubGovernanceApi();

    render(<App />);

    await openTermsPage();
    await screen.findByText("default_it");
    const aliasInput = await screen.findByLabelText("Alias");

    expect(screen.queryByLabelText("Confidence")).not.toBeInTheDocument();

    fireEvent.change(aliasInput, { target: { value: "kube" } });
    fireEvent.change(screen.getByLabelText("Notes"), {
      target: { value: "Common Kubernetes shorthand" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add alias" }));

    await waitFor(() => {
      expect(screen.getAllByText("kube").length).toBeGreaterThan(0);
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8010/v1/governance/profiles/default_it/terms/kubernetes/aliases",
      expect.objectContaining({
        body: JSON.stringify({
          alias_value: "kube",
          confidence: 1,
          notes: "Common Kubernetes shorthand",
          status: "active",
        }),
        method: "POST",
      }),
    );
  });

  it("updates and deletes aliases through the governance API", async () => {
    const fetchMock = stubGovernanceApi();
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<App />);

    await openTermsPage();
    await screen.findByText("default_it");
    await screen.findByText("k8s");

    const editAliasButton = await screen.findByRole("button", {
      name: "Edit alias",
    });
    expect(editAliasButton).not.toBeDisabled();
    fireEvent.click(editAliasButton);
    const editAliasInput = await screen.findByLabelText("Edit alias");
    fireEvent.change(editAliasInput, { target: { value: "kube" } });
    fireEvent.change(screen.getByLabelText("Edit alias notes"), {
      target: { value: "Short Kubernetes alias" },
    });

    const aliasStatusSelect = screen.getByLabelText(
      "Alias status",
    ) as HTMLSelectElement;
    const aliasStatusOptions = Array.from(aliasStatusSelect.options).map(
      (option) => option.value,
    );
    expect(aliasStatusOptions).toEqual(["active", "deprecated", "disabled"]);
    expect(aliasStatusOptions).not.toContain("ambiguous");
    expect(aliasStatusOptions).not.toContain("pending");
    expect(aliasStatusOptions).not.toContain("rejected");

    fireEvent.change(aliasStatusSelect, { target: { value: "deprecated" } });
    fireEvent.click(screen.getByRole("button", { name: "Save alias" }));

    await waitFor(() => {
      expect(screen.getAllByText("kube").length).toBeGreaterThan(0);
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8010/v1/governance/profiles/default_it/terms/kubernetes/aliases/1",
      expect.objectContaining({
        body: JSON.stringify({
          alias_value: "kube",
          confidence: 1,
          notes: "Short Kubernetes alias",
          status: "deprecated",
        }),
        method: "PATCH",
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Delete alias" }));

    await waitFor(() => {
      expect(screen.queryByText("kube")).not.toBeInTheDocument();
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8010/v1/governance/profiles/default_it/terms/kubernetes/aliases/1",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("lets admins check Elasticsearch evidence for terms", async () => {
    const fetchMock = stubGovernanceApi();

    render(<App />);

    await openTermsPage();
    expect(await screen.findByText("Evidence check")).toBeInTheDocument();
    expect(await screen.findByText("infra docs · docs")).toBeInTheDocument();

    const checkEvidenceButtons = screen.getAllByRole("button", {
      name: "Check evidence",
    });
    fireEvent.click(checkEvidenceButtons[checkEvidenceButtons.length - 1]);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/elasticsearch/bindings/1/evidence",
        expect.objectContaining({
          body: JSON.stringify({
            canonical_value: "kubernetes",
            max_documents: 5,
            query: "kubernetes",
          }),
          method: "POST",
        }),
      );
    });
    expect(await screen.findByText(/Evidence mentions/)).toBeInTheDocument();
    expect(screen.getAllByText("kubernetes").length).toBeGreaterThan(0);
    expect(
      screen.queryByRole("button", { name: "Export draft snapshot" }),
    ).not.toBeInTheDocument();
  });

  it("signs in when auth is enabled and sends bearer tokens", async () => {
    const fetchMock = stubGovernanceApi({ authRequired: true });

    render(<App />);

    expect(await screen.findByText("SkeinRank sign in")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Username"), {
      target: { value: "admin" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "change-me" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await openTermsPage();
    await screen.findByText("default_it");

    const profileRequest = fetchMock.mock.calls.find(([url]) =>
      url.toString().endsWith("/v1/governance/profiles"),
    );
    expect(profileRequest).toBeTruthy();
    expect(new Headers(profileRequest?.[1]?.headers).get("Authorization")).toBe(
      "Bearer test-token",
    );
    expect(window.localStorage.getItem("skeinrank-ui-auth-token")).toBe(
      "test-token",
    );
  });

  it("lets admins manage users from the Users page", async () => {
    const fetchMock = stubGovernanceApi();
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<App />);

    await openTermsPage();
    fireEvent.click(screen.getByRole("button", { name: "Users" }));

    expect(await screen.findByText("Access management control plane")).toBeInTheDocument();
    expect(await screen.findByText("Governance users")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByText("Admin User").length).toBeGreaterThan(0);
    });
    expect(screen.getByText("Status semantics")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("New username"), {
      target: { value: "alex" },
    });
    fireEvent.change(screen.getByLabelText("New display name"), {
      target: { value: "Alex Kim" },
    });
    fireEvent.change(screen.getByLabelText("Temporary password"), {
      target: { value: "temporary-password" },
    });
    fireEvent.change(screen.getByLabelText("New user role"), {
      target: { value: "moderator" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create user" }));

    await screen.findByText("Alex Kim");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8010/v1/auth/users",
      expect.objectContaining({
        body: JSON.stringify({
          username: "alex",
          password: "temporary-password",
          display_name: "Alex Kim",
          role: "moderator",
          status: "active",
        }),
        method: "POST",
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: /contributor/i }));
    fireEvent.change(screen.getByLabelText("Display name"), {
      target: { value: "Term Contributor" },
    });
    fireEvent.change(screen.getByLabelText("Role"), {
      target: { value: "moderator" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save user" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/auth/users/contributor",
        expect.objectContaining({
          body: JSON.stringify({
            username: "contributor",
            display_name: "Term Contributor",
            password: null,
            role: "moderator",
          }),
          method: "PATCH",
        }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "Suspend" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/auth/users/contributor/status",
        expect.objectContaining({
          body: JSON.stringify({ status: "suspended" }),
          method: "PATCH",
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getAllByText("suspended").length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByRole("button", { name: "Reactivate" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/auth/users/contributor/status",
        expect.objectContaining({
          body: JSON.stringify({ status: "active" }),
          method: "PATCH",
        }),
      );
    });

    fireEvent.click(
      screen.getByRole("button", { name: "Revoke all API tokens" }),
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/auth/users/contributor/revoke-api-tokens",
        expect.objectContaining({ method: "POST" }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "Delete user" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/auth/users/contributor",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
  });

  it("lets admins manage global stop-list guardrails", async () => {
    const fetchMock = stubGovernanceApi();
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<App />);

    await openTermsPage();
    fireEvent.click(screen.getByRole("button", { name: "Guardrails" }));

    expect(await screen.findByText("Global stop list")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByText("unknown").length).toBeGreaterThan(0);
    });
    expect(screen.getByRole("tab", { name: /Global/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Profile/ })).toBeInTheDocument();
    expect(
      screen.getByText("Too generic across every profile"),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Global blocked value"), {
      target: { value: "noise" },
    });
    fireEvent.change(screen.getByLabelText("Global target"), {
      target: { value: "both" },
    });
    fireEvent.change(screen.getByLabelText("Global reason"), {
      target: { value: "Generic global placeholder" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Add to global stop list" }),
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/global-stop-list",
        expect.objectContaining({
          body: JSON.stringify({
            value: "noise",
            target: "both",
            reason: "Generic global placeholder",
            is_active: true,
          }),
          method: "POST",
        }),
      );
    });
    expect((await screen.findAllByText("noise")).length).toBeGreaterThanOrEqual(
      1,
    );

    fireEvent.click(screen.getAllByText("unknown")[0]);
    fireEvent.change(screen.getByLabelText("Edit global blocked value"), {
      target: { value: "unknown-value" },
    });
    fireEvent.change(screen.getByLabelText("Edit global target"), {
      target: { value: "canonical" },
    });
    fireEvent.change(screen.getByLabelText("Edit global reason"), {
      target: { value: "Reserved global placeholder" },
    });
    fireEvent.click(screen.getByLabelText("Active global guardrail"));
    fireEvent.click(
      screen.getByRole("button", { name: "Save global stop-list entry" }),
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/global-stop-list/1",
        expect.objectContaining({
          body: JSON.stringify({
            value: "unknown-value",
            target: "canonical",
            reason: "Reserved global placeholder",
            is_active: false,
          }),
          method: "PATCH",
        }),
      );
    });

    fireEvent.click(
      screen.getByRole("button", { name: "Delete global stop-list entry" }),
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/global-stop-list/1",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
  });

  it("marks inherited global stop-list entries as read-only for profiles", async () => {
    stubGovernanceApi();

    render(<App />);

    await openTermsPage();
    fireEvent.click(screen.getByRole("button", { name: "Guardrails" }));
    fireEvent.click(await screen.findByRole("tab", { name: /Profile/ }));

    expect(
      await screen.findByText("Inherited global stop list"),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByText("unknown").length).toBeGreaterThan(0);
    });

    fireEvent.change(screen.getByLabelText("Blocked value"), {
      target: { value: "unknown" },
    });
    fireEvent.change(screen.getByLabelText("Target"), {
      target: { value: "alias" },
    });

    expect(
      await screen.findByText(/This value is already blocked globally/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Add to stop list" }),
    ).toBeDisabled();
  });

  it("lets admins manage profile stop-list guardrails", async () => {
    const fetchMock = stubGovernanceApi();
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<App />);

    await openTermsPage();
    fireEvent.click(screen.getByRole("button", { name: "Guardrails" }));
    fireEvent.click(await screen.findByRole("tab", { name: /Profile/ }));

    expect(await screen.findByText("Profile scope")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByText("service").length).toBeGreaterThan(0);
    });
    expect(
      screen.getByText("Too generic for incident search"),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Blocked value"), {
      target: { value: "app" },
    });
    fireEvent.change(screen.getByLabelText("Target"), {
      target: { value: "both" },
    });
    fireEvent.change(screen.getByLabelText("Reason"), {
      target: { value: "Too broad for runtime matching" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add to stop list" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/profiles/default_it/stop-list",
        expect.objectContaining({
          body: JSON.stringify({
            value: "app",
            target: "both",
            reason: "Too broad for runtime matching",
            is_active: true,
          }),
          method: "POST",
        }),
      );
    });
    expect((await screen.findAllByText("app")).length).toBeGreaterThanOrEqual(
      1,
    );

    fireEvent.click(screen.getAllByText("service")[0]);
    fireEvent.change(screen.getByLabelText("Edit blocked value"), {
      target: { value: "svc" },
    });
    fireEvent.change(screen.getByLabelText("Edit target"), {
      target: { value: "canonical" },
    });
    fireEvent.change(screen.getByLabelText("Edit reason"), {
      target: { value: "Reserved internal abbreviation" },
    });
    fireEvent.click(screen.getByLabelText("Active guardrail"));
    fireEvent.click(
      screen.getByRole("button", { name: "Save stop-list entry" }),
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/profiles/default_it/stop-list/1",
        expect.objectContaining({
          body: JSON.stringify({
            value: "svc",
            target: "canonical",
            reason: "Reserved internal abbreviation",
            is_active: false,
          }),
          method: "PATCH",
        }),
      );
    });

    fireEvent.click(
      screen.getByRole("button", { name: "Delete stop-list entry" }),
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/profiles/default_it/stop-list/1",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
  });

  it("keeps contributor users in read-only guardrails mode", async () => {
    stubGovernanceApi({ currentUser: contributorUser });

    render(<App />);

    await openTermsPage();
    fireEvent.click(screen.getByRole("button", { name: "Guardrails" }));
    fireEvent.click(await screen.findByRole("tab", { name: /Profile/ }));

    await waitFor(() => {
      expect(screen.getAllByText("service").length).toBeGreaterThan(0);
    });
    expect(
      screen.getByRole("button", { name: "Add to stop list" }),
    ).toBeDisabled();
    expect(
      screen.getByText(
        "Your role can inspect guardrails, but only admins and moderators can update stop lists.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Contributors can inspect stop lists, but only admins and moderators can update guardrails.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Save stop-list entry" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Delete stop-list entry" }),
    ).toBeDisabled();
  });

  it("lets admins manage Elasticsearch enrichment bindings", async () => {
    const fetchMock = stubGovernanceApi();
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<App />);

    await openTermsPage();
    fireEvent.click(screen.getByRole("button", { name: "Integrations" }));

    expect(
      await screen.findByText("Elasticsearch runtime bindings"),
    ).toBeInTheDocument();
    expect(screen.getByText("Integrations cockpit")).toBeInTheDocument();
    expect(screen.getByText("Binding inventory")).toBeInTheDocument();
    expect(screen.getByText("Elasticsearch bindings")).toBeInTheDocument();
    expect(await screen.findByText("Connected")).toBeInTheDocument();
    expect(screen.queryByText("Binding setup flow")).not.toBeInTheDocument();
    expect(screen.queryByText("Binding patterns")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Hide details" }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByText("infra docs").length).toBeGreaterThan(0);
    });
    fireEvent.click(screen.getAllByText("infra docs")[0]);
    expect(await screen.findByText("Selected binding")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Create binding" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit binding" }));
    await waitFor(() => {
      expect(screen.getByLabelText("Edit description")).toHaveValue(
        "Apply default IT terms to docs.",
      );
    });
    expect(screen.getAllByText("Runtime snapshot").length).toBeGreaterThan(0);
    expect(screen.getAllByText("ready").length).toBeGreaterThan(0);
    expect(screen.getAllByText("default_it@abc123").length).toBeGreaterThan(0);
    expect(screen.getAllByText("#101").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Run dry-run" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/elasticsearch/bindings/1/dry-run",
        expect.objectContaining({
          body: JSON.stringify({ limit: 3 }),
          method: "POST",
        }),
      );
    });
    expect(await screen.findByText("doc-1")).toBeInTheDocument();
    expect(screen.getByText("k8s → kubernetes")).toBeInTheDocument();

    expect(await screen.findByText("Job history")).toBeInTheDocument();
    expect(await screen.findByText("Job #101")).toBeInTheDocument();
    expect(screen.getByText("10/12")).toBeInTheDocument();
    expect(screen.getByText("4/4 chunks")).toBeInTheDocument();
    expect(screen.getAllByText("default_it@old001").length).toBeGreaterThan(0);
    expect(screen.getByText("Rollout metadata")).toBeInTheDocument();
    expect(screen.getAllByText("docs_v1").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Rollback alias" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/elasticsearch/jobs/101/rollback",
        expect.objectContaining({
          body: JSON.stringify({
            reason: "Rollback requested from Integrations UI.",
          }),
          method: "POST",
        }),
      );
    });
    expect(
      (await screen.findAllByText(/Rollback completed/)).length,
    ).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText("Job target index"), {
      target: { value: "docs__skeinrank_candidate" },
    });
    fireEvent.change(screen.getByLabelText("Job alias name"), {
      target: { value: "docs" },
    });
    fireEvent.change(screen.getByLabelText("Max documents"), {
      target: { value: "25" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run enrichment job" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/elasticsearch/bindings/1/jobs",
        expect.objectContaining({
          body: JSON.stringify({
            max_documents: 25,
            target_index_name: "docs__skeinrank_candidate",
            alias_name: "docs",
          }),
          method: "POST",
        }),
      );
    });
    expect(await screen.findByText("Job #102")).toBeInTheDocument();
    expect(screen.getByText(/doc-3/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel job" }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/elasticsearch/jobs/102/cancel",
        expect.objectContaining({
          body: JSON.stringify({ reason: "Cancelled from Integrations UI." }),
          method: "POST",
        }),
      );
    });
    expect(
      (await screen.findAllByText("cancel_requested")).length,
    ).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Create binding" }));
    expect(
      await screen.findByText("Profile and binding identity"),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Binding name"), {
      target: { value: "runbook docs" },
    });
    fireEvent.change(screen.getByLabelText("Index"), {
      target: { value: "runbooks" },
    });
    expect(
      await screen.findByText("Discovered text fields"),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Text fields/), {
      target: { value: "title, body, summary" },
    });
    fireEvent.change(screen.getByLabelText("Target field"), {
      target: { value: "skeinrank" },
    });
    fireEvent.change(screen.getByLabelText("Document discriminator field"), {
      target: { value: "team" },
    });
    fireEvent.change(screen.getByLabelText("Value for this profile"), {
      target: { value: "infra" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save new binding" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/elasticsearch/bindings",
        expect.objectContaining({
          body: JSON.stringify({
            name: "runbook docs",
            profile_name: "default_it",
            description: null,
            index_name: "runbooks",
            text_fields: ["title", "body", "summary"],
            target_field: "skeinrank",
            filter_field: "team",
            filter_value: "infra",
            timestamp_field: null,
            time_window_days: null,
            mode: "dry_run",
            write_strategy: "reindex_alias_swap",
            is_enabled: true,
          }),
          method: "POST",
        }),
      );
    });
    expect(
      (await screen.findAllByText("runbook docs")).length,
    ).toBeGreaterThanOrEqual(1);

    fireEvent.click(screen.getAllByText("infra docs")[0]);
    fireEvent.click(screen.getByRole("button", { name: "Edit binding" }));
    fireEvent.change(screen.getByLabelText("Edit binding name"), {
      target: { value: "infra docs v2" },
    });
    fireEvent.change(screen.getByLabelText("Edit index"), {
      target: { value: "docs-v2" },
    });
    fireEvent.change(screen.getByLabelText("Edit text fields"), {
      target: { value: "title\nbody" },
    });
    fireEvent.change(screen.getByLabelText("Edit target field"), {
      target: { value: "skeinrank_attrs" },
    });
    fireEvent.change(
      screen.getByLabelText("Edit document discriminator field"),
      { target: { value: "space" } },
    );
    fireEvent.change(screen.getByLabelText("Edit value for this profile"), {
      target: { value: "infra" },
    });
    fireEvent.change(screen.getByLabelText("Edit mode"), {
      target: { value: "write" },
    });
    fireEvent.click(screen.getByLabelText("Edit enabled binding"));
    fireEvent.click(screen.getByRole("button", { name: "Save binding" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/elasticsearch/bindings/1",
        expect.objectContaining({
          body: JSON.stringify({
            name: "infra docs v2",
            profile_name: "default_it",
            description: "Apply default IT terms to docs.",
            index_name: "docs-v2",
            text_fields: ["title", "body"],
            target_field: "skeinrank_attrs",
            filter_field: "space",
            filter_value: "infra",
            timestamp_field: "created_at",
            time_window_days: 1825,
            mode: "write",
            write_strategy: "reindex_alias_swap",
            is_enabled: false,
          }),
          method: "PATCH",
        }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "Edit binding" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete binding" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/elasticsearch/bindings/1",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
  });

  it("requires a discriminator when multiple profiles share one Elasticsearch index", async () => {
    stubGovernanceApi();

    render(<App />);

    await openTermsPage();
    fireEvent.click(screen.getByRole("button", { name: "Integrations" }));

    expect(
      await screen.findByText("Elasticsearch bindings"),
    ).toBeInTheDocument();
    expect(await screen.findByText("Connected")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Create binding" }));
    expect(
      await screen.findByText("Profile and binding identity"),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Profile"), {
      target: { value: "ml_platform" },
    });
    fireEvent.change(screen.getByLabelText("Binding name"), {
      target: { value: "ml docs without discriminator" },
    });
    fireEvent.change(screen.getByLabelText("Index"), {
      target: { value: "docs" },
    });
    fireEvent.change(screen.getByLabelText(/Text fields/), {
      target: { value: "title, body" },
    });
    fireEvent.change(screen.getByLabelText("Target field"), {
      target: { value: "skeinrank" },
    });

    expect(
      await screen.findByText(/This index is already used by another profile/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Save new binding" }),
    ).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Document discriminator field"), {
      target: { value: "team" },
    });
    fireEvent.change(screen.getByLabelText("Value for this profile"), {
      target: { value: "ml-platform" },
    });

    expect(
      (
        await screen.findAllByText(
          /The discriminator keeps this profile scoped/,
        )
      ).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByRole("button", { name: "Save new binding" }),
    ).not.toBeDisabled();
  });

  it("lets admins run enrichment jobs from the jobs panel", async () => {
    const fetchMock = stubGovernanceApi();

    render(<App />);

    await openTermsPage();
    fireEvent.click(screen.getByRole("button", { name: "Integrations" }));
    fireEvent.click(
      await screen.findByRole("tab", { name: "Enrichment jobs" }),
    );

    expect(
      await screen.findByText("Binding rollout queue"),
    ).toBeInTheDocument();
    expect(screen.getByText("Active jobs")).toBeInTheDocument();
    expect(screen.getByLabelText("Default max documents")).toHaveValue(1000);

    fireEvent.change(screen.getByLabelText("Default max documents"), {
      target: { value: "50" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Run default job" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/elasticsearch/bindings/1/jobs",
        expect.objectContaining({
          body: JSON.stringify({ max_documents: 50 }),
          method: "POST",
        }),
      );
    });
    expect((await screen.findAllByText("#102")).length).toBeGreaterThan(0);
  });

  it("shows integrations graph view and opens selected binding", async () => {
    stubGovernanceApi();

    render(<App />);

    await openTermsPage();
    fireEvent.click(screen.getByRole("button", { name: "Integrations" }));
    fireEvent.click(await screen.findByRole("tab", { name: "Graph view" }));

    expect(await screen.findByText("Integration topology")).toBeInTheDocument();
    expect(screen.getByText("Topology canvas")).toBeInTheDocument();
    expect(screen.getByText("Profiles")).toBeInTheDocument();
    expect(screen.getAllByText("Bindings").length).toBeGreaterThan(0);
    expect(screen.getByText("Indexes / aliases")).toBeInTheDocument();
    expect(screen.getByText("Runtime snapshots")).toBeInTheDocument();
    expect(screen.getByLabelText("Graph scope")).toHaveValue("all");
    expect(
      screen.getByText("docs: default_it, ml_platform"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("shared index").length).toBeGreaterThan(0);
    expect(screen.getAllByText("default_it@abc123").length).toBeGreaterThan(0);

    fireEvent.click(screen.getAllByRole("button", { name: "Open binding" })[0]);

    expect(await screen.findByText("Selected binding")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Bindings" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("keeps contributor users in read-only integrations mode", async () => {
    stubGovernanceApi({ currentUser: contributorUser });

    render(<App />);

    await openTermsPage();
    fireEvent.click(screen.getByRole("button", { name: "Integrations" }));

    await waitFor(() => {
      expect(screen.getAllByText("infra docs").length).toBeGreaterThan(0);
    });
    expect(
      screen.getByRole("button", { name: "Create binding" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Run enrichment job" }),
    ).toBeDisabled();
    expect(
      screen.getByText(
        "Your role can inspect Elasticsearch bindings, but only admins and moderators can update integrations.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Contributors can inspect bindings, but only admins and moderators can update Elasticsearch integration configs.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit binding" })).toBeDisabled();
    expect(
      screen.queryByRole("button", { name: "Save binding" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Delete binding" }),
    ).not.toBeInTheDocument();
  });

  it("keeps contributor users in read-only governance mode", async () => {
    stubGovernanceApi({ currentUser: contributorUser });

    render(<App />);

    await openTermsPage();
    await screen.findByText("default_it");
    await screen.findByText("kubernetes");

    expect(
      screen.queryByRole("button", { name: "Users" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add term" })).toBeDisabled();
    expect(
      screen.queryByRole("button", { name: "Edit alias" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(
        "Your role has read-only access to this terminology profile. Use the Suggestions tab to propose changes for review.",
      ),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /Profiles/ }));
    expect(
      screen.getByRole("button", { name: "Create profile" }),
    ).toBeDisabled();
  });

  it("lets contributors create suggestions without review actions", async () => {
    const fetchMock = stubGovernanceApi({ currentUser: contributorUser });

    render(<App />);

    await openTermsPage();
    fireEvent.click(screen.getByRole("button", { name: "Suggestions" }));

    expect(
      await screen.findByText("Suggestions and approvals"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Review terminology proposals"),
    ).toBeInTheDocument();
    expect(await screen.findByText("Suggestion workspace")).toBeInTheDocument();
    expect(screen.getByText("Pending review")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Propose/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(
      screen.queryByRole("button", { name: /Approve suggestion/ }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /Review queue/ }));
    expect(
      await screen.findByText("People search for kube in incident docs."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Contributors can create suggestions, but only admins and moderators can approve or reject them.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Approve suggestion/ }),
    ).toBeDisabled();

    fireEvent.click(screen.getByRole("tab", { name: /Propose/ }));
    expect(screen.queryByLabelText("Confidence")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Source")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Canonical term"), {
      target: { value: "kube" },
    });
    fireEvent.click(
      await screen.findByRole("button", { name: /kubernetes.*1 aliases/i }),
    );
    expect(screen.getByLabelText("Slot")).toHaveValue("TOOL");
    expect(screen.getByText("Existing aliases")).toBeInTheDocument();
    expect(screen.getByText("k8s")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Suggested alias"), {
      target: { value: "k8s-prod" },
    });
    fireEvent.change(screen.getByLabelText("Context"), {
      target: { value: "Support tickets mention k8s-prod." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create suggestion" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/profiles/default_it/suggestions",
        expect.objectContaining({
          body: JSON.stringify({
            suggestion_type: "alias",
            canonical_value: "kubernetes",
            alias_value: "k8s-prod",
            slot: "TOOL",
            confidence: 1,
            source: "manual",
            context: "Support tickets mention k8s-prod.",
          }),
          method: "POST",
        }),
      );
    });

    expect(screen.getByRole("tab", { name: /Propose/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(
      screen.getByText("Suggestion queued for review"),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "View in Review queue" }),
    );
    expect(screen.getByRole("tab", { name: /Review queue/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("blocks duplicate alias suggestions for the selected canonical term", async () => {
    stubGovernanceApi({ currentUser: contributorUser });

    render(<App />);

    await openTermsPage();
    fireEvent.click(screen.getByRole("button", { name: "Suggestions" }));

    expect(
      await screen.findByText("Suggestions and approvals"),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Canonical term"), {
      target: { value: "kubernetes" },
    });
    fireEvent.click(
      await screen.findByRole("button", { name: /kubernetes.*1 aliases/i }),
    );
    fireEvent.change(screen.getByLabelText("Suggested alias"), {
      target: { value: "k8s" },
    });

    expect(
      await screen.findByText(/This alias already exists for kubernetes/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Create suggestion" }),
    ).toBeDisabled();
  });

  it("lets contributors suggest new canonical terms", async () => {
    const fetchMock = stubGovernanceApi({ currentUser: contributorUser });

    render(<App />);

    await openTermsPage();
    fireEvent.click(screen.getByRole("button", { name: "Suggestions" }));

    expect(
      await screen.findByText("Suggestions and approvals"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /New canonical term/ }));
    fireEvent.change(screen.getByLabelText("New canonical term"), {
      target: { value: "vector database" },
    });
    fireEvent.change(screen.getByLabelText("Slot"), {
      target: { value: "TOOL" },
    });
    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "Storage optimized for vector similarity search." },
    });
    fireEvent.change(screen.getByLabelText("Context"), {
      target: { value: "No canonical term exists for vectordb searches." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create suggestion" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/profiles/default_it/suggestions",
        expect.objectContaining({
          body: JSON.stringify({
            suggestion_type: "canonical_term",
            canonical_value: "vector database",
            alias_value: null,
            slot: "TOOL",
            description: "Storage optimized for vector similarity search.",
            confidence: 1,
            source: "manual",
            context: "No canonical term exists for vectordb searches.",
          }),
          method: "POST",
        }),
      );
    });

    expect(
      await screen.findByText("Suggestion queued for review"),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Propose/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("blocks duplicate canonical term suggestions", async () => {
    stubGovernanceApi({ currentUser: contributorUser });

    render(<App />);

    await openTermsPage();
    fireEvent.click(screen.getByRole("button", { name: "Suggestions" }));

    expect(
      await screen.findByText("Suggestions and approvals"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /New canonical term/ }));
    fireEvent.change(screen.getByLabelText("New canonical term"), {
      target: { value: "kubernetes" },
    });
    fireEvent.change(screen.getByLabelText("Slot"), {
      target: { value: "TOOL" },
    });

    expect(
      await screen.findByText(/This canonical term already exists/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Create suggestion" }),
    ).toBeDisabled();
  });

  it("lets reviewers refresh suggestion evidence snapshots", async () => {
    const fetchMock = stubGovernanceApi({ currentUser: moderatorUser });

    render(<App />);

    await openTermsPage();
    fireEvent.click(screen.getByRole("button", { name: "Suggestions" }));

    expect(
      await screen.findByText("Suggestions and approvals"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Evidence from Elasticsearch"),
    ).toBeInTheDocument();
    expect(screen.getByText("No snapshot")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Check evidence" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/profiles/default_it/suggestions/1/evidence/refresh",
        expect.objectContaining({
          body: JSON.stringify({
            binding_id: 1,
            max_documents: 5,
            query: "kube",
          }),
          method: "POST",
        }),
      );
    });

    expect(await screen.findByText("Snapshot saved")).toBeInTheDocument();
    expect(
      await screen.findByText(/This runbook explains/),
    ).toBeInTheDocument();
    expect(screen.getAllByText("kube").length).toBeGreaterThan(0);
  });

  it("lets moderators approve suggestions into active aliases", async () => {
    const fetchMock = stubGovernanceApi({ currentUser: moderatorUser });

    render(<App />);

    await openTermsPage();
    fireEvent.click(screen.getByRole("button", { name: "Suggestions" }));

    expect(
      await screen.findByText("Suggestions and approvals"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("People search for kube in incident docs."),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Review comment"), {
      target: { value: "Looks valid for Kubernetes docs." },
    });
    fireEvent.click(screen.getByRole("button", { name: /Approve suggestion/ }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/profiles/default_it/suggestions/1/approve",
        expect.objectContaining({
          body: JSON.stringify({
            review_comment: "Looks valid for Kubernetes docs.",
          }),
          method: "POST",
        }),
      );
    });

    await waitFor(() => {
      expect(
        screen.getByText("No suggestions found for this filter."),
      ).toBeInTheDocument();
    });
    expect(
      screen.queryByText("This suggestion has already been reviewed."),
    ).not.toBeInTheDocument();
  });

  it("lets admins reject suggestions with a review comment", async () => {
    const fetchMock = stubGovernanceApi();

    render(<App />);

    await openTermsPage();
    fireEvent.click(screen.getByRole("button", { name: "Suggestions" }));

    expect(
      await screen.findByText("Suggestions and approvals"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("People search for kube in incident docs."),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Review comment"), {
      target: { value: "Too ambiguous for the default profile." },
    });
    fireEvent.click(screen.getByRole("button", { name: /Reject suggestion/ }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/profiles/default_it/suggestions/1/reject",
        expect.objectContaining({
          body: JSON.stringify({
            review_comment: "Too ambiguous for the default profile.",
          }),
          method: "POST",
        }),
      );
    });

    await waitFor(() => {
      expect(
        screen.getByText("No suggestions found for this filter."),
      ).toBeInTheDocument();
    });
    expect(
      screen.queryByText("This suggestion has already been reviewed."),
    ).not.toBeInTheDocument();
  });

  it("shows governance API conflicts when a canonical term cannot be added", async () => {
    stubGovernanceApi({ duplicateTerm: true });

    render(<App />);

    await openTermsPage();
    await screen.findByText("default_it");

    fireEvent.click(screen.getByRole("button", { name: "Add term" }));

    fireEvent.change(screen.getByLabelText("Canonical value"), {
      target: { value: "kubernetes" },
    });
    fireEvent.change(screen.getByLabelText("Slot"), {
      target: { value: "TOOL" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create term" }));

    expect(
      await screen.findByText(
        "Term already exists in profile 'default_it': kubernetes",
      ),
    ).toBeInTheDocument();
  });
  it("lets users create and revoke personal API tokens", async () => {
    const fetchMock = stubGovernanceApi();
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<App />);

    await openTermsPage();
    fireEvent.click(screen.getByRole("button", { name: "API Access" }));

    expect(await screen.findByText("API security control plane")).toBeInTheDocument();
    expect(screen.getByText("Issue personal token")).toBeInTheDocument();
    expect(await screen.findByText("My API tokens")).toBeInTheDocument();
    expect(
      await screen.findByText("Existing Jupyter token"),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Create personal token name"), {
      target: { value: "Notebook import token" },
    });
    fireEvent.change(
      screen.getByLabelText("Create personal token expiration days"),
      {
        target: { value: "30" },
      },
    );
    fireEvent.click(screen.getAllByLabelText("migration:apply")[0]);
    fireEvent.click(
      screen.getByRole("button", { name: "Create personal token" }),
    );

    expect(await screen.findByTestId("copy-once-token")).toHaveTextContent(
      "sk_pat_plaintext",
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8010/v1/auth/api-tokens",
      expect.objectContaining({
        body: JSON.stringify({
          name: "Notebook import token",
          scopes: ["migration:validate", "migration:export", "migration:apply"],
          expires_in_days: 30,
        }),
        method: "POST",
      }),
    );

    fireEvent.click(screen.getAllByRole("button", { name: "Revoke" })[0]);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/auth/api-tokens/20",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
  });

  it("lets admins manage service accounts and service tokens", async () => {
    const fetchMock = stubGovernanceApi();
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<App />);

    await openTermsPage();
    fireEvent.click(screen.getByRole("button", { name: "API Access" }));

    fireEvent.click(screen.getByRole("tab", { name: /Service accounts/ }));

    expect(await screen.findByText("Service account identities")).toBeInTheDocument();
    expect(screen.getByText("Automation details")).toBeInTheDocument();
    expect(await screen.findByText("Migration Bot")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Service account name"), {
      target: { value: "sync-bot" },
    });
    fireEvent.change(screen.getByLabelText("Service account display name"), {
      target: { value: "Sync Bot" },
    });
    fireEvent.change(screen.getByLabelText("Service account description"), {
      target: { value: "Nightly dictionary sync" },
    });
    fireEvent.change(screen.getByLabelText("Service account role"), {
      target: { value: "moderator" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Create service account" }),
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/auth/service-accounts",
        expect.objectContaining({
          body: JSON.stringify({
            name: "sync-bot",
            display_name: "Sync Bot",
            description: "Nightly dictionary sync",
            role: "moderator",
            is_active: true,
          }),
          method: "POST",
        }),
      );
    });

    fireEvent.click(
      await screen.findByRole("button", { name: "Migration Bot" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Suspend service account" }),
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/auth/service-accounts/migration-bot",
        expect.objectContaining({
          body: JSON.stringify({ is_active: false }),
          method: "PATCH",
        }),
      );
    });

    fireEvent.click(
      await screen.findByRole("button", { name: "Reactivate service account" }),
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/auth/service-accounts/migration-bot",
        expect.objectContaining({
          body: JSON.stringify({ is_active: true }),
          method: "PATCH",
        }),
      );
    });

    fireEvent.change(screen.getByLabelText("Create service token name"), {
      target: { value: "CI import token" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Create service token" }),
    );

    expect(await screen.findByTestId("copy-once-token")).toHaveTextContent(
      "sk_sat_plaintext",
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8010/v1/auth/service-accounts/migration-bot/tokens",
      expect.objectContaining({
        body: JSON.stringify({
          name: "CI import token",
          scopes: ["migration:validate", "migration:export"],
          expires_in_days: 90,
        }),
        method: "POST",
      }),
    );

    fireEvent.click(screen.getAllByRole("button", { name: "Revoke" })[0]);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/auth/service-accounts/migration-bot/tokens/30",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
  });

  it("keeps service account management admin-only", async () => {
    stubGovernanceApi({ currentUser: contributorUser });

    render(<App />);

    await openTermsPage();
    fireEvent.click(screen.getByRole("button", { name: "API Access" }));

    expect(await screen.findByText("My API tokens")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Service accounts/ }));
    expect(
      screen.getByText(
        "Service accounts are visible to admins only. You can still create and revoke your own personal API tokens from the Personal tokens section.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Create service account" }),
    ).not.toBeInTheDocument();
  });
});
