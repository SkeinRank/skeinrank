import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SearchPlaygroundPage } from "../src/pages/SearchPlaygroundPage";
import type { ElasticsearchBinding, RuntimeQueryPlanResponse } from "../src/types";

const bindings: ElasticsearchBinding[] = [
  {
    id: 1,
    profile_id: 1,
    profile_name: "default_it",
    name: "prod runtime",
    normalized_name: "prod_runtime",
    description: "Active production binding",
    provider: "elasticsearch",
    index_name: "docs-prod",
    text_fields: ["title", "body"],
    target_field: "skeinrank",
    filter_field: "team",
    filter_value: "infra",
    timestamp_field: null,
    time_window_days: null,
    mode: "write",
    write_strategy: "reindex_alias_swap",
    is_enabled: true,
    last_successful_snapshot_version: "default_it@prod123",
    last_successful_snapshot_at: "2026-05-28T00:00:00Z",
    last_successful_job_id: 10,
    pending_snapshot_version: null,
    snapshot_status: "ready",
    created_at: "2026-05-28T00:00:00Z",
    updated_at: "2026-05-28T00:00:00Z",
  },
  {
    id: 2,
    profile_id: 1,
    profile_name: "default_it",
    name: "staging runtime",
    normalized_name: "staging_runtime",
    description: "Candidate staging binding",
    provider: "elasticsearch",
    index_name: "docs-staging",
    text_fields: ["title", "body"],
    target_field: "skeinrank",
    filter_field: "team",
    filter_value: "infra",
    timestamp_field: null,
    time_window_days: null,
    mode: "dry_run",
    write_strategy: "reindex_alias_swap",
    is_enabled: true,
    last_successful_snapshot_version: "default_it@draft456",
    last_successful_snapshot_at: "2026-05-28T01:00:00Z",
    last_successful_job_id: 11,
    pending_snapshot_version: "default_it@draft789",
    snapshot_status: "stale",
    created_at: "2026-05-28T00:00:00Z",
    updated_at: "2026-05-28T00:00:00Z",
  },
];

function queryPlanFor(bindingId: number): RuntimeQueryPlanResponse {
  const isDraft = bindingId === 2;
  return {
    profile_name: "default_it",
    normalized_profile_name: "default_it",
    query: "k8s pg timeout",
    canonical_query: isDraft ? "kubernetes postgresql timeout" : "k8s postgresql timeout",
    changed: true,
    text_fields: ["title", "body"],
    target_field: "skeinrank",
    binding_id: bindingId,
    snapshot_version: isDraft ? "default_it@draft456" : "default_it@prod123",
    snapshot_source: "binding_runtime_snapshot",
    canonical_values: isDraft ? ["kubernetes", "postgresql"] : ["postgresql"],
    slots: isDraft ? { TOOL: ["kubernetes"], DATABASE: ["postgresql"] } : { DATABASE: ["postgresql"] },
    matched_aliases: isDraft ? ["k8s", "pg"] : ["pg"],
    replacements: [
      ...(isDraft
        ? [
            {
              alias_value: "k8s",
              canonical_value: "kubernetes",
              slot: "TOOL",
              matched_text: "k8s",
              start: 0,
              end: 3,
              confidence: 0.97,
            },
          ]
        : []),
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
    elasticsearch: { query: { bool: { should: [] } }, size: 10 },
    warnings: [],
  };
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <SearchPlaygroundPage />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("SearchPlaygroundPage snapshot compare", () => {
  it("compares two binding-backed snapshots through the existing query-plan API", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = input.toString();
      const method = init?.method ?? "GET";

      if (url.endsWith("/v1/governance/elasticsearch/bindings") && method === "GET") {
        return Response.json(bindings);
      }

      if (url.endsWith("/v1/query/plan") && method === "POST") {
        const body = JSON.parse(init?.body?.toString() ?? "{}") as { binding_id: number };
        return Response.json(queryPlanFor(body.binding_id));
      }

      return Response.json({ detail: "not found" }, { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);

    renderPage();

    expect(await screen.findByText("Runtime search playground")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Compare snapshots" })[0]);

    await screen.findByText("Column B binding");
    fireEvent.click(screen.getAllByRole("button", { name: "Compare snapshots" })[1]);

    expect(await screen.findByText("Snapshot compare result")).toBeInTheDocument();
    expect(screen.getAllByText("prod runtime").length).toBeGreaterThan(0);
    expect(screen.getAllByText("staging runtime").length).toBeGreaterThan(0);
    expect(screen.getByText("k8s postgresql timeout")).toBeInTheDocument();
    expect(screen.getByText("kubernetes postgresql timeout")).toBeInTheDocument();
    expect(screen.getByText("Added canonical values")).toBeInTheDocument();
    expect(screen.getAllByText("kubernetes").length).toBeGreaterThan(0);

    await waitFor(() => {
      const planCalls = fetchMock.mock.calls.filter(([url]) => url.toString().endsWith("/v1/query/plan"));
      expect(planCalls).toHaveLength(2);
    });

    const bodies = fetchMock.mock.calls
      .filter(([url]) => url.toString().endsWith("/v1/query/plan"))
      .map(([, init]) => JSON.parse(init?.body?.toString() ?? "{}"));

    expect(bodies).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          binding_id: 1,
          query: "k8s pg timeout",
          size: 10,
          canonical_boost: 3,
          include_evidence: true,
        }),
        expect.objectContaining({
          binding_id: 2,
          query: "k8s pg timeout",
          size: 10,
          canonical_boost: 3,
          include_evidence: true,
        }),
      ]),
    );
  });
});
