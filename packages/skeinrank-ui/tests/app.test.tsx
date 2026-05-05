import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/App";
import type { CanonicalTerm, Profile, TermAlias } from "../src/types";

const profiles: Profile[] = [
  {
    id: 1,
    name: "default_it",
    normalized_name: "default_it",
    description: "Default IT terms",
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

type StubOptions = {
  duplicateTerm?: boolean;
};

function cloneTerms() {
  return JSON.parse(JSON.stringify(terms)) as CanonicalTerm[];
}

function stubGovernanceApi(options: StubOptions = {}) {
  let currentTerms = cloneTerms();
  let nextTermId = 10;
  let nextAliasId = 20;

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = input.toString();
    const method = init?.method ?? "GET";

    if (url.endsWith("/v1/governance/profiles") && method === "GET") {
      return Response.json(profiles);
    }

    if (url.endsWith("/v1/governance/profiles/default_it/terms") && method === "GET") {
      return Response.json(currentTerms);
    }

    if (url.endsWith("/v1/governance/profiles/default_it/terms") && method === "POST") {
      if (options.duplicateTerm) {
        return Response.json({ detail: "Term already exists in profile 'default_it': kubernetes" }, { status: 409 });
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

    if (url.endsWith("/v1/governance/profiles/default_it/terms/kubernetes/aliases") && method === "POST") {
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
        term.canonical_value === "kubernetes" ? { ...term, aliases: [...term.aliases, newAlias] } : term,
      );
      return Response.json(newAlias, { status: 201 });
    }

    return Response.json({ detail: "not found" }, { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("App", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    window.localStorage.clear();
    document.documentElement.classList.remove("dark");
    document.documentElement.style.colorScheme = "";
  });

  it("renders the governance console with profiles and terms", async () => {
    stubGovernanceApi();

    render(<App />);

    expect(screen.getByText("Terminology control plane")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("default_it")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getAllByText("kubernetes").length).toBeGreaterThan(0);
    });
    expect(screen.getAllByText("k8s").length).toBeGreaterThan(0);
    expect(screen.getByText("Postgres → Snapshot → Aho-Corasick")).toBeInTheDocument();
  });

  it("cycles the governance console theme", async () => {
    stubGovernanceApi();

    render(<App />);

    const themeButton = screen.getByRole("button", { name: /switch theme/i });
    expect(themeButton).toHaveTextContent("System");

    fireEvent.click(themeButton);
    expect(themeButton).toHaveTextContent("Light");
    expect(document.documentElement).not.toHaveClass("dark");

    fireEvent.click(themeButton);
    expect(themeButton).toHaveTextContent("Dark");
    expect(document.documentElement).toHaveClass("dark");
    expect(window.localStorage.getItem("skeinrank-ui-theme")).toBe("dark");
  });

  it("adds a canonical term through the governance API", async () => {
    const fetchMock = stubGovernanceApi();

    render(<App />);

    await screen.findByText("default_it");

    fireEvent.change(screen.getByLabelText("Canonical value"), { target: { value: "postgresql" } });
    fireEvent.change(screen.getByLabelText("Slot"), { target: { value: "DB" } });
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "PostgreSQL database" } });
    fireEvent.click(screen.getByRole("button", { name: "Add term" }));

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

  it("adds an alias to the selected canonical term", async () => {
    const fetchMock = stubGovernanceApi();

    render(<App />);

    await screen.findByText("default_it");
    const aliasValueInput = await screen.findByLabelText("Alias value");

    fireEvent.change(aliasValueInput, { target: { value: "kube" } });
    fireEvent.change(screen.getByLabelText("Confidence"), { target: { value: "0.91" } });
    fireEvent.change(screen.getByLabelText("Notes"), { target: { value: "Common Kubernetes shorthand" } });
    fireEvent.click(screen.getByRole("button", { name: "Add alias" }));

    await waitFor(() => {
      expect(screen.getAllByText("kube").length).toBeGreaterThan(0);
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8010/v1/governance/profiles/default_it/terms/kubernetes/aliases",
      expect.objectContaining({
        body: JSON.stringify({
          alias_value: "kube",
          confidence: 0.91,
          notes: "Common Kubernetes shorthand",
          status: "active",
        }),
        method: "POST",
      }),
    );
  });

  it("shows governance API conflicts when a canonical term cannot be added", async () => {
    stubGovernanceApi({ duplicateTerm: true });

    render(<App />);

    await screen.findByText("default_it");

    fireEvent.change(screen.getByLabelText("Canonical value"), { target: { value: "kubernetes" } });
    fireEvent.change(screen.getByLabelText("Slot"), { target: { value: "TOOL" } });
    fireEvent.click(screen.getByRole("button", { name: "Add term" }));

    expect(await screen.findByText("Term already exists in profile 'default_it': kubernetes")).toBeInTheDocument();
  });
});
