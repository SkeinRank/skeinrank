import type {
  AliasCreateRequest,
  AliasUpdateRequest,
  ApiToken,
  ApiTokenCreateRequest,
  ApiTokenCreateResponse,
  AuthTokenResponse,
  AuthUser,
  ElasticsearchBinding,
  ElasticsearchBindingCreateRequest,
  ElasticsearchBindingDryRunRequest,
  ElasticsearchBindingDryRunResponse,
  ElasticsearchEnrichmentJob,
  ElasticsearchEnrichmentJobCreateRequest,
  ElasticsearchEvidenceRequest,
  ElasticsearchEvidenceResponse,
  ElasticsearchBindingUpdateRequest,
  ElasticsearchConnectionStatus,
  ElasticsearchIndex,
  ElasticsearchIndexMapping,
  CanonicalTerm,
  GlobalStopListCreateRequest,
  GlobalStopListEntry,
  GlobalStopListUpdateRequest,
  LoginRequest,
  GovernanceSuggestion,
  Profile,
  ProfileCreateRequest,
  ProfileUpdateRequest,
  RuntimeSnapshot,
  SnapshotExportRequest,
  ServiceAccount,
  ServiceAccountCreateRequest,
  ServiceAccountUpdateRequest,
  StopListCreateRequest,
  StopListEntry,
  StopListUpdateRequest,
  SuggestionCreateRequest,
  SuggestionEvidenceRefreshRequest,
  SuggestionReviewRequest,
  SuggestionStatus,
  TermAlias,
  TermCreateRequest,
  TermUpdateRequest,
  UserCreateRequest,
  UserStatus,
  UserTokenRevokeResponse,
  UserUpdateRequest,
} from "../types";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8010";
const AUTH_TOKEN_STORAGE_KEY = "skeinrank-ui-auth-token";

export const governanceApiBaseUrl =
  import.meta.env.VITE_SKEINRANK_GOVERNANCE_API_URL ?? DEFAULT_API_BASE_URL;

let inMemoryAuthToken: string | null = readStoredAuthToken();

export class GovernanceApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "GovernanceApiError";
  }
}

export function getAuthToken() {
  return inMemoryAuthToken;
}

export function setAuthToken(token: string) {
  inMemoryAuthToken = token;
  if (typeof window !== "undefined") {
    window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token);
  }
}

