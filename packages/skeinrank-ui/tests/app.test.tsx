import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/App";

const profiles = [
  {
    id: 1,
    name: "default_it",
    normalized_name: "default_it",
    description: "Default IT terms",
    created_at: "2026-05-04T00:00:00Z",
    updated_at: "2026-05-04T00:00:00Z",
  },
];

const terms = [
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

function stubGovernanceApi() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = input.toString();
    if (url.endsWith("/v1/governance/profiles")) {
      return Response.json(profiles);
    }
    if (url.endsWith("/v1/governance/profiles/default_it/terms")) {
      return Response.json(terms);
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

    expect(await screen.findByText("kubernetes")).toBeInTheDocument();
    expect(screen.getByText("k8s")).toBeInTheDocument();
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
});
