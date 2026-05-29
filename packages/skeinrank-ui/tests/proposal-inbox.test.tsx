import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/App";
import type { AuthUser, DashboardSummary, GovernanceSuggestion, Profile } from "../src/types";

const adminUser: AuthUser = {
  id: 1,
  username: "admin",
  normalized_username: "admin",
  display_name: "Admin User",
  role: "admin",
  status: "active",
  is_active: true,
};

const contributorUser: AuthUser = {
  ...adminUser,
  id: 2,
  username: "agent",
  normalized_username: "agent",
  display_name: "Agent User",
  role: "contributor",
};

const profiles: Profile[] = [
  {
    id: 1,
    name: "infra_incidents",
    normalized_name: "infra_incidents",
    description: "Infrastructure incident terminology.",
    created_at: "2026-05-28T00:00:00Z",
    updated_at: "2026-05-28T00:00:00Z",
  },
];

const dashboardSummary: DashboardSummary = {
  readiness: {},
  counts: {
    profiles: 1,
    canonical_terms: 1,
    aliases: 1,
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
    has_profile: true,
    has_terms: true,
    has_binding: false,
    has_successful_enrichment: false,
    has_runtime_snapshot: false,
  },
  bindings: [],
  recent_jobs: [],
};

function makeSuggestion(overrides: Partial<GovernanceSuggestion> = {}): GovernanceSuggestion {
  return {
    id: 42,
    profile_id: 1,
    term_id: 7,
    alias_id: null,
    binding_id: 3,
    suggestion_type: "alias",
    canonical_value: "postgresql",
    normalized_canonical: "postgresql",
    alias_value: "pg",
    normalized_alias: "pg",
    slot: "database",
    description: null,
    confidence: 0.9,
    source: "discovery",
    context: "Agent found pg timeout in failed search logs.",
    proposal_source_type: "agent",
    proposal_source_name: "openrouter-alias-scout",
    idempotency_key: "agent:pg:postgresql",
    source_payload: {
      candidate_alias: "pg",
      canonical_hint: {
        reason: "single_configured_alias_match",
      },
    },
    validation_summary: {
      status: "passed",
      validation_reasons: ["evidence_snapshot_available"],
      warnings: [],
      apply_policy: {
        schema_version: "skeinrank.apply_policy.v1",
        risk_level: "low",
        decision: "batch_approve_allowed",
        can_batch_apply: true,
        requires_reviewer: true,
        requires_admin: false,
        requires_warning_override: false,
        auto_apply_allowed: false,
        reasons: ["validation_passed_low_risk_thresholds"],
        signals: {
          evidence_documents: 1,
          duplicate_alias: false,
        },
      },
    },
    status: "pending",
    lifecycle_status: "pending_review",
    lifecycle_reason: "waiting_for_review",
    validation_status: "passed",
    risk_level: "low",
    apply_policy: {
      schema_version: "skeinrank.apply_policy.v1",
      risk_level: "low",
      decision: "batch_approve_allowed",
      can_batch_apply: true,
      requires_reviewer: true,
      requires_admin: false,
      requires_warning_override: false,
      auto_apply_allowed: false,
      reasons: ["validation_passed_low_risk_thresholds"],
      signals: { evidence_documents: 1, duplicate_alias: false },
    },
    can_approve: true,
    can_apply: false,
    created_by: "agent-bot",
    reviewed_by: null,
    review_comment: null,
    reviewed_at: null,
    evidence_snapshot: {
      binding_id: 3,
      binding_name: "infra docs",
      index_name: "incidents",
      profile_name: "infra_incidents",
      query: "pg timeout",
      normalized_query: "pg timeout",
      canonical_value: "postgresql",
      max_documents: 5,
      warnings: [],
      documents: [
        {
          document_id: "inc-1",
          index_name: "incidents",
          field: "body",
          fragment: "pg timeout after failover",
          highlighted_fragment: "<mark>pg</mark> timeout after failover",
          matched_text: "pg",
          match_start: 0,
          match_end: 2,
        },
      ],
    },
    evidence_checked_by: "agent-bot",
    evidence_checked_at: "2026-05-28T00:00:00Z",
    created_at: "2026-05-28T00:00:00Z",
    updated_at: "2026-05-28T00:00:00Z",
    ...overrides,
  };
}