export function clearAuthToken() {
  inMemoryAuthToken = null;
  if (typeof window !== "undefined") {
    window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (inMemoryAuthToken && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${inMemoryAuthToken}`);
  }

  const response = await fetch(`${governanceApiBaseUrl}${path}`, {
    ...init,
    headers,
  });

  if (!response.ok) {
    const detail = await safeErrorDetail(response);
    throw new GovernanceApiError(detail ?? `Request failed: ${response.status}`, response.status);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

async function safeErrorDetail(response: Response) {
  try {
    const body = (await response.json()) as { detail?: string };
    return body.detail;
  } catch {
    return null;
  }
}

function encodePathSegment(value: string) {
  return encodeURIComponent(value);
}

function readStoredAuthToken() {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY);
}

export function login(payload: LoginRequest) {
  return requestJson<AuthTokenResponse>("/v1/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function logout() {
  return requestJson<void>("/v1/auth/logout", {
    method: "POST",
  });
}

export function getCurrentUser() {
  return requestJson<AuthUser>("/v1/auth/me");
}

export function listUsers() {
  return requestJson<AuthUser[]>("/v1/auth/users");
}

export function createUser(payload: UserCreateRequest) {
  return requestJson<AuthUser>("/v1/auth/users", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateUser(username: string, payload: UserUpdateRequest) {
  return requestJson<AuthUser>(`/v1/auth/users/${encodePathSegment(username)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function updateUserStatus(username: string, userStatus: UserStatus) {
  return requestJson<AuthUser>(`/v1/auth/users/${encodePathSegment(username)}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status: userStatus }),
  });
}

export function revokeUserApiTokens(username: string) {
  return requestJson<UserTokenRevokeResponse>(`/v1/auth/users/${encodePathSegment(username)}/revoke-api-tokens`, {
    method: "POST",
  });
}

export function deleteUser(username: string) {
  return requestJson<void>(`/v1/auth/users/${encodePathSegment(username)}`, {
    method: "DELETE",
  });
}


export function listPersonalApiTokens() {
  return requestJson<ApiToken[]>("/v1/auth/api-tokens");
}

export function createPersonalApiToken(payload: ApiTokenCreateRequest) {
  return requestJson<ApiTokenCreateResponse>("/v1/auth/api-tokens", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function revokePersonalApiToken(tokenId: number) {
  return requestJson<void>(`/v1/auth/api-tokens/${tokenId}`, {
    method: "DELETE",
  });
}

export function listServiceAccounts() {
  return requestJson<ServiceAccount[]>("/v1/auth/service-accounts");
}

export function createServiceAccount(payload: ServiceAccountCreateRequest) {
  return requestJson<ServiceAccount>("/v1/auth/service-accounts", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateServiceAccount(accountName: string, payload: ServiceAccountUpdateRequest) {
  return requestJson<ServiceAccount>(`/v1/auth/service-accounts/${encodePathSegment(accountName)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteServiceAccount(accountName: string) {
  return requestJson<void>(`/v1/auth/service-accounts/${encodePathSegment(accountName)}`, {
    method: "DELETE",
  });
}

export function listServiceAccountTokens(accountName: string) {
  return requestJson<ApiToken[]>(`/v1/auth/service-accounts/${encodePathSegment(accountName)}/tokens`);
}

export function createServiceAccountToken(accountName: string, payload: ApiTokenCreateRequest) {
  return requestJson<ApiTokenCreateResponse>(`/v1/auth/service-accounts/${encodePathSegment(accountName)}/tokens`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function revokeServiceAccountToken(accountName: string, tokenId: number) {
  return requestJson<void>(`/v1/auth/service-accounts/${encodePathSegment(accountName)}/tokens/${tokenId}`, {
    method: "DELETE",
  });
}

export function listProfiles() {
  return requestJson<Profile[]>("/v1/governance/profiles");
}

export function createProfile(payload: ProfileCreateRequest) {
  return requestJson<Profile>("/v1/governance/profiles", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateProfile(profileName: string, payload: ProfileUpdateRequest) {
  return requestJson<Profile>(`/v1/governance/profiles/${encodePathSegment(profileName)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteProfile(profileName: string) {
  return requestJson<void>(`/v1/governance/profiles/${encodePathSegment(profileName)}`, {
    method: "DELETE",
  });
}

export function listTerms(profileName: string) {
  return requestJson<CanonicalTerm[]>(`/v1/governance/profiles/${encodePathSegment(profileName)}/terms`);
}

export function createTerm(profileName: string, payload: TermCreateRequest) {
  return requestJson<CanonicalTerm>(`/v1/governance/profiles/${encodePathSegment(profileName)}/terms`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateTerm(profileName: string, canonicalValue: string, payload: TermUpdateRequest) {
  return requestJson<CanonicalTerm>(
    `/v1/governance/profiles/${encodePathSegment(profileName)}/terms/${encodePathSegment(canonicalValue)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export function deleteTerm(profileName: string, canonicalValue: string) {
  return requestJson<void>(`/v1/governance/profiles/${encodePathSegment(profileName)}/terms/${encodePathSegment(canonicalValue)}`, {
    method: "DELETE",
  });
}

export function createAlias(profileName: string, canonicalValue: string, payload: AliasCreateRequest) {
  return requestJson<TermAlias>(
    `/v1/governance/profiles/${encodePathSegment(profileName)}/terms/${encodePathSegment(canonicalValue)}/aliases`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function updateAlias(profileName: string, canonicalValue: string, aliasId: number, payload: AliasUpdateRequest) {
  return requestJson<TermAlias>(
    `/v1/governance/profiles/${encodePathSegment(profileName)}/terms/${encodePathSegment(canonicalValue)}/aliases/${aliasId}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export function deleteAlias(profileName: string, canonicalValue: string, aliasId: number) {
  return requestJson<void>(
    `/v1/governance/profiles/${encodePathSegment(profileName)}/terms/${encodePathSegment(canonicalValue)}/aliases/${aliasId}`,
    {
      method: "DELETE",
    },
  );
}


export function listStopList(profileName: string) {
  return requestJson<StopListEntry[]>(`/v1/governance/profiles/${encodePathSegment(profileName)}/stop-list`);
}

export function createStopListEntry(profileName: string, payload: StopListCreateRequest) {
  return requestJson<StopListEntry>(`/v1/governance/profiles/${encodePathSegment(profileName)}/stop-list`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateStopListEntry(profileName: string, entryId: number, payload: StopListUpdateRequest) {
  return requestJson<StopListEntry>(`/v1/governance/profiles/${encodePathSegment(profileName)}/stop-list/${entryId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteStopListEntry(profileName: string, entryId: number) {
  return requestJson<void>(`/v1/governance/profiles/${encodePathSegment(profileName)}/stop-list/${entryId}`, {
    method: "DELETE",
  });
}


export function listGlobalStopList() {
  return requestJson<GlobalStopListEntry[]>("/v1/governance/global-stop-list");
}

export function createGlobalStopListEntry(payload: GlobalStopListCreateRequest) {
  return requestJson<GlobalStopListEntry>("/v1/governance/global-stop-list", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateGlobalStopListEntry(entryId: number, payload: GlobalStopListUpdateRequest) {
  return requestJson<GlobalStopListEntry>(`/v1/governance/global-stop-list/${entryId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteGlobalStopListEntry(entryId: number) {
  return requestJson<void>(`/v1/governance/global-stop-list/${entryId}`, {
    method: "DELETE",
  });
}


export function getElasticsearchConnectionStatus() {
  return requestJson<ElasticsearchConnectionStatus>("/v1/governance/elasticsearch/connection/status");
}

export function listElasticsearchIndices() {
  return requestJson<ElasticsearchIndex[]>("/v1/governance/elasticsearch/indices");
}

export function getElasticsearchIndexMapping(indexName: string) {
  return requestJson<ElasticsearchIndexMapping>(
    `/v1/governance/elasticsearch/indices/${encodePathSegment(indexName)}/mapping`,
  );
}

export function listElasticsearchBindings(profileName?: string) {
  const query = profileName ? `?profile_name=${encodeURIComponent(profileName)}` : "";
  return requestJson<ElasticsearchBinding[]>(`/v1/governance/elasticsearch/bindings${query}`);
}

export function createElasticsearchBinding(payload: ElasticsearchBindingCreateRequest) {
  return requestJson<ElasticsearchBinding>("/v1/governance/elasticsearch/bindings", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateElasticsearchBinding(bindingId: number, payload: ElasticsearchBindingUpdateRequest) {
  return requestJson<ElasticsearchBinding>(`/v1/governance/elasticsearch/bindings/${bindingId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteElasticsearchBinding(bindingId: number) {
  return requestJson<void>(`/v1/governance/elasticsearch/bindings/${bindingId}`, {
    method: "DELETE",
  });
}

export function dryRunElasticsearchBinding(bindingId: number, payload: ElasticsearchBindingDryRunRequest = {}) {
  return requestJson<ElasticsearchBindingDryRunResponse>(`/v1/governance/elasticsearch/bindings/${bindingId}/dry-run`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function findElasticsearchEvidence(bindingId: number, payload: ElasticsearchEvidenceRequest) {
  return requestJson<ElasticsearchEvidenceResponse>(`/v1/governance/elasticsearch/bindings/${bindingId}/evidence`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function startElasticsearchEnrichmentJob(bindingId: number, payload: ElasticsearchEnrichmentJobCreateRequest = {}) {
  return requestJson<ElasticsearchEnrichmentJob>(`/v1/governance/elasticsearch/bindings/${bindingId}/jobs`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listElasticsearchEnrichmentJobs(bindingId?: number) {
  const query = bindingId !== undefined ? `?binding_id=${encodeURIComponent(String(bindingId))}` : "";
  return requestJson<ElasticsearchEnrichmentJob[]>(`/v1/governance/elasticsearch/jobs${query}`);
}

export function getElasticsearchEnrichmentJob(jobId: number) {
  return requestJson<ElasticsearchEnrichmentJob>(`/v1/governance/elasticsearch/jobs/${jobId}`);
}

export function listSuggestions(profileName: string, status?: SuggestionStatus | "all") {
  const query = status && status !== "all" ? `?status=${encodeURIComponent(status)}` : "";
  return requestJson<GovernanceSuggestion[]>(`/v1/governance/profiles/${encodePathSegment(profileName)}/suggestions${query}`);
}

export function createSuggestion(profileName: string, payload: SuggestionCreateRequest) {
  return requestJson<GovernanceSuggestion>(`/v1/governance/profiles/${encodePathSegment(profileName)}/suggestions`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function refreshSuggestionEvidence(profileName: string, suggestionId: number, payload: SuggestionEvidenceRefreshRequest) {
  return requestJson<GovernanceSuggestion>(
    `/v1/governance/profiles/${encodePathSegment(profileName)}/suggestions/${suggestionId}/evidence/refresh`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function approveSuggestion(profileName: string, suggestionId: number, payload: SuggestionReviewRequest = {}) {
  return requestJson<GovernanceSuggestion>(
    `/v1/governance/profiles/${encodePathSegment(profileName)}/suggestions/${suggestionId}/approve`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function rejectSuggestion(profileName: string, suggestionId: number, payload: SuggestionReviewRequest = {}) {
  return requestJson<GovernanceSuggestion>(
    `/v1/governance/profiles/${encodePathSegment(profileName)}/suggestions/${suggestionId}/reject`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function exportSnapshot(profileName: string, payload: SnapshotExportRequest = {}) {
  return requestJson<RuntimeSnapshot>(`/v1/governance/profiles/${encodePathSegment(profileName)}/snapshot/export`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
