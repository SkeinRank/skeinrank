import type { CanonicalTerm, Profile, RuntimeSnapshot, SnapshotExportRequest } from "../types";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8010";

export const governanceApiBaseUrl =
  import.meta.env.VITE_SKEINRANK_GOVERNANCE_API_URL ?? DEFAULT_API_BASE_URL;

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${governanceApiBaseUrl}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    const detail = await safeErrorDetail(response);
    throw new Error(detail ?? `Request failed: ${response.status}`);
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

export function listProfiles() {
  return requestJson<Profile[]>("/v1/governance/profiles");
}

export function listTerms(profileName: string) {
  return requestJson<CanonicalTerm[]>(`/v1/governance/profiles/${profileName}/terms`);
}

export function exportSnapshot(profileName: string, payload: SnapshotExportRequest = {}) {
  return requestJson<RuntimeSnapshot>(`/v1/governance/profiles/${profileName}/snapshot/export`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
