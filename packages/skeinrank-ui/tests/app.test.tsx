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

function cloneProfiles() {
  return JSON.parse(JSON.stringify(profiles)) as Profile[];
}

function cloneTerms() {
  return JSON.parse(JSON.stringify(terms)) as CanonicalTerm[];
}

function stubGovernanceApi(options: StubOptions = {}) {
  let currentProfiles = cloneProfiles();
  let currentTerms = cloneTerms();
  let nextProfileId = 10;
  let nextTermId = 10;
  let nextAliasId = 20;

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = input.toString();
    const method = init?.method ?? "GET";

    if (url.endsWith("/v1/governance/profiles") && method === "GET") {
      return Response.json(currentProfiles);
    }

    if (url.endsWith("/v1/governance/profiles") && method === "POST") {
      const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
        description?: string | null;
        name: string;
      };
      const newProfile: Profile = {
        id: nextProfileId++,
        name: payload.name,
        normalized_name: payload.name.toLowerCase(),
        description: payload.description ?? null,
        created_at: "2026-05-05T00:00:00Z",
        updated_at: "2026-05-05T00:00:00Z",
      };
      currentProfiles = [...currentProfiles, newProfile];
      return Response.json(newProfile, { status: 201 });
    }

    if (url.endsWith("/v1/governance/profiles/default_it") && method === "PATCH") {
      const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
        description?: string | null;
        name?: string | null;
      };
      const updatedProfile: Profile = {
        ...currentProfiles[0],
        name: payload.name ?? currentProfiles[0].name,
        normalized_name: (payload.name ?? currentProfiles[0].name).toLowerCase(),
        description: payload.description ?? null,
        updated_at: "2026-05-05T00:00:00Z",
      };
      currentProfiles = [updatedProfile, ...currentProfiles.slice(1)];
      return Response.json(updatedProfile);
    }

    if (url.endsWith("/v1/governance/profiles/default_it") && method === "DELETE") {
      currentProfiles = currentProfiles.filter((profile) => profile.name !== "default_it");
      currentTerms = [];
      return new Response(null, { status: 204 });
    }

    if ((url.endsWith("/v1/governance/profiles/default_it/terms") || url.endsWith("/v1/governance/profiles/platform_terms/terms")) && method === "GET") {
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

    if (url.endsWith("/v1/governance/profiles/default_it/terms/kubernetes") && method === "PATCH") {
      const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
        canonical_value?: string | null;
        description?: string | null;
        slot?: string | null;
        status?: string | null;
      };
      const updatedTerm: CanonicalTerm = {
        ...currentTerms[0],
        canonical_value: payload.canonical_value ?? currentTerms[0].canonical_value,
        normalized_value: (payload.canonical_value ?? currentTerms[0].canonical_value).toLowerCase(),
        slot: payload.slot ?? currentTerms[0].slot,
        status: payload.status ?? currentTerms[0].status,
        description: payload.description ?? null,
        updated_at: "2026-05-05T00:00:00Z",
      };
      currentTerms = [updatedTerm, ...currentTerms.slice(1)];
      return Response.json(updatedTerm);
    }

    if (url.endsWith("/v1/governance/profiles/default_it/terms/kubernetes") && method === "DELETE") {
      currentTerms = currentTerms.filter((term) => term.canonical_value !== "kubernetes");
      return new Response(null, { status: 204 });
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

    if (url.endsWith("/v1/governance/profiles/default_it/terms/kubernetes/aliases/1") && method === "PATCH") {
      const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
        alias_value?: string | null;
        confidence?: number | null;
        notes?: string | null;
        status?: string | null;
      };
      const updatedAlias: TermAlias = {
        ...currentTerms[0].aliases[0],
        alias_value: payload.alias_value ?? currentTerms[0].aliases[0].alias_value,
        normalized_alias: (payload.alias_value ?? currentTerms[0].aliases[0].alias_value).toLowerCase(),
        status: payload.status ?? currentTerms[0].aliases[0].status,
        confidence: payload.confidence ?? currentTerms[0].aliases[0].confidence,
        notes: payload.notes ?? null,
        updated_at: "2026-05-05T00:00:00Z",
      };
      currentTerms = currentTerms.map((term) => ({
        ...term,
        aliases: term.aliases.map((alias) => (alias.id === 1 ? updatedAlias : alias)),
      }));
      return Response.json(updatedAlias);
    }

    if (url.endsWith("/v1/governance/profiles/default_it/terms/kubernetes/aliases/1") && method === "DELETE") {
      currentTerms = currentTerms.map((term) => ({ ...term, aliases: term.aliases.filter((alias) => alias.id !== 1) }));
      return new Response(null, { status: 204 });
    }

    if (url.endsWith("/v1/governance/profiles/default_it/snapshot/export") && method === "POST") {
      return Response.json({
        profile_id: "default_it",
        snapshot: {
          version: "default_it@draft",
          source: "governance-api",
          created_at: "2026-05-05T00:00:00Z",
          description: "Runtime snapshot exported from the governance console.",
        },
        alias_matcher: {
          backend: "aho_corasick",
        },
        aliases: [
          {
            slot: "TOOL",
            canonical: "kubernetes",
            aliases: ["k8s"],
          },
        ],
        rules: [],
      });
    }

    return Response.json({ detail: "not found" }, { status: 404 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("App", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    window.localStorage.clear();
    document.documentElement.classList.remove("dark");
    document.documentElement.style.colorScheme = "";
  });

  it("renders the governance console with profiles and terms", async () => {
    stubGovernanceApi();

    render(<App />);

    expect(screen.getByText("Terminology control plane")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getAllByText("default_it").length).toBeGreaterThan(0);
    });

    await waitFor(() => {
      expect(screen.getAllByText("kubernetes").length).toBeGreaterThan(0);
    });
    expect(screen.getAllByText("k8s").length).toBeGreaterThan(0);
    expect(screen.getByText("Postgres → Snapshot → Aho-Corasick")).toBeInTheDocument();
    expect(screen.getByText("MVP")).toBeInTheDocument();
    expect(screen.queryByText("UI skeleton")).not.toBeInTheDocument();
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

  it("creates and renames a profile through the governance API", async () => {
    const fetchMock = stubGovernanceApi();

    render(<App />);

    await screen.findByRole("button", { name: "Create profile" });

    fireEvent.change(screen.getByLabelText("New profile name"), { target: { value: "security_docs" } });
    fireEvent.change(screen.getByLabelText("New profile description"), { target: { value: "Security terminology" } });
    fireEvent.click(screen.getByRole("button", { name: "Create profile" }));

    await waitFor(() => {
      expect(screen.getAllByText("security_docs").length).toBeGreaterThan(0);
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8010/v1/governance/profiles",
      expect.objectContaining({
        body: JSON.stringify({
          name: "security_docs",
          description: "Security terminology",
        }),
        method: "POST",
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "default_it" }));
    fireEvent.change(screen.getByLabelText("Profile name"), { target: { value: "platform_terms" } });
    fireEvent.change(screen.getByLabelText("Profile description"), { target: { value: "Platform terminology" } });
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));

    await waitFor(() => {
      expect(screen.getAllByText("platform_terms").length).toBeGreaterThan(0);
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8010/v1/governance/profiles/default_it",
      expect.objectContaining({
        body: JSON.stringify({
          name: "platform_terms",
          description: "Platform terminology",
        }),
        method: "PATCH",
      }),
    );
  });

  it("deletes a profile after confirmation", async () => {
    const fetchMock = stubGovernanceApi();
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<App />);

    await screen.findByText("default_it");
    fireEvent.click(screen.getByRole("button", { name: "Delete profile" }));

    await waitFor(() => {
      expect(screen.queryByRole("button", { name: "default_it" })).not.toBeInTheDocument();
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8010/v1/governance/profiles/default_it",
      expect.objectContaining({ method: "DELETE" }),
    );
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

  it("updates and deletes canonical terms through the governance API", async () => {
    const fetchMock = stubGovernanceApi();
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<App />);

    await screen.findByText("default_it");
    await screen.findByLabelText("Edit canonical value");

    fireEvent.change(screen.getByLabelText("Edit canonical value"), { target: { value: "kubernetes" } });
    fireEvent.change(screen.getByLabelText("Edit slot"), { target: { value: "PLATFORM" } });
    fireEvent.change(screen.getByLabelText("Edit description"), { target: { value: "Container orchestration platform" } });
    fireEvent.change(screen.getByLabelText("Term status"), { target: { value: "deprecated" } });
    fireEvent.click(screen.getByRole("button", { name: "Save term" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/profiles/default_it/terms/kubernetes",
        expect.objectContaining({
          body: JSON.stringify({
            canonical_value: "kubernetes",
            slot: "PLATFORM",
            description: "Container orchestration platform",
            status: "deprecated",
          }),
          method: "PATCH",
        }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "Delete term" }));

    await waitFor(() => {
      expect(screen.getByText("No terms found for this profile.")).toBeInTheDocument();
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8010/v1/governance/profiles/default_it/terms/kubernetes",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("adds an alias to the selected canonical term with manual confidence hidden", async () => {
    const fetchMock = stubGovernanceApi();

    render(<App />);

    await screen.findByText("default_it");
    const aliasInput = await screen.findByLabelText("Alias");

    expect(screen.queryByLabelText("Confidence")).not.toBeInTheDocument();

    fireEvent.change(aliasInput, { target: { value: "kube" } });
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
          confidence: 1,
          notes: "Common Kubernetes shorthand",
          status: "active",
        }),
        method: "POST",
      }),
    );
  });

  it("updates and deletes aliases through the governance API", async () => {
    const fetchMock = stubGovernanceApi();
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<App />);

    await screen.findByText("default_it");
    await screen.findByText("k8s");

    const editAliasButton = await screen.findByRole("button", { name: "Edit alias" });
    expect(editAliasButton).not.toBeDisabled();
    fireEvent.click(editAliasButton);
    const editAliasInput = await screen.findByLabelText("Edit alias");
    fireEvent.change(editAliasInput, { target: { value: "kube" } });
    fireEvent.change(screen.getByLabelText("Edit alias notes"), { target: { value: "Short Kubernetes alias" } });
    fireEvent.change(screen.getByLabelText("Alias status"), { target: { value: "deprecated" } });
    fireEvent.click(screen.getByRole("button", { name: "Save alias" }));

    await waitFor(() => {
      expect(screen.getAllByText("kube").length).toBeGreaterThan(0);
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8010/v1/governance/profiles/default_it/terms/kubernetes/aliases/1",
      expect.objectContaining({
        body: JSON.stringify({
          alias_value: "kube",
          confidence: 1,
          notes: "Short Kubernetes alias",
          status: "deprecated",
        }),
        method: "PATCH",
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Delete alias" }));

    await waitFor(() => {
      expect(screen.queryByText("kube")).not.toBeInTheDocument();
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8010/v1/governance/profiles/default_it/terms/kubernetes/aliases/1",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("exports and downloads the runtime snapshot JSON", async () => {
    const fetchMock = stubGovernanceApi();
    const createObjectUrl = vi.fn(() => "blob:skeinrank-snapshot");
    const revokeObjectUrl = vi.fn();
    const clickAnchor = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectUrl });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeObjectUrl });

    render(<App />);

    await screen.findByText("default_it");

    const exportButton = screen.getByRole("button", { name: "Export draft snapshot" });
    await waitFor(() => expect(exportButton).not.toBeDisabled());
    fireEvent.click(exportButton);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/profiles/default_it/snapshot/export",
        expect.objectContaining({
          body: JSON.stringify({
            snapshot_version: "default_it@draft",
            description: "Runtime snapshot exported from the governance console.",
          }),
          method: "POST",
        }),
      );
    });

    const snapshotPreview = await screen.findByText((_content, element) => {
      return (
        element?.tagName.toLowerCase() === "pre" &&
        Boolean(element.textContent?.includes('"profile_id": "default_it"'))
      );
    });
    expect(snapshotPreview).toBeInTheDocument();

    const downloadButton = screen.getByRole("button", { name: "Download JSON" });
    await waitFor(() => expect(downloadButton).not.toBeDisabled());
    fireEvent.click(downloadButton);

    expect(createObjectUrl).toHaveBeenCalledTimes(1);
    expect(clickAnchor).toHaveBeenCalledTimes(1);
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:skeinrank-snapshot");
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
