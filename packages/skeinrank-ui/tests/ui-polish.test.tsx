import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/App";
import type { AlertingReport, AuthUser, DashboardSummary } from "../src/types";

const adminUser: AuthUser = {
  id: 1,
  username: "admin",
  normalized_username: "admin",
  display_name: "Admin User",
  role: "admin",
  status: "active",
  is_active: true,
  created_at: "2026-05-28T00:00:00Z",
  updated_at: "2026-05-28T00:00:00Z",
  last_login_at: null,
};

const dashboardSummary: DashboardSummary = {
  readiness: {},
  counts: {
    profiles: 0,
    canonical_terms: 0,
    aliases: 0,
    bindings: 0,
    ready_bindings: 0,
    stale_bindings: 0,
    updating_bindings: 0,
    failed_bindings: 0,
    never_enriched_bindings: 0,
    running_jobs: 0,
    failed_jobs: 0,
  },
  setup: {
    has_profile: false,
    has_terms: false,
    has_binding: false,
    has_successful_enrichment: false,
    has_runtime_snapshot: false,
  },
  bindings: [],
  recent_jobs: [],
};

const degradedReport: AlertingReport = {
  schema_version: "skeinrank.alerting_report.v1",
  status: "degraded",
  severity: "critical",
  generated_at: "2026-05-28T00:00:00Z",
  service: { name: "skeinrank-governance-api", version: "0.1.0" },
  environment: "test",
  request_id: "req-001",
  summary: {
    events_total: 1,
    critical_events: 1,
    warning_events: 0,
    info_events: 0,
    degraded_sources: ["profile_isolation"],
  },
  events: [
    {
      id: "profile-isolation-binding_profile_alignment-failed",
      severity: "critical",
      source: "profile_isolation",
      signal: "binding_profile_alignment",
      message: "Some bindings reference missing profiles.",
      details: { issues_count: 1 },
      recommended_action: "Repair orphaned or cross-profile rows before production pilot runs.",
    },
  ],
  hooks: {},
  recommendations: ["Resolve critical alerts before continuing the pilot."],
  safety: {
    read_only: true,
    database_mutation_enabled: false,
    runtime_mutation_enabled: false,
    openrouter_calls: false,
    elasticsearch_calls: false,
    webhook_delivery_enabled: false,
    secrets_included: false,
  },
};

function stubApi({ alertsReport = degradedReport }: { alertsReport?: AlertingReport | null } = {}) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = input.toString();
    const method = init?.method ?? "GET";

    if (url.endsWith("/v1/auth/me") && method === "GET") {
      return Response.json(adminUser);
    }
    if (url.endsWith("/v1/dashboard/summary") && method === "GET") {
      return Response.json(dashboardSummary);
    }
    if (url.endsWith("/v1/ops/alerts/report") && method === "GET") {
      if (!alertsReport) {
        return Response.json({ detail: "not found" }, { status: 404 });
      }
      return Response.json(alertsReport);
    }
    if (url.endsWith("/v1/governance/profiles") && method === "GET") {
      return Response.json([]);
    }
    if (url.endsWith("/v1/auth/logout") && method === "POST") {
      return new Response(null, { status: 204 });
    }

    return Response.json({ detail: `Unhandled request: ${method} ${url}` }, { status: 404 });
  });

  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("UI polish and degraded-state surfaces", () => {
  it("shows a non-mutating degraded-state banner from the alerts report", async () => {
    stubApi();

    render(<App />);

    expect(await screen.findByLabelText("Degraded state alert")).toBeInTheDocument();
    expect(screen.getByText("SkeinRank degraded state")).toBeInTheDocument();
    expect(screen.getByText("Some bindings reference missing profiles.")).toBeInTheDocument();
    expect(screen.getByText(/Read-only banner/)).toBeInTheDocument();
  });

  it("keeps AI Inbox empty states actionable when no profiles exist", async () => {
    stubApi();

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "AI Inbox" }));

    expect(await screen.findByText("No profiles are ready for AI Inbox")).toBeInTheDocument();
    expect(screen.getByText(/Seed a profile through the headless API/)).toBeInTheDocument();
  });
});