function stubApi(currentUser: AuthUser = adminUser) {
  let suggestions = [makeSuggestion()];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = input.toString();
    const method = init?.method ?? "GET";

    if (url.endsWith("/v1/auth/me") && method === "GET") {
      return Response.json(currentUser);
    }
    if (url.endsWith("/v1/dashboard/summary") && method === "GET") {
      return Response.json(dashboardSummary);
    }
    if (url.endsWith("/v1/governance/profiles") && method === "GET") {
      return Response.json(profiles);
    }
    if (url.includes("/v1/governance/profiles/infra_incidents/suggestions") && method === "GET") {
      const status = new URL(url).searchParams.get("status");
      return Response.json(status ? suggestions.filter((suggestion) => suggestion.status === status) : suggestions);
    }
    if (url.endsWith("/v1/governance/profiles/infra_incidents/suggestions/42/approve") && method === "POST") {
      const payload = JSON.parse(init?.body?.toString() ?? "{}") as { review_comment?: string | null };
      suggestions = suggestions.map((suggestion) =>
        suggestion.id === 42
          ? {
              ...suggestion,
              status: "approved",
              reviewed_by: currentUser.username,
              review_comment: payload.review_comment ?? null,
              reviewed_at: "2026-05-28T01:00:00Z",
            }
          : suggestion,
      );
      return Response.json(suggestions[0]);
    }
    if (url.endsWith("/v1/governance/profiles/infra_incidents/suggestions/42/reject") && method === "POST") {
      const payload = JSON.parse(init?.body?.toString() ?? "{}") as { review_comment?: string | null };
      suggestions = suggestions.map((suggestion) =>
        suggestion.id === 42
          ? {
              ...suggestion,
              status: "rejected",
              reviewed_by: currentUser.username,
              review_comment: payload.review_comment ?? null,
              reviewed_at: "2026-05-28T01:00:00Z",
            }
          : suggestion,
      );
      return Response.json(suggestions[0]);
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
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("ProposalInboxPage", () => {
  it("renders a review-focused proposal inbox with risk and evidence summaries", async () => {
    stubApi(adminUser);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "AI Inbox" }));

    expect((await screen.findAllByText("AI Proposals Inbox")).length).toBeGreaterThan(0);
    expect(await screen.findByText("pg → postgresql")).toBeInTheDocument();
    expect(screen.getAllByText("Risk: low").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Validation: passed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Evidence ready").length).toBeGreaterThan(0);
    expect(screen.getAllByText("batch_approve_allowed").length).toBeGreaterThan(0);
    expect(screen.getByText("Risk and apply policy")).toBeInTheDocument();
    expect(screen.getByText("Validation findings")).toBeInTheDocument();
    expect(screen.getByText("validation passed low risk thresholds")).toBeInTheDocument();
    expect(screen.getByText("evidence snapshot available")).toBeInTheDocument();
    expect(screen.getByText("evidence_documents: 1")).toBeInTheDocument();
    expect(screen.getByText("Source payload JSON")).toBeInTheDocument();
    expect(screen.getByText((_, element) => element?.textContent === "pg timeout after failover")).toBeInTheDocument();
  });

  it("lets reviewers approve a pending proposal through the existing governance endpoint", async () => {
    const fetchMock = stubApi(adminUser);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "AI Inbox" }));
    expect((await screen.findAllByText("pg → postgresql")).length).toBeGreaterThan(0);

    fireEvent.change(screen.getByLabelText("Review comment"), {
      target: { value: "Evidence and risk look safe." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Approve proposal" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/profiles/infra_incidents/suggestions/42/approve",
        expect.objectContaining({
          body: JSON.stringify({ review_comment: "Evidence and risk look safe." }),
          method: "POST",
        }),
      );
    });

    expect(await screen.findByText("No pending proposals in this inbox view")).toBeInTheDocument();
  });

  it("keeps contributor users in read-only inbox mode", async () => {
    stubApi(contributorUser);

    render(<App />);

    fireEvent.click(await screen.findByRole("button", { name: "AI Inbox" }));
    expect((await screen.findAllByText("pg → postgresql")).length).toBeGreaterThan(0);

    expect(screen.getByText("Read-only mode")).toBeInTheDocument();
    expect(screen.getByText("Your role can inspect proposals but cannot approve or reject them.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve proposal" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reject proposal" })).toBeDisabled();
  });
});
