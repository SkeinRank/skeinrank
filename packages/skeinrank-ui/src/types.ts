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

export type AuthUser = {
  id: number;
  username: string;
  normalized_username: string;
  display_name: string | null;
  role: UserRole;
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
  is_active?: boolean;
};

export type UserUpdateRequest = {
  username?: string | null;
  password?: string | null;
  display_name?: string | null;
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
