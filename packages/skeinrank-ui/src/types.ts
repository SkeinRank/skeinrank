export type DashboardReadinessItem = {
  status: string;
  configured: boolean;
  message: string | null;
  url: string | null;
  name: string | null;
  version: string | null;
};

export type DashboardCounts = {
  profiles: number;
  canonical_terms: number;
  aliases: number;
  bindings: number;
  ready_bindings: number;
  stale_bindings: number;
  updating_bindings: number;
  failed_bindings: number;
  never_enriched_bindings: number;
  running_jobs: number;
  failed_jobs: number;
};

export type DashboardSetupChecklist = {
  has_profile: boolean;
  has_terms: boolean;
  has_binding: boolean;
  has_successful_enrichment: boolean;
  has_runtime_snapshot: boolean;
};

export type DashboardRecentJob = {
  id: number;
  binding_id: number;
  binding_name: string;
  profile_name: string;
  status: string;
  source_index: string;
  target_index: string | null;
  alias_name: string | null;
  snapshot_version: string | null;
  documents_seen: number;
  documents_enriched: number;
  documents_failed: number;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
};

export type DashboardBindingSummary = {
  id: number;
  name: string;
  profile_name: string;
  index_name: string;
  is_enabled: boolean;
  status: string;
  snapshot_version: string | null;
  pending_snapshot_version: string | null;
  last_successful_job_id: number | null;
  latest_job: DashboardRecentJob | null;
  updated_at: string;
};

export type DashboardSummary = {
  readiness: Record<string, DashboardReadinessItem>;
  counts: DashboardCounts;
  setup: DashboardSetupChecklist;
  bindings: DashboardBindingSummary[];
  recent_jobs: DashboardRecentJob[];
};

export type SnapshotDiffSummary = {
  active_checksum: string | null;
  current_checksum: string | null;
  active_aliases: number;
  current_aliases: number;
  added_aliases: number;
  removed_aliases: number;
  changed_aliases: number;
  changed: boolean;
};

export type SnapshotBindingState = {
  id: number;
  name: string;
  profile_name: string;
  index_name: string;
  filter_field: string | null;
  filter_value: string | null;
  is_enabled: boolean;
  status: string;
  active_snapshot_version: string | null;
  pending_snapshot_version: string | null;
  last_successful_snapshot_at: string | null;
  last_successful_job_id: number | null;
  latest_job_id: number | null;
  latest_job_status: string | null;
  latest_job_error: string | null;
  rollback_available: boolean;
  snapshot_aliases_total: number;
  current_aliases_total: number;
  diff: SnapshotDiffSummary;
  updated_at: string;
};

export type SnapshotHistoryItem = {
  job_id: number;
  binding_id: number;
  binding_name: string;
  profile_name: string;
  status: string;
  snapshot_version: string | null;
  previous_snapshot_version: string | null;
  checksum: string | null;
  alias_entries_total: number;
  documents_seen: number;
  documents_enriched: number;
  documents_failed: number;
  target_index: string | null;
  alias_name: string | null;
  rollback_available: boolean;
  error_message: string | null;
  created_at: string;
  finished_at: string | null;
};

export type SnapshotCounts = {
  bindings: number;
  active_snapshots: number;
  stale_snapshots: number;
  pending_snapshots: number;
  failed_updates: number;
  never_enriched: number;
  rollback_available: number;
};

export type SnapshotSummary = {
  counts: SnapshotCounts;
  bindings: SnapshotBindingState[];
  history: SnapshotHistoryItem[];
};


export type RuntimeTextMatch = {
  alias_value: string;
  canonical_value: string;
  slot: string;
  matched_text: string;
  start: number;
  end: number;
  confidence: number;
};

export type RuntimeTextEvidence = RuntimeTextMatch & {
  reason: string;
  source: string;
};

export type RuntimeQueryPlanRequest = {
  profile_name?: string | null;
  binding_id?: number | null;
  query: string;
  text_fields?: string[] | null;
  target_field?: string | null;
  size?: number;
  canonical_boost?: number;
  include_evidence?: boolean;
  max_matches?: number;
};

