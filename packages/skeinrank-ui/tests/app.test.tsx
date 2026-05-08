import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/App";
import type {
  AuthUser,
  CanonicalTerm,
  ElasticsearchBinding,
  ElasticsearchIndex,
  ElasticsearchIndexMapping,
  GovernanceSuggestion,
  Profile,
  StopListEntry,
  TermAlias,
} from "../src/types";

const adminUser: AuthUser = {
  id: 1,
  username: "admin",
  normalized_username: "admin",
  display_name: "Admin User",
  role: "admin",
  is_active: true,
  created_at: "2026-05-05T00:00:00Z",
  updated_at: "2026-05-05T00:00:00Z",
  last_login_at: "2026-05-05T00:00:00Z",
};

const moderatorUser: AuthUser = {
  ...adminUser,
  id: 2,
  username: "moderator",
  normalized_username: "moderator",
  display_name: "Moderator User",
  role: "moderator",
};

const contributorUser: AuthUser = {
  ...adminUser,
  id: 3,
  username: "contributor",
  normalized_username: "contributor",
  display_name: "Contributor User",
  role: "contributor",
};

const profiles: Profile[] = [
  {
    id: 1,
    name: "default_it",
    normalized_name: "default_it",
    description: "Default IT terms",
    created_at: "2026-05-04T00:00:00Z",
    updated_at: "2026-05-04T00:00:00Z",
  },
  {
    id: 2,
    name: "ml_platform",
    normalized_name: "ml_platform",
    description: "ML platform terminology",
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


const stopListEntries: StopListEntry[] = [
  {
    id: 1,
    profile_id: 1,
    value: "service",
    normalized_value: "service",
    target: "alias",
    reason: "Too generic for incident search",
    is_active: true,
    created_at: "2026-05-07T00:00:00Z",
    updated_at: "2026-05-07T00:00:00Z",
  },
];

const elasticsearchBindings: ElasticsearchBinding[] = [
  {
    id: 1,
    profile_id: 1,
    profile_name: "default_it",
    name: "infra docs",
    normalized_name: "infra_docs",
    description: "Apply default IT terms to docs.",
    provider: "elasticsearch",
    index_name: "docs",
    text_fields: ["title", "body"],
    target_field: "skeinrank",
    filter_field: "team",
    filter_value: "infra",
    mode: "dry_run",
    is_enabled: true,
    created_at: "2026-05-07T00:00:00Z",
    updated_at: "2026-05-07T00:00:00Z",
  },
  {
    id: 2,
    profile_id: 2,
    profile_name: "ml_platform",
    name: "ml docs",
    normalized_name: "ml_docs",
    description: "Apply ML terms to docs.",
    provider: "elasticsearch",
    index_name: "docs",
    text_fields: ["title", "body"],
    target_field: "skeinrank",
    filter_field: "team",
    filter_value: "ml-platform",
    mode: "dry_run",
    is_enabled: true,
    created_at: "2026-05-07T00:00:00Z",
    updated_at: "2026-05-07T00:00:00Z",
  },
];

const elasticsearchIndices: ElasticsearchIndex[] = [
  { name: "docs", health: "green", status: "open", docs_count: 42 },
  { name: "runbooks", health: "yellow", status: "open", docs_count: 7 },
];

const elasticsearchMapping: ElasticsearchIndexMapping = {
  index_name: "docs",
  fields: [
    { name: "title", type: "text", is_text_candidate: true, is_discriminator_candidate: false },
    { name: "body", type: "text", is_text_candidate: true, is_discriminator_candidate: false },
    { name: "summary", type: "text", is_text_candidate: true, is_discriminator_candidate: false },
    { name: "team", type: "keyword", is_text_candidate: false, is_discriminator_candidate: true },
    { name: "space", type: "keyword", is_text_candidate: false, is_discriminator_candidate: true },
  ],
};

const suggestions: GovernanceSuggestion[] = [
  {
    id: 1,
    profile_id: 1,
    term_id: 1,
    alias_id: null,
    suggestion_type: "alias",
    canonical_value: "kubernetes",
    normalized_canonical: "kubernetes",
    alias_value: "kube",
    normalized_alias: "kube",
    slot: "TOOL",
    description: null,
    confidence: 0.82,
    source: "manual",
    context: "People search for kube in incident docs.",
    status: "pending",
    created_by: "contributor",
    reviewed_by: null,
    review_comment: null,
    reviewed_at: null,
    created_at: "2026-05-06T00:00:00Z",
    updated_at: "2026-05-06T00:00:00Z",
  },
];

type StubOptions = {
  authRequired?: boolean;
  currentUser?: AuthUser;
  duplicateTerm?: boolean;
};

function cloneProfiles() {
  return JSON.parse(JSON.stringify(profiles)) as Profile[];
}

function cloneTerms() {
  return JSON.parse(JSON.stringify(terms)) as CanonicalTerm[];
}

function cloneSuggestions() {
  return JSON.parse(JSON.stringify(suggestions)) as GovernanceSuggestion[];
}

function cloneStopListEntries() {
  return JSON.parse(JSON.stringify(stopListEntries)) as StopListEntry[];
}

function cloneElasticsearchBindings() {
  return JSON.parse(JSON.stringify(elasticsearchBindings)) as ElasticsearchBinding[];
}

function cloneElasticsearchIndices() {
  return JSON.parse(JSON.stringify(elasticsearchIndices)) as ElasticsearchIndex[];
}

function cloneElasticsearchMapping(indexName = "docs") {
  const mapping = JSON.parse(JSON.stringify(elasticsearchMapping)) as ElasticsearchIndexMapping;
  mapping.index_name = indexName;
  return mapping;
}

function stubGovernanceApi(options: StubOptions = {}) {
  let currentProfiles = cloneProfiles();
  let currentUser = options.currentUser ?? adminUser;
  let currentUsers: AuthUser[] = [adminUser, moderatorUser, contributorUser];
  let currentTerms = cloneTerms();
  let currentSuggestions = cloneSuggestions();
  let currentStopListEntries = cloneStopListEntries();
  let currentElasticsearchBindings = cloneElasticsearchBindings();
  let nextProfileId = 10;
  let nextTermId = 10;
  let nextAliasId = 20;
  let nextSuggestionId = 10;
  let nextStopListEntryId = 10;
  let nextElasticsearchBindingId = 10;

  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = input.toString();
      const method = init?.method ?? "GET";
      const headers = new Headers(init?.headers);

      if (url.endsWith("/v1/auth/me") && method === "GET") {
        if (
          options.authRequired &&
          headers.get("Authorization") !== "Bearer test-token"
        ) {
          return Response.json(
            { detail: "Missing bearer token" },
            { status: 401 },
          );
        }
        return Response.json(currentUser);
      }

      if (url.endsWith("/v1/auth/login") && method === "POST") {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          username: string;
          password: string;
        };
        if (payload.username !== "admin" || payload.password !== "change-me") {
          return Response.json(
            { detail: "Invalid username or password" },
            { status: 401 },
          );
        }
        currentUser = adminUser;
        return Response.json({
          access_token: "test-token",
          token_type: "bearer",
          expires_at: "2026-05-06T00:00:00Z",
          user: adminUser,
        });
      }

      if (url.endsWith("/v1/auth/logout") && method === "POST") {
        return new Response(null, { status: 204 });
      }

      if (url.endsWith("/v1/auth/users") && method === "GET") {
        return Response.json(currentUsers);
      }

      if (url.endsWith("/v1/auth/users") && method === "POST") {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          display_name?: string | null;
          role: AuthUser["role"];
          username: string;
        };
        const user: AuthUser = {
          id: 20,
          username: payload.username,
          normalized_username: payload.username.toLowerCase(),
          display_name: payload.display_name ?? null,
          role: payload.role,
          is_active: true,
          created_at: "2026-05-05T00:00:00Z",
          updated_at: "2026-05-05T00:00:00Z",
          last_login_at: null,
        };
        currentUsers = [...currentUsers, user];
        return Response.json(user, { status: 201 });
      }

      if (url.endsWith("/v1/auth/users/contributor") && method === "PATCH") {
        const payload = JSON.parse(
          init?.body?.toString() ?? "{}",
        ) as Partial<AuthUser> & { password?: string | null };
        const updated: AuthUser = {
          ...contributorUser,
          username: payload.username ?? contributorUser.username,
          normalized_username: (
            payload.username ?? contributorUser.username
          ).toLowerCase(),
          display_name: payload.display_name ?? null,
          role: payload.role ?? contributorUser.role,
          is_active: payload.is_active ?? contributorUser.is_active,
          updated_at: "2026-05-06T00:00:00Z",
        };
        currentUsers = currentUsers.map((user) =>
          user.username === "contributor" ? updated : user,
        );
        return Response.json(updated);
      }

      if (url.endsWith("/v1/auth/users/contributor") && method === "DELETE") {
        currentUsers = currentUsers.filter(
          (user) => user.username !== "contributor",
        );
        return new Response(null, { status: 204 });
      }

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

      if (
        url.endsWith("/v1/governance/profiles/default_it") &&
        method === "PATCH"
      ) {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          description?: string | null;
          name?: string | null;
        };
        const updatedProfile: Profile = {
          ...currentProfiles[0],
          name: payload.name ?? currentProfiles[0].name,
          normalized_name: (
            payload.name ?? currentProfiles[0].name
          ).toLowerCase(),
          description: payload.description ?? null,
          updated_at: "2026-05-05T00:00:00Z",
        };
        currentProfiles = [updatedProfile, ...currentProfiles.slice(1)];
        return Response.json(updatedProfile);
      }

      if (
        url.endsWith("/v1/governance/profiles/default_it") &&
        method === "DELETE"
      ) {
        currentProfiles = currentProfiles.filter(
          (profile) => profile.name !== "default_it",
        );
        currentTerms = [];
        return new Response(null, { status: 204 });
      }

      if (
        url.endsWith("/v1/governance/profiles/default_it/stop-list") &&
        method === "GET"
      ) {
        return Response.json(currentStopListEntries);
      }

      if (
        url.endsWith("/v1/governance/profiles/default_it/stop-list") &&
        method === "POST"
      ) {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          is_active?: boolean;
          reason?: string | null;
          target: StopListEntry["target"];
          value: string;
        };
        const entry: StopListEntry = {
          id: nextStopListEntryId++,
          profile_id: 1,
          value: payload.value,
          normalized_value: payload.value.toLowerCase(),
          target: payload.target,
          reason: payload.reason ?? null,
          is_active: payload.is_active ?? true,
          created_at: "2026-05-07T00:00:00Z",
          updated_at: "2026-05-07T00:00:00Z",
        };
        currentStopListEntries = [entry, ...currentStopListEntries];
        return Response.json(entry, { status: 201 });
      }

      if (
        url.endsWith("/v1/governance/profiles/default_it/stop-list/1") &&
        method === "PATCH"
      ) {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          is_active?: boolean | null;
          reason?: string | null;
          target?: StopListEntry["target"] | null;
          value?: string | null;
        };
        const existingEntry = currentStopListEntries.find((entry) => entry.id === 1);
        if (!existingEntry) {
          return Response.json({ detail: "not found" }, { status: 404 });
        }
        const updatedEntry: StopListEntry = {
          ...existingEntry,
          value: payload.value ?? existingEntry.value,
          normalized_value: (payload.value ?? existingEntry.value).toLowerCase(),
          target: payload.target ?? existingEntry.target,
          reason: payload.reason ?? null,
          is_active: payload.is_active ?? existingEntry.is_active,
          updated_at: "2026-05-07T00:00:00Z",
        };
        currentStopListEntries = currentStopListEntries.map((entry) =>
          entry.id === 1 ? updatedEntry : entry,
        );
        return Response.json(updatedEntry);
      }

      if (
        url.endsWith("/v1/governance/profiles/default_it/stop-list/1") &&
        method === "DELETE"
      ) {
        currentStopListEntries = currentStopListEntries.filter((entry) => entry.id !== 1);
        return new Response(null, { status: 204 });
      }

      if (url.endsWith("/v1/governance/elasticsearch/connection/status") && method === "GET") {
        return Response.json({
          configured: true,
          ok: true,
          url: "http://localhost:9200",
          cluster_name: "skeinrank-dev",
          cluster_version: "8.13.4",
          error: null,
        });
      }

      if (url.endsWith("/v1/governance/elasticsearch/indices") && method === "GET") {
        return Response.json(cloneElasticsearchIndices());
      }

      if (url.includes("/v1/governance/elasticsearch/indices/") && url.endsWith("/mapping") && method === "GET") {
        const indexName = decodeURIComponent(url.split("/v1/governance/elasticsearch/indices/")[1].replace("/mapping", ""));
        return Response.json(cloneElasticsearchMapping(indexName));
      }

      if (url.includes("/v1/governance/elasticsearch/bindings") && method === "GET") {
        const profileName = new URL(url).searchParams.get("profile_name");
        const visibleBindings = profileName
          ? currentElasticsearchBindings.filter((binding) => binding.profile_name === profileName)
          : currentElasticsearchBindings;
        return Response.json(visibleBindings);
      }

      if (url.endsWith("/v1/governance/elasticsearch/bindings") && method === "POST") {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          description?: string | null;
          filter_field?: string | null;
          filter_value?: string | null;
          index_name: string;
          is_enabled?: boolean;
          mode?: ElasticsearchBinding["mode"];
          name: string;
          profile_name: string;
          target_field: string;
          text_fields: string[];
        };
        const binding: ElasticsearchBinding = {
          id: nextElasticsearchBindingId++,
          profile_id: 1,
          profile_name: payload.profile_name,
          name: payload.name,
          normalized_name: payload.name.toLowerCase().replace(/\s+/g, "_"),
          description: payload.description ?? null,
          provider: "elasticsearch",
          index_name: payload.index_name,
          text_fields: payload.text_fields,
          target_field: payload.target_field,
          filter_field: payload.filter_field ?? null,
          filter_value: payload.filter_value ?? null,
          mode: payload.mode ?? "dry_run",
          is_enabled: payload.is_enabled ?? true,
          created_at: "2026-05-07T00:00:00Z",
          updated_at: "2026-05-07T00:00:00Z",
        };
        currentElasticsearchBindings = [binding, ...currentElasticsearchBindings];
        return Response.json(binding, { status: 201 });
      }

      if (url.endsWith("/v1/governance/elasticsearch/bindings/1") && method === "PATCH") {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as Partial<ElasticsearchBinding> & { profile_name?: string | null; text_fields?: string[] | null };
        const existingBinding = currentElasticsearchBindings.find((binding) => binding.id === 1);
        if (!existingBinding) {
          return Response.json({ detail: "not found" }, { status: 404 });
        }
        const updatedBinding: ElasticsearchBinding = {
          ...existingBinding,
          name: payload.name ?? existingBinding.name,
          normalized_name: (payload.name ?? existingBinding.name).toLowerCase().replace(/\s+/g, "_"),
          profile_name: payload.profile_name ?? existingBinding.profile_name,
          description: payload.description ?? null,
          index_name: payload.index_name ?? existingBinding.index_name,
          text_fields: payload.text_fields ?? existingBinding.text_fields,
          target_field: payload.target_field ?? existingBinding.target_field,
          filter_field: payload.filter_field ?? null,
          filter_value: payload.filter_value ?? null,
          mode: payload.mode ?? existingBinding.mode,
          is_enabled: payload.is_enabled ?? existingBinding.is_enabled,
          updated_at: "2026-05-07T00:00:00Z",
        };
        currentElasticsearchBindings = currentElasticsearchBindings.map((binding) => binding.id === 1 ? updatedBinding : binding);
        return Response.json(updatedBinding);
      }

      if (url.endsWith("/v1/governance/elasticsearch/bindings/1") && method === "DELETE") {
        currentElasticsearchBindings = currentElasticsearchBindings.filter((binding) => binding.id !== 1);
        return new Response(null, { status: 204 });
      }

      if (
        (url.endsWith("/v1/governance/profiles/default_it/terms") ||
          url.endsWith("/v1/governance/profiles/platform_terms/terms")) &&
        method === "GET"
      ) {
        return Response.json(currentTerms);
      }

      if (
        url.endsWith("/v1/governance/profiles/default_it/terms") &&
        method === "POST"
      ) {
        if (options.duplicateTerm) {
          return Response.json(
            {
              detail: "Term already exists in profile 'default_it': kubernetes",
            },
            { status: 409 },
          );
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

      if (
        url.endsWith("/v1/governance/profiles/default_it/terms/kubernetes") &&
        method === "PATCH"
      ) {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          canonical_value?: string | null;
          description?: string | null;
          slot?: string | null;
          status?: string | null;
        };
        const updatedTerm: CanonicalTerm = {
          ...currentTerms[0],
          canonical_value:
            payload.canonical_value ?? currentTerms[0].canonical_value,
          normalized_value: (
            payload.canonical_value ?? currentTerms[0].canonical_value
          ).toLowerCase(),
          slot: payload.slot ?? currentTerms[0].slot,
          status: payload.status ?? currentTerms[0].status,
          description: payload.description ?? null,
          updated_at: "2026-05-05T00:00:00Z",
        };
        currentTerms = [updatedTerm, ...currentTerms.slice(1)];
        return Response.json(updatedTerm);
      }

      if (
        url.endsWith("/v1/governance/profiles/default_it/terms/kubernetes") &&
        method === "DELETE"
      ) {
        currentTerms = currentTerms.filter(
          (term) => term.canonical_value !== "kubernetes",
        );
        return new Response(null, { status: 204 });
      }

      if (
        url.endsWith(
          "/v1/governance/profiles/default_it/terms/kubernetes/aliases",
        ) &&
        method === "POST"
      ) {
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
          term.canonical_value === "kubernetes"
            ? { ...term, aliases: [...term.aliases, newAlias] }
            : term,
        );
        return Response.json(newAlias, { status: 201 });
      }

      if (
        url.endsWith(
          "/v1/governance/profiles/default_it/terms/kubernetes/aliases/1",
        ) &&
        method === "PATCH"
      ) {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          alias_value?: string | null;
          confidence?: number | null;
          notes?: string | null;
          status?: string | null;
        };
        const updatedAlias: TermAlias = {
          ...currentTerms[0].aliases[0],
          alias_value:
            payload.alias_value ?? currentTerms[0].aliases[0].alias_value,
          normalized_alias: (
            payload.alias_value ?? currentTerms[0].aliases[0].alias_value
          ).toLowerCase(),
          status: payload.status ?? currentTerms[0].aliases[0].status,
          confidence:
            payload.confidence ?? currentTerms[0].aliases[0].confidence,
          notes: payload.notes ?? null,
          updated_at: "2026-05-05T00:00:00Z",
        };
        currentTerms = currentTerms.map((term) => ({
          ...term,
          aliases: term.aliases.map((alias) =>
            alias.id === 1 ? updatedAlias : alias,
          ),
        }));
        return Response.json(updatedAlias);
      }

      if (
        url.endsWith(
          "/v1/governance/profiles/default_it/terms/kubernetes/aliases/1",
        ) &&
        method === "DELETE"
      ) {
        currentTerms = currentTerms.map((term) => ({
          ...term,
          aliases: term.aliases.filter((alias) => alias.id !== 1),
        }));
        return new Response(null, { status: 204 });
      }

      if (
        url.includes("/v1/governance/profiles/default_it/suggestions") &&
        method === "GET"
      ) {
        const status = new URL(url).searchParams.get("status");
        const visibleSuggestions = status
          ? currentSuggestions.filter(
              (suggestion) => suggestion.status === status,
            )
          : currentSuggestions;
        return Response.json(visibleSuggestions);
      }

      if (
        url.endsWith("/v1/governance/profiles/default_it/suggestions") &&
        method === "POST"
      ) {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          alias_value?: string | null;
          canonical_value: string;
          confidence?: number;
          context?: string | null;
          description?: string | null;
          slot: string;
          source?: GovernanceSuggestion["source"];
          suggestion_type?: GovernanceSuggestion["suggestion_type"];
        };
        const suggestionType = payload.suggestion_type ?? "alias";
        const suggestion: GovernanceSuggestion = {
          id: nextSuggestionId++,
          profile_id: 1,
          term_id:
            suggestionType === "alias"
              ? currentTerms.find(
                  (term) => term.canonical_value === payload.canonical_value,
                )?.id ?? null
              : null,
          alias_id: null,
          suggestion_type: suggestionType,
          canonical_value: payload.canonical_value,
          normalized_canonical: payload.canonical_value.toLowerCase(),
          alias_value: payload.alias_value ?? null,
          normalized_alias: payload.alias_value?.toLowerCase() ?? null,
          slot: payload.slot,
          description: payload.description ?? null,
          confidence: payload.confidence ?? 1,
          source: payload.source ?? "manual",
          context: payload.context ?? null,
          status: "pending",
          created_by: currentUser.username,
          reviewed_by: null,
          review_comment: null,
          reviewed_at: null,
          created_at: "2026-05-06T00:00:00Z",
          updated_at: "2026-05-06T00:00:00Z",
        };
        currentSuggestions = [suggestion, ...currentSuggestions];
        return Response.json(suggestion, { status: 201 });
      }

      if (
        url.includes("/v1/governance/profiles/default_it/suggestions/") &&
        url.endsWith("/approve") &&
        method === "POST"
      ) {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          review_comment?: string | null;
        };
        const suggestionId = Number(url.match(/suggestions\/(\d+)\/approve/)?.[1] ?? "0");
        const currentSuggestion =
          currentSuggestions.find((suggestion) => suggestion.id === suggestionId) ??
          currentSuggestions[0];
        let aliasId = currentSuggestion.alias_id;
        let termId = currentSuggestion.term_id;
        if (currentSuggestion.suggestion_type === "alias") {
          const newAlias: TermAlias = {
            id: nextAliasId++,
            alias_value: currentSuggestion.alias_value ?? "",
            normalized_alias: currentSuggestion.normalized_alias ?? "",
            status: "active",
            confidence: currentSuggestion.confidence,
            notes: currentSuggestion.context,
            created_at: "2026-05-06T00:00:00Z",
            updated_at: "2026-05-06T00:00:00Z",
          };
          aliasId = newAlias.id;
          currentTerms = currentTerms.map((term) =>
            term.canonical_value === currentSuggestion.canonical_value
              ? { ...term, aliases: [...term.aliases, newAlias] }
              : term,
          );
        } else {
          const newTerm: CanonicalTerm = {
            id: nextTermId++,
            canonical_value: currentSuggestion.canonical_value,
            normalized_value: currentSuggestion.normalized_canonical,
            slot: currentSuggestion.slot,
            status: "active",
            description: currentSuggestion.description,
            aliases: [],
            created_at: "2026-05-06T00:00:00Z",
            updated_at: "2026-05-06T00:00:00Z",
          };
          termId = newTerm.id;
          currentTerms = [...currentTerms, newTerm];
        }
        const updatedSuggestion: GovernanceSuggestion = {
          ...currentSuggestion,
          alias_id: aliasId,
          term_id: termId,
          status: "approved",
          reviewed_by: currentUser.username,
          review_comment: payload.review_comment ?? null,
          reviewed_at: "2026-05-06T00:00:00Z",
          updated_at: "2026-05-06T00:00:00Z",
        };
        currentSuggestions = currentSuggestions.map((suggestion) =>
          suggestion.id === currentSuggestion.id ? updatedSuggestion : suggestion,
        );
        return Response.json(updatedSuggestion);
      }

      if (
        url.includes("/v1/governance/profiles/default_it/suggestions/") &&
        url.endsWith("/reject") &&
        method === "POST"
      ) {
        const payload = JSON.parse(init?.body?.toString() ?? "{}") as {
          review_comment?: string | null;
        };
        const suggestionId = Number(url.match(/suggestions\/(\d+)\/reject/)?.[1] ?? "0");
        const currentSuggestion =
          currentSuggestions.find((suggestion) => suggestion.id === suggestionId) ??
          currentSuggestions[0];
        const updatedSuggestion: GovernanceSuggestion = {
          ...currentSuggestion,
          status: "rejected",
          reviewed_by: currentUser.username,
          review_comment: payload.review_comment ?? null,
          reviewed_at: "2026-05-06T00:00:00Z",
          updated_at: "2026-05-06T00:00:00Z",
        };
        currentSuggestions = currentSuggestions.map((suggestion) =>
          suggestion.id === currentSuggestion.id ? updatedSuggestion : suggestion,
        );
        return Response.json(updatedSuggestion);
      }

      if (
        url.endsWith("/v1/governance/profiles/default_it/snapshot/export") &&
        method === "POST"
      ) {
        return Response.json({
          profile_id: "default_it",
          snapshot: {
            version: "default_it@draft",
            source: "governance-api",
            created_at: "2026-05-05T00:00:00Z",
            description:
              "Runtime snapshot exported from the governance console.",
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
    },
  );
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

    expect(
      await screen.findByText("Terminology control plane"),
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getAllByText("default_it").length).toBeGreaterThan(0);
    });

    await waitFor(() => {
      expect(screen.getAllByText("kubernetes").length).toBeGreaterThan(0);
    });
    expect(screen.getAllByText("k8s").length).toBeGreaterThan(0);
    expect(
      screen.getByText("Postgres → Snapshot → Aho-Corasick"),
    ).toBeInTheDocument();
    expect(screen.getByText("MVP")).toBeInTheDocument();
    expect(screen.queryByText("UI skeleton")).not.toBeInTheDocument();
  });

  it("cycles the governance console theme", async () => {
    stubGovernanceApi();

    render(<App />);

    const themeButton = await screen.findByRole("button", {
      name: /switch theme/i,
    });
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

    fireEvent.change(screen.getByLabelText("New profile name"), {
      target: { value: "security_docs" },
    });
    fireEvent.change(screen.getByLabelText("New profile description"), {
      target: { value: "Security terminology" },
    });
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
    fireEvent.change(screen.getByLabelText("Profile name"), {
      target: { value: "platform_terms" },
    });
    fireEvent.change(screen.getByLabelText("Profile description"), {
      target: { value: "Platform terminology" },
    });
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

    fireEvent.click(await screen.findByRole("button", { name: "default_it" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Delete profile" }),
    );

    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: "default_it" }),
      ).not.toBeInTheDocument();
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

    fireEvent.change(screen.getByLabelText("Canonical value"), {
      target: { value: "postgresql" },
    });
    fireEvent.change(screen.getByLabelText("Slot"), {
      target: { value: "DB" },
    });
    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "PostgreSQL database" },
    });
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

    fireEvent.change(screen.getByLabelText("Edit canonical value"), {
      target: { value: "kubernetes" },
    });
    fireEvent.change(screen.getByLabelText("Edit slot"), {
      target: { value: "PLATFORM" },
    });
    fireEvent.change(screen.getByLabelText("Edit description"), {
      target: { value: "Container orchestration platform" },
    });
    fireEvent.change(screen.getByLabelText("Term status"), {
      target: { value: "deprecated" },
    });
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
      expect(
        screen.getByText("No terms found for this profile."),
      ).toBeInTheDocument();
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
    fireEvent.change(screen.getByLabelText("Notes"), {
      target: { value: "Common Kubernetes shorthand" },
    });
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

    const editAliasButton = await screen.findByRole("button", {
      name: "Edit alias",
    });
    expect(editAliasButton).not.toBeDisabled();
    fireEvent.click(editAliasButton);
    const editAliasInput = await screen.findByLabelText("Edit alias");
    fireEvent.change(editAliasInput, { target: { value: "kube" } });
    fireEvent.change(screen.getByLabelText("Edit alias notes"), {
      target: { value: "Short Kubernetes alias" },
    });

    const aliasStatusSelect = screen.getByLabelText(
      "Alias status",
    ) as HTMLSelectElement;
    const aliasStatusOptions = Array.from(aliasStatusSelect.options).map(
      (option) => option.value,
    );
    expect(aliasStatusOptions).toEqual(["active", "deprecated", "disabled"]);
    expect(aliasStatusOptions).not.toContain("ambiguous");
    expect(aliasStatusOptions).not.toContain("pending");
    expect(aliasStatusOptions).not.toContain("rejected");

    fireEvent.change(aliasStatusSelect, { target: { value: "deprecated" } });
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
    const clickAnchor = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: createObjectUrl,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: revokeObjectUrl,
    });

    render(<App />);

    await screen.findByText("default_it");
    await screen.findByText("kubernetes");

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Export draft snapshot" })).not.toBeDisabled();
    });
    fireEvent.click(screen.getByRole("button", { name: "Export draft snapshot" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/profiles/default_it/snapshot/export",
        expect.objectContaining({
          body: JSON.stringify({
            snapshot_version: "default_it@draft",
            description:
              "Runtime snapshot exported from the governance console.",
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

    const downloadButton = screen.getByRole("button", {
      name: "Download JSON",
    });
    await waitFor(() => expect(downloadButton).not.toBeDisabled());
    fireEvent.click(downloadButton);

    expect(createObjectUrl).toHaveBeenCalledTimes(1);
    expect(clickAnchor).toHaveBeenCalledTimes(1);
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:skeinrank-snapshot");
  });

  it("signs in when auth is enabled and sends bearer tokens", async () => {
    const fetchMock = stubGovernanceApi({ authRequired: true });

    render(<App />);

    expect(await screen.findByText("SkeinRank sign in")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Username"), {
      target: { value: "admin" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "change-me" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await screen.findByText("Terminology control plane");
    await screen.findByText("default_it");

    const profileRequest = fetchMock.mock.calls.find(([url]) =>
      url.toString().endsWith("/v1/governance/profiles"),
    );
    expect(profileRequest).toBeTruthy();
    expect(new Headers(profileRequest?.[1]?.headers).get("Authorization")).toBe(
      "Bearer test-token",
    );
    expect(window.localStorage.getItem("skeinrank-ui-auth-token")).toBe(
      "test-token",
    );
  });

  it("lets admins manage users from the Users page", async () => {
    const fetchMock = stubGovernanceApi();
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<App />);

    await screen.findByText("Terminology control plane");
    fireEvent.click(screen.getByRole("button", { name: "Users" }));

    expect(await screen.findByText("Users and roles")).toBeInTheDocument();
    expect(await screen.findByText("Admin User")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("New username"), {
      target: { value: "alex" },
    });
    fireEvent.change(screen.getByLabelText("New display name"), {
      target: { value: "Alex Kim" },
    });
    fireEvent.change(screen.getByLabelText("Temporary password"), {
      target: { value: "temporary-password" },
    });
    fireEvent.change(screen.getByLabelText("New user role"), {
      target: { value: "moderator" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create user" }));

    await screen.findByText("Alex Kim");
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8010/v1/auth/users",
      expect.objectContaining({
        body: JSON.stringify({
          username: "alex",
          password: "temporary-password",
          display_name: "Alex Kim",
          role: "moderator",
          is_active: true,
        }),
        method: "POST",
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: /contributor/i }));
    fireEvent.change(screen.getByLabelText("Display name"), {
      target: { value: "Term Contributor" },
    });
    fireEvent.change(screen.getByLabelText("Role"), {
      target: { value: "moderator" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save user" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/auth/users/contributor",
        expect.objectContaining({
          body: JSON.stringify({
            username: "contributor",
            display_name: "Term Contributor",
            password: null,
            role: "moderator",
            is_active: true,
          }),
          method: "PATCH",
        }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "Delete user" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/auth/users/contributor",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
  });


  it("lets admins manage profile stop-list guardrails", async () => {
    const fetchMock = stubGovernanceApi();
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<App />);

    await screen.findByText("Terminology control plane");
    fireEvent.click(screen.getByRole("button", { name: "Guardrails" }));

    expect(await screen.findByText("Manage stop lists that block noisy or unsafe terminology changes.")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByText("service").length).toBeGreaterThan(0);
    });
    expect(screen.getByText("Too generic for incident search")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Blocked value"), {
      target: { value: "app" },
    });
    fireEvent.change(screen.getByLabelText("Target"), {
      target: { value: "both" },
    });
    fireEvent.change(screen.getByLabelText("Reason"), {
      target: { value: "Too broad for runtime matching" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add to stop list" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/profiles/default_it/stop-list",
        expect.objectContaining({
          body: JSON.stringify({
            value: "app",
            target: "both",
            reason: "Too broad for runtime matching",
            is_active: true,
          }),
          method: "POST",
        }),
      );
    });
    expect((await screen.findAllByText("app")).length).toBeGreaterThanOrEqual(1);

    fireEvent.click(screen.getAllByText("service")[0]);
    fireEvent.change(screen.getByLabelText("Edit blocked value"), {
      target: { value: "svc" },
    });
    fireEvent.change(screen.getByLabelText("Edit target"), {
      target: { value: "canonical" },
    });
    fireEvent.change(screen.getByLabelText("Edit reason"), {
      target: { value: "Reserved internal abbreviation" },
    });
    fireEvent.click(screen.getByLabelText("Active guardrail"));
    fireEvent.click(screen.getByRole("button", { name: "Save stop-list entry" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/profiles/default_it/stop-list/1",
        expect.objectContaining({
          body: JSON.stringify({
            value: "svc",
            target: "canonical",
            reason: "Reserved internal abbreviation",
            is_active: false,
          }),
          method: "PATCH",
        }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "Delete stop-list entry" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/profiles/default_it/stop-list/1",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
  });

  it("keeps contributor users in read-only guardrails mode", async () => {
    stubGovernanceApi({ currentUser: contributorUser });

    render(<App />);

    await screen.findByText("Terminology control plane");
    fireEvent.click(screen.getByRole("button", { name: "Guardrails" }));

    await waitFor(() => {
      expect(screen.getAllByText("service").length).toBeGreaterThan(0);
    });
    expect(screen.getByRole("button", { name: "Add to stop list" })).toBeDisabled();
    expect(screen.getByText("Your role can inspect guardrails, but only admins and moderators can update stop lists.")).toBeInTheDocument();
    expect(screen.getByText("Contributors can inspect stop lists, but only admins and moderators can update guardrails.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save stop-list entry" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Delete stop-list entry" })).toBeDisabled();
  });

  it("lets admins manage Elasticsearch enrichment bindings", async () => {
    const fetchMock = stubGovernanceApi();
    vi.spyOn(window, "confirm").mockReturnValue(true);

    render(<App />);

    await screen.findByText("Terminology control plane");
    fireEvent.click(screen.getByRole("button", { name: "Integrations" }));

    expect(await screen.findByText("Elasticsearch bindings")).toBeInTheDocument();
    expect(await screen.findByText("Connected")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByText("infra docs").length).toBeGreaterThan(0);
    });
    fireEvent.click(screen.getAllByText("infra docs")[0]);
    await waitFor(() => {
      expect(screen.getByLabelText("Edit description")).toHaveValue("Apply default IT terms to docs.");
    });

    fireEvent.change(screen.getByLabelText("Binding name"), { target: { value: "runbook docs" } });
    fireEvent.change(screen.getByLabelText("Index"), { target: { value: "runbooks" } });
    expect(await screen.findByText("Discovered text fields")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Text fields/), { target: { value: "title, body, summary" } });
    fireEvent.change(screen.getByLabelText("Target field"), { target: { value: "skeinrank" } });
    fireEvent.change(screen.getByLabelText("Document discriminator field"), { target: { value: "team" } });
    fireEvent.change(screen.getByLabelText("Value for this profile"), { target: { value: "infra" } });
    fireEvent.click(screen.getByRole("button", { name: "Create binding" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/elasticsearch/bindings",
        expect.objectContaining({
          body: JSON.stringify({
            name: "runbook docs",
            profile_name: "default_it",
            description: null,
            index_name: "runbooks",
            text_fields: ["title", "body", "summary"],
            target_field: "skeinrank",
            filter_field: "team",
            filter_value: "infra",
            mode: "dry_run",
            is_enabled: true,
          }),
          method: "POST",
        }),
      );
    });
    expect((await screen.findAllByText("runbook docs")).length).toBeGreaterThanOrEqual(1);

    fireEvent.click(screen.getAllByText("infra docs")[0]);
    fireEvent.change(screen.getByLabelText("Edit binding name"), { target: { value: "infra docs v2" } });
    fireEvent.change(screen.getByLabelText("Edit index"), { target: { value: "docs-v2" } });
    fireEvent.change(screen.getByLabelText("Edit text fields"), { target: { value: "title\nbody" } });
    fireEvent.change(screen.getByLabelText("Edit target field"), { target: { value: "skeinrank_attrs" } });
    fireEvent.change(screen.getByLabelText("Edit document discriminator field"), { target: { value: "space" } });
    fireEvent.change(screen.getByLabelText("Edit value for this profile"), { target: { value: "infra" } });
    fireEvent.change(screen.getByLabelText("Edit mode"), { target: { value: "write" } });
    fireEvent.click(screen.getByLabelText("Edit enabled binding"));
    fireEvent.click(screen.getByRole("button", { name: "Save binding" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/elasticsearch/bindings/1",
        expect.objectContaining({
          body: JSON.stringify({
            name: "infra docs v2",
            profile_name: "default_it",
            description: "Apply default IT terms to docs.",
            index_name: "docs-v2",
            text_fields: ["title", "body"],
            target_field: "skeinrank_attrs",
            filter_field: "space",
            filter_value: "infra",
            mode: "write",
            is_enabled: false,
          }),
          method: "PATCH",
        }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "Delete binding" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/elasticsearch/bindings/1",
        expect.objectContaining({ method: "DELETE" }),
      );
    });
  });

  it("requires a discriminator when multiple profiles share one Elasticsearch index", async () => {
    stubGovernanceApi();

    render(<App />);

    await screen.findByText("Terminology control plane");
    fireEvent.click(screen.getByRole("button", { name: "Integrations" }));

    expect(await screen.findByText("Elasticsearch bindings")).toBeInTheDocument();
    expect(await screen.findByText("Connected")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Profile"), { target: { value: "ml_platform" } });
    fireEvent.change(screen.getByLabelText("Binding name"), { target: { value: "ml docs without discriminator" } });
    fireEvent.change(screen.getByLabelText("Index"), { target: { value: "docs" } });
    fireEvent.change(screen.getByLabelText(/Text fields/), { target: { value: "title, body" } });
    fireEvent.change(screen.getByLabelText("Target field"), { target: { value: "skeinrank" } });

    expect(
      await screen.findByText(/This index is already used by another profile/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create binding" })).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Document discriminator field"), { target: { value: "team" } });
    fireEvent.change(screen.getByLabelText("Value for this profile"), { target: { value: "ml-platform" } });

    expect((await screen.findAllByText(/The discriminator keeps this profile scoped/)).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Create binding" })).not.toBeDisabled();
  });

  it("keeps contributor users in read-only integrations mode", async () => {
    stubGovernanceApi({ currentUser: contributorUser });

    render(<App />);

    await screen.findByText("Terminology control plane");
    fireEvent.click(screen.getByRole("button", { name: "Integrations" }));

    await waitFor(() => {
      expect(screen.getAllByText("infra docs").length).toBeGreaterThan(0);
    });
    expect(screen.getByRole("button", { name: "Create binding" })).toBeDisabled();
    expect(screen.getByText("Your role can inspect Elasticsearch bindings, but only admins and moderators can update integrations.")).toBeInTheDocument();
    expect(screen.getByText("Contributors can inspect bindings, but only admins and moderators can update Elasticsearch integration configs.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save binding" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Delete binding" })).toBeDisabled();
  });

  it("keeps contributor users in read-only governance mode", async () => {
    stubGovernanceApi({ currentUser: contributorUser });

    render(<App />);

    await screen.findByText("Terminology control plane");
    await screen.findByText("default_it");
    await screen.findByText("kubernetes");

    expect(
      screen.queryByRole("button", { name: "Users" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add term" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Create profile" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Export draft snapshot" }),
    ).toBeDisabled();
    expect(
      screen.queryByRole("button", { name: "Edit alias" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(
        "Your role has read-only access to this terminology profile. Use the Suggestions tab to propose changes for review.",
      ),
    ).toBeInTheDocument();
  });

  it("lets contributors create suggestions without review actions", async () => {
    const fetchMock = stubGovernanceApi({ currentUser: contributorUser });

    render(<App />);

    await screen.findByText("Terminology control plane");
    fireEvent.click(screen.getByRole("button", { name: "Suggestions" }));

    expect(
      await screen.findByText("Suggestions and approvals"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("People search for kube in incident docs."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Contributors can create suggestions, but only admins and moderators can approve or reject them.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Approve suggestion/ }),
    ).toBeDisabled();

    expect(screen.queryByLabelText("Confidence")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Source")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Canonical term"), {
      target: { value: "kube" },
    });
    fireEvent.click(
      await screen.findByRole("button", { name: /kubernetes.*1 aliases/i }),
    );
    expect(screen.getByLabelText("Slot")).toHaveValue("TOOL");
    expect(screen.getByText("Existing aliases")).toBeInTheDocument();
    expect(screen.getByText("k8s")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Suggested alias"), {
      target: { value: "k8s-prod" },
    });
    fireEvent.change(screen.getByLabelText("Context"), {
      target: { value: "Support tickets mention k8s-prod." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create suggestion" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/profiles/default_it/suggestions",
        expect.objectContaining({
          body: JSON.stringify({
            suggestion_type: "alias",
            canonical_value: "kubernetes",
            alias_value: "k8s-prod",
            slot: "TOOL",
            confidence: 1,
            source: "manual",
            context: "Support tickets mention k8s-prod.",
          }),
          method: "POST",
        }),
      );
    });
  });

  it("blocks duplicate alias suggestions for the selected canonical term", async () => {
    stubGovernanceApi({ currentUser: contributorUser });

    render(<App />);

    await screen.findByText("Terminology control plane");
    fireEvent.click(screen.getByRole("button", { name: "Suggestions" }));

    expect(
      await screen.findByText("Suggestions and approvals"),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Canonical term"), {
      target: { value: "kubernetes" },
    });
    fireEvent.click(
      await screen.findByRole("button", { name: /kubernetes.*1 aliases/i }),
    );
    fireEvent.change(screen.getByLabelText("Suggested alias"), {
      target: { value: "k8s" },
    });

    expect(
      await screen.findByText(/This alias already exists for kubernetes/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Create suggestion" }),
    ).toBeDisabled();
  });

  it("lets contributors suggest new canonical terms", async () => {
    const fetchMock = stubGovernanceApi({ currentUser: contributorUser });

    render(<App />);

    await screen.findByText("Terminology control plane");
    fireEvent.click(screen.getByRole("button", { name: "Suggestions" }));

    expect(
      await screen.findByText("Suggestions and approvals"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /New canonical term/ }));
    fireEvent.change(screen.getByLabelText("New canonical term"), {
      target: { value: "vector database" },
    });
    fireEvent.change(screen.getByLabelText("Slot"), {
      target: { value: "TOOL" },
    });
    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "Storage optimized for vector similarity search." },
    });
    fireEvent.change(screen.getByLabelText("Context"), {
      target: { value: "No canonical term exists for vectordb searches." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create suggestion" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/profiles/default_it/suggestions",
        expect.objectContaining({
          body: JSON.stringify({
            suggestion_type: "canonical_term",
            canonical_value: "vector database",
            alias_value: null,
            slot: "TOOL",
            description: "Storage optimized for vector similarity search.",
            confidence: 1,
            source: "manual",
            context: "No canonical term exists for vectordb searches.",
          }),
          method: "POST",
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getAllByText("vector database").length).toBeGreaterThan(0);
    });
    expect(screen.getAllByText("Proposed new canonical term").length).toBeGreaterThan(0);
  });

  it("blocks duplicate canonical term suggestions", async () => {
    stubGovernanceApi({ currentUser: contributorUser });

    render(<App />);

    await screen.findByText("Terminology control plane");
    fireEvent.click(screen.getByRole("button", { name: "Suggestions" }));

    expect(
      await screen.findByText("Suggestions and approvals"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /New canonical term/ }));
    fireEvent.change(screen.getByLabelText("New canonical term"), {
      target: { value: "kubernetes" },
    });
    fireEvent.change(screen.getByLabelText("Slot"), {
      target: { value: "TOOL" },
    });

    expect(
      await screen.findByText(/This canonical term already exists/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Create suggestion" }),
    ).toBeDisabled();
  });

  it("lets moderators approve suggestions into active aliases", async () => {
    const fetchMock = stubGovernanceApi({ currentUser: moderatorUser });

    render(<App />);

    await screen.findByText("Terminology control plane");
    fireEvent.click(screen.getByRole("button", { name: "Suggestions" }));

    expect(
      await screen.findByText("Suggestions and approvals"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("People search for kube in incident docs."),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Review comment"), {
      target: { value: "Looks valid for Kubernetes docs." },
    });
    fireEvent.click(screen.getByRole("button", { name: /Approve suggestion/ }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/profiles/default_it/suggestions/1/approve",
        expect.objectContaining({
          body: JSON.stringify({
            review_comment: "Looks valid for Kubernetes docs.",
          }),
          method: "POST",
        }),
      );
    });

    await waitFor(() => {
      expect(
        screen.getByText("No suggestions found for this filter."),
      ).toBeInTheDocument();
    });
    expect(
      screen.queryByText("This suggestion has already been reviewed."),
    ).not.toBeInTheDocument();
  });

  it("lets admins reject suggestions with a review comment", async () => {
    const fetchMock = stubGovernanceApi();

    render(<App />);

    await screen.findByText("Terminology control plane");
    fireEvent.click(screen.getByRole("button", { name: "Suggestions" }));

    expect(
      await screen.findByText("Suggestions and approvals"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("People search for kube in incident docs."),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Review comment"), {
      target: { value: "Too ambiguous for the default profile." },
    });
    fireEvent.click(screen.getByRole("button", { name: /Reject suggestion/ }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "http://127.0.0.1:8010/v1/governance/profiles/default_it/suggestions/1/reject",
        expect.objectContaining({
          body: JSON.stringify({
            review_comment: "Too ambiguous for the default profile.",
          }),
          method: "POST",
        }),
      );
    });

    await waitFor(() => {
      expect(
        screen.getByText("No suggestions found for this filter."),
      ).toBeInTheDocument();
    });
    expect(
      screen.queryByText("This suggestion has already been reviewed."),
    ).not.toBeInTheDocument();
  });

  it("shows governance API conflicts when a canonical term cannot be added", async () => {
    stubGovernanceApi({ duplicateTerm: true });

    render(<App />);

    await screen.findByText("default_it");

    fireEvent.change(screen.getByLabelText("Canonical value"), {
      target: { value: "kubernetes" },
    });
    fireEvent.change(screen.getByLabelText("Slot"), {
      target: { value: "TOOL" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add term" }));

    expect(
      await screen.findByText(
        "Term already exists in profile 'default_it': kubernetes",
      ),
    ).toBeInTheDocument();
  });
});
