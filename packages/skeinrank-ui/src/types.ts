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


export type TermCreateRequest = {
  canonical_value: string;
  slot: string;
  description?: string | null;
  status?: string;
};

export type AliasCreateRequest = {
  alias_value: string;
  confidence?: number;
  status?: string;
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