export type RuntimeQueryPlanResponse = {
  profile_name: string;
  normalized_profile_name: string;
  query: string;
  canonical_query: string;
  changed: boolean;
  text_fields: string[];
  target_field: string;
  binding_id: number | null;
  snapshot_version: string | null;
  snapshot_source: string;
  canonical_values: string[];
  slots: Record<string, string[]>;
  matched_aliases: string[];
  replacements: RuntimeTextMatch[];
  evidence: RuntimeTextEvidence[];
  elasticsearch: Record<string, unknown>;
  warnings: string[];
};

export type RuntimeSearchRequest = RuntimeQueryPlanRequest & {
  index_name?: string | null;
  include_source?: boolean;
  source_fields?: string[] | null;
};

export type RuntimeSearchHit = {
  id: string;
  index: string;
  score: number | null;
  source: Record<string, unknown>;
  skeinrank: Record<string, unknown> | null;
};

export type RuntimeSearchResponse = Omit<RuntimeQueryPlanResponse, "text_fields" | "target_field"> & {
  index_name: string;
  text_fields?: string[];
  target_field?: string;
  total: Record<string, unknown> | number | null;
  hits: RuntimeSearchHit[];
};

export type Profile = {
  id: number;
  name: string;
  normalized_name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
};

export type TermAlias = {
  id: number;
  alias_value: string;
  normalized_alias: string;
  status: string;
  confidence: number;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type CanonicalTerm = {
  id: number;
  canonical_value: string;
  normalized_value: string;
  slot: string;
  status: string;
  description: string | null;
  aliases: TermAlias[];
  created_at: string;
  updated_at: string;
};



export type StopListTarget = "alias" | "canonical" | "both";

export type StopListEntry = {
  id: number;
  profile_id: number;
  value: string;
  normalized_value: string;
  target: StopListTarget;
  reason: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type StopListCreateRequest = {
  value: string;
  target: StopListTarget;
  reason?: string | null;
  is_active?: boolean;
};

export type StopListUpdateRequest = {
  value?: string | null;
  target?: StopListTarget | null;
  reason?: string | null;
  is_active?: boolean | null;
};



export type GlobalStopListEntry = {
  id: number;
  value: string;
  normalized_value: string;
  target: StopListTarget;
  reason: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type GlobalStopListCreateRequest = {
  value: string;
  target: StopListTarget;
  reason?: string | null;
  is_active?: boolean;
};

export type GlobalStopListUpdateRequest = {
  value?: string | null;
  target?: StopListTarget | null;
  reason?: string | null;
  is_active?: boolean | null;
};


export type ElasticsearchConnectionStatus = {
  configured: boolean;
  ok: boolean;
  url: string | null;
  cluster_name: string | null;
  cluster_version: string | null;
  error: string | null;
};

export type ElasticsearchIndex = {
  name: string;
  health: string | null;
  status: string | null;
  docs_count: number | null;
};

export type ElasticsearchMappingField = {
  name: string;
  type: string;
  is_text_candidate: boolean;
  is_discriminator_candidate: boolean;
};

export type ElasticsearchIndexMapping = {
  index_name: string;
  fields: ElasticsearchMappingField[];
};

export type ElasticsearchBindingMode = "dry_run" | "write";

export type ElasticsearchBindingWriteStrategy = "in_place" | "reindex_alias_swap";

export type ElasticsearchEnrichmentJobStatus = "queued" | "running" | "cancel_requested" | "cancelled" | "succeeded" | "failed";

export type ElasticsearchBindingSnapshotStatus = "never_enriched" | "ready" | "stale" | "updating" | "failed";

export type ElasticsearchBinding = {
  id: number;
  profile_id: number;
  profile_name: string;
  name: string;
  normalized_name: string;
  description: string | null;
  provider: string;
  index_name: string;
  text_fields: string[];
  target_field: string;
  filter_field: string | null;
  filter_value: string | null;
  timestamp_field: string | null;
  time_window_days: number | null;
  mode: ElasticsearchBindingMode;
  write_strategy: ElasticsearchBindingWriteStrategy;
  is_enabled: boolean;
  last_successful_snapshot_version?: string | null;
  last_successful_snapshot_at?: string | null;
  last_successful_job_id?: number | null;
  pending_snapshot_version?: string | null;
  snapshot_status?: ElasticsearchBindingSnapshotStatus | string | null;
  created_at: string;
  updated_at: string;
};

export type ElasticsearchBindingCreateRequest = {
  name: string;
  profile_name: string;
  description?: string | null;
  index_name: string;
  text_fields: string[];
  target_field: string;
  filter_field?: string | null;
  filter_value?: string | null;
  timestamp_field?: string | null;
  time_window_days?: number | null;
  mode?: ElasticsearchBindingMode;
  write_strategy?: ElasticsearchBindingWriteStrategy;
  is_enabled?: boolean;
};

export type ElasticsearchBindingUpdateRequest = {
  name?: string | null;
  profile_name?: string | null;
  description?: string | null;
  index_name?: string | null;
  text_fields?: string[] | null;
  target_field?: string | null;
  filter_field?: string | null;
  filter_value?: string | null;
  timestamp_field?: string | null;
  time_window_days?: number | null;
  mode?: ElasticsearchBindingMode | null;
  write_strategy?: ElasticsearchBindingWriteStrategy | null;
  is_enabled?: boolean | null;
};



export type ElasticsearchBindingDryRunRequest = {
  limit?: number;
};

export type ElasticsearchDryRunMatchedAlias = {
  alias_value: string;
  canonical_value: string;
  slot: string;
  matched_text: string;
  confidence: number;
};

export type ElasticsearchDryRunDocument = {
  document_id: string;
  index_name: string;
  text_preview: string;
  source_preview: Record<string, string[]>;
  matched_aliases: ElasticsearchDryRunMatchedAlias[];
  would_write: Record<string, unknown>;
};

export type ElasticsearchBindingDryRunResponse = {
  binding: ElasticsearchBinding;
  limit: number;
  documents: ElasticsearchDryRunDocument[];
  warnings: string[];
};




export type ElasticsearchEvidenceRequest = {
  query: string;
  canonical_value?: string | null;
  max_documents?: number;
  context_chars?: number;
};

export type ElasticsearchEvidenceDocument = {
  document_id: string;
  index_name: string;
  field: string;
  fragment: string;
  highlighted_fragment: string;
  matched_text: string;
  match_start: number;
  match_end: number;
};

export type ElasticsearchEvidenceResponse = {
  binding: ElasticsearchBinding;
  query: string;
  normalized_query: string;
  canonical_value: string | null;
  max_documents: number;
  documents: ElasticsearchEvidenceDocument[];
  warnings: string[];
};

export type SuggestionEvidenceSnapshot = {
  binding_id: number;
  binding_name: string;
  index_name: string;
  profile_name: string;
  query: string;
  normalized_query: string;
  canonical_value: string | null;
  max_documents: number;
  documents: ElasticsearchEvidenceDocument[];
  warnings: string[];
};

export type SuggestionEvidenceRefreshRequest = {
  binding_id: number;
  query?: string | null;
  max_documents?: number;
  context_chars?: number;
};

export type ElasticsearchEnrichmentJobCreateRequest = {
  target_index_name?: string | null;
  alias_name?: string | null;
  max_documents?: number;
  chunk_size?: number | null;
};

export type ElasticsearchEnrichmentJobCancelRequest = {
  reason?: string | null;
};

export type ElasticsearchEnrichmentJobRollbackRequest = {
  reason?: string | null;
};

export type ElasticsearchEnrichmentJob = {
  id: number;
  binding_id: number;
  profile_id: number;
  binding_name: string;
  profile_name: string;
  status: ElasticsearchEnrichmentJobStatus;
  write_strategy: ElasticsearchBindingWriteStrategy;
  source_index: string;
  target_index: string | null;
  alias_name: string | null;
  snapshot_version?: string | null;
  previous_snapshot_version?: string | null;
  requested_by: string | null;
  documents_seen: number;
  documents_enriched: number;
  documents_failed: number;
  result_json: Record<string, unknown>;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
};

export type SuggestionStatus = "pending" | "approved" | "rejected";

export type SuggestionSource = "manual" | "discovery" | "import";

export type SuggestionType = "alias" | "canonical_term";

export type GovernanceSuggestion = {
  id: number;
  profile_id: number;
  term_id: number | null;
  alias_id: number | null;
  suggestion_type: SuggestionType;
  canonical_value: string;
  normalized_canonical: string;
  alias_value: string | null;
  normalized_alias: string | null;
  slot: string;
  description: string | null;
  confidence: number;
  source: SuggestionSource;
  context: string | null;
  status: SuggestionStatus;
  created_by: string | null;
  reviewed_by: string | null;
  review_comment: string | null;
  reviewed_at: string | null;
  evidence_snapshot: SuggestionEvidenceSnapshot | null;
  evidence_checked_by: string | null;
  evidence_checked_at: string | null;
  created_at: string;
  updated_at: string;
};

export type SuggestionCreateRequest = {
  suggestion_type?: SuggestionType;
  canonical_value: string;
  alias_value?: string | null;
  slot: string;
  description?: string | null;
  confidence?: number;
  source?: SuggestionSource;
  context?: string | null;
};

export type SuggestionReviewRequest = {
  review_comment?: string | null;
};

export type UserRole = "admin" | "moderator" | "contributor";

export type UserStatus = "active" | "suspended" | "deactivated";

export type AuthUser = {
  id: number;
  username: string;
  normalized_username: string;
  display_name: string | null;
  role: UserRole;
  status: UserStatus;
  is_active: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  last_login_at?: string | null;
};

export type LoginRequest = {
  username: string;
  password: string;
};

export type AuthTokenResponse = {
  access_token: string;
  token_type: "bearer";
  expires_at: string;
  user: AuthUser;
};

export type UserCreateRequest = {
  username: string;
  password: string;
  display_name?: string | null;
  role: UserRole;
  status?: UserStatus;
  is_active?: boolean | null;
};

export type UserUpdateRequest = {
  username?: string | null;
  password?: string | null;
  display_name?: string | null;
  role?: UserRole | null;
  status?: UserStatus | null;
  is_active?: boolean | null;
};

export type UserTokenRevokeResponse = {
  username: string;
  revoked_api_tokens: number;
};



export type ApiTokenScope = "migration:validate" | "migration:apply" | "migration:export";

export type ApiTokenOwnerType = "personal" | "service_account" | "unknown";

export type ApiToken = {
  id: number;
  name: string;
  token_prefix: string;
  scopes: string[];
  owner_type: ApiTokenOwnerType;
  owner_name: string;
  expires_at: string | null;
  revoked_at: string | null;
  last_used_at: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
};

export type ApiTokenCreateRequest = {
  name: string;
  scopes: string[];
  expires_in_days?: number | null;
};

export type ApiTokenCreateResponse = ApiToken & {
  access_token: string;
  token_type: "bearer";
};

export type ServiceAccount = {
  id: number;
  name: string;
  normalized_name: string;
  display_name: string | null;
  description: string | null;
  role: UserRole;
  is_active: boolean;
  created_by: string | null;
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ServiceAccountCreateRequest = {
  name: string;
  display_name?: string | null;
  description?: string | null;
  role: UserRole;
  is_active?: boolean;
};

export type ServiceAccountUpdateRequest = {
  name?: string | null;
  display_name?: string | null;
  description?: string | null;
  role?: UserRole | null;
  is_active?: boolean | null;
};

export type ProfileCreateRequest = {
  name: string;
  description?: string | null;
};

export type ProfileUpdateRequest = {
  name?: string | null;
  description?: string | null;
};

export type TermCreateRequest = {
  canonical_value: string;
  slot: string;
  description?: string | null;
  status?: string;
};

export type TermUpdateRequest = {
  canonical_value?: string | null;
  slot?: string | null;
  description?: string | null;
  status?: string | null;
};

export type AliasCreateRequest = {
  alias_value: string;
  confidence?: number;
  status?: string;
  notes?: string | null;
};

export type AliasUpdateRequest = {
  alias_value?: string | null;
  confidence?: number | null;
  status?: string | null;
  notes?: string | null;
};

export type SnapshotExportRequest = {
  snapshot_version?: string;
  description?: string;
};

export type RuntimeSnapshot = {
  profile_id: string;
  snapshot: {
    version: string;
    source: string;
    created_at?: string;
    description?: string | null;
  };
  alias_matcher: {
    backend: string;
  };
  aliases: Array<{
    slot: string;
    canonical: string;
    aliases: Array<string | { value: string; confidence?: number }>;
  }>;
  rules: unknown[];
};
