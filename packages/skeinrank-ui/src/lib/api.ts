import type {
  AliasCreateRequest,
  CanonicalTerm,
  Profile,
  RuntimeSnapshot,
  SnapshotExportRequest,
  TermAlias,
  TermCreateRequest,
} from "../types";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8010";

export const governanceApiBaseUrl =
  import.meta.env.VITE_SKEINRANK_GOVERNANCE_API_URL ?? DEFAULT_API_BASE_URL;

export class GovernanceApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "GovernanceApiError";
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${governanceApiBaseUrl}${path}`, {
    ...init,
    headers,
  });

  if (!response.ok) {
    const detail = await safeErrorDetail(response);
    throw new GovernanceApiError(detail ?? `Request failed: ${response.status}`, response.status);
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

export function listProfiles() {
  return requestJson<Profile[]>("/v1/governance/profiles");
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

export function createAlias(profileName: string, canonicalValue: string, payload: AliasCreateRequest) {
  return requestJson<TermAlias>(
    `/v1/governance/profiles/${encodePathSegment(profileName)}/terms/${encodePathSegment(canonicalValue)}/aliases`,
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
