import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle, Search, XCircle } from "lucide-react";
import { type FormEvent, useEffect, useMemo, useState } from "react";

import { EvidenceDocumentsList } from "../components/EvidenceDocumentsList";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../components/ui/card";
import { Input } from "../components/ui/input";
import {
  approveSuggestion,
  createSuggestion,
  listElasticsearchBindings,
  listProfiles,
  listSuggestions,
  listTerms,
  refreshSuggestionEvidence,
  rejectSuggestion,
} from "../lib/api";
import { permissionsForUser } from "../permissions";
import type {
  AuthUser,
  CanonicalTerm,
  ElasticsearchBinding,
  GovernanceSuggestion,
  Profile,
  SuggestionCreateRequest,
  SuggestionEvidenceSnapshot,
  SuggestionReviewRequest,
  SuggestionStatus,
  SuggestionType,
} from "../types";

const statusFilters: Array<SuggestionStatus | "all"> = [
  "pending",
  "approved",
  "rejected",
  "all",
];

type SuggestionsSection = "propose" | "review";

export function SuggestionsPage({ currentUser }: { currentUser: AuthUser }) {
  const permissions = permissionsForUser(currentUser);
  const [activeSection, setActiveSection] = useState<SuggestionsSection>(
    permissions.canReviewSuggestions ? "review" : "propose",
  );
  const queryClient = useQueryClient();
  const profilesQuery = useQuery({
    queryKey: ["profiles"],
    queryFn: listProfiles,
  });
  const [selectedProfile, setSelectedProfile] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<SuggestionStatus | "all">(
    "pending",
  );
  const [selectedSuggestionId, setSelectedSuggestionId] = useState<
    number | null
  >(null);

  useEffect(() => {
    if (!profilesQuery.data || profilesQuery.data.length === 0) {
      setSelectedProfile(null);
      setSelectedSuggestionId(null);
      return;
    }

    if (
      !selectedProfile ||
      !profilesQuery.data.some((profile) => profile.name === selectedProfile)
    ) {
      setSelectedProfile(profilesQuery.data[0].name);
      setSelectedSuggestionId(null);
    }
  }, [profilesQuery.data, selectedProfile]);

  const suggestionsQuery = useQuery({
    queryKey: ["suggestions", selectedProfile, statusFilter],
    queryFn: () => listSuggestions(selectedProfile ?? "", statusFilter),
    enabled: Boolean(selectedProfile),
  });

  const termsQuery = useQuery({
    queryKey: ["terms", selectedProfile],
    queryFn: () => listTerms(selectedProfile ?? ""),
    enabled: Boolean(selectedProfile),
  });

  const bindingsQuery = useQuery({
    queryKey: ["elasticsearch", "bindings", selectedProfile],
    queryFn: () => listElasticsearchBindings(selectedProfile ?? ""),
    enabled: Boolean(selectedProfile),
  });

  useEffect(() => {
    if (!suggestionsQuery.data) {
      return;
    }
    if (suggestionsQuery.data.length === 0) {
      setSelectedSuggestionId(null);
      return;
    }
    if (
      !selectedSuggestionId ||
      !suggestionsQuery.data.some(
        (suggestion) => suggestion.id === selectedSuggestionId,
      )
    ) {
      setSelectedSuggestionId(suggestionsQuery.data[0].id);
    }
  }, [selectedSuggestionId, suggestionsQuery.data]);

  const selectedSuggestion = useMemo(() => {
    if (!suggestionsQuery.data || !selectedSuggestionId) {
      return null;
    }
    return (
      suggestionsQuery.data.find(
        (suggestion) => suggestion.id === selectedSuggestionId,
      ) ?? null
    );
  }, [selectedSuggestionId, suggestionsQuery.data]);

  const createSuggestionMutation = useMutation({
    mutationFn: (payload: SuggestionCreateRequest) => {
      if (!selectedProfile) {
        throw new Error("Select a profile before creating a suggestion.");
      }
      return createSuggestion(selectedProfile, payload);
    },
    onSuccess: (suggestion) => {
      setStatusFilter("pending");
      setActiveSection("review");
      setSelectedSuggestionId(suggestion.id);
      upsertSuggestion(queryClient, selectedProfile, statusFilter, suggestion);
      upsertSuggestion(queryClient, selectedProfile, "pending", suggestion);
      void queryClient.invalidateQueries({
        queryKey: ["suggestions", selectedProfile],
      });
    },
  });

  const approveSuggestionMutation = useMutation({
    mutationFn: ({
      suggestion,
      payload,
    }: {
      suggestion: GovernanceSuggestion;
      payload: SuggestionReviewRequest;
    }) => {
      if (!selectedProfile) {
        throw new Error("Select a profile before approving a suggestion.");
      }
      return approveSuggestion(selectedProfile, suggestion.id, payload);
    },
    onSuccess: (suggestion) => {
      const shouldKeepReviewedSuggestionVisible =
        statusFilter === "all" || statusFilter === suggestion.status;
      setSelectedSuggestionId(
        shouldKeepReviewedSuggestionVisible ? suggestion.id : null,
      );
      syncReviewedSuggestion(
        queryClient,
        selectedProfile,
        statusFilter,
        suggestion,
      );
      void queryClient.invalidateQueries({
        queryKey: ["suggestions", selectedProfile],
      });
      void queryClient.invalidateQueries({
        queryKey: ["terms", selectedProfile],
      });
    },
  });

  const rejectSuggestionMutation = useMutation({
    mutationFn: ({
      suggestion,
      payload,
    }: {
      suggestion: GovernanceSuggestion;
      payload: SuggestionReviewRequest;
    }) => {
      if (!selectedProfile) {
        throw new Error("Select a profile before rejecting a suggestion.");
      }
      return rejectSuggestion(selectedProfile, suggestion.id, payload);
    },
    onSuccess: (suggestion) => {
      const shouldKeepReviewedSuggestionVisible =
        statusFilter === "all" || statusFilter === suggestion.status;
      setSelectedSuggestionId(
        shouldKeepReviewedSuggestionVisible ? suggestion.id : null,
      );
      syncReviewedSuggestion(
        queryClient,
        selectedProfile,
        statusFilter,
        suggestion,
      );
      void queryClient.invalidateQueries({
        queryKey: ["suggestions", selectedProfile],
      });
    },
  });

  const refreshEvidenceMutation = useMutation({
    mutationFn: ({
      bindingId,
      maxDocuments,
      query,
      suggestion,
    }: {
      bindingId: number;
      maxDocuments: number;
      query?: string | null;
      suggestion: GovernanceSuggestion;
    }) => {
      if (!selectedProfile) {
        throw new Error("Select a profile before checking evidence.");
      }
      return refreshSuggestionEvidence(selectedProfile, suggestion.id, {
        binding_id: bindingId,
        max_documents: maxDocuments,
        query: query?.trim() || null,
      });
    },
    onSuccess: (suggestion) => {
      upsertSuggestion(queryClient, selectedProfile, statusFilter, suggestion);
      upsertSuggestion(
        queryClient,
        selectedProfile,
        suggestion.status,
        suggestion,
      );
      void queryClient.invalidateQueries({
        queryKey: ["suggestions", selectedProfile],
      });
    },
  });

  async function handleCreateSuggestion(payload: SuggestionCreateRequest) {
    await createSuggestionMutation.mutateAsync(payload);
  }

  async function handleApproveSuggestion(
    suggestion: GovernanceSuggestion,
    payload: SuggestionReviewRequest,
  ) {
    await approveSuggestionMutation.mutateAsync({ suggestion, payload });
  }

  async function handleRejectSuggestion(
    suggestion: GovernanceSuggestion,
    payload: SuggestionReviewRequest,
  ) {
    await rejectSuggestionMutation.mutateAsync({ suggestion, payload });
  }

  async function handleRefreshSuggestionEvidence(
    suggestion: GovernanceSuggestion,
    bindingId: number,
    query: string,
    maxDocuments: number,
  ) {
    await refreshEvidenceMutation.mutateAsync({
      bindingId,
      maxDocuments,
      query,
      suggestion,
    });
  }

  const suggestionsCount = suggestionsQuery.data?.length ?? 0;
  const selectedProfileLabel = selectedProfile ?? "No profile";

  return (
    <div className="space-y-6">
      <SuggestionsSectionTabs
        activeSection={activeSection}
        onSelectSection={setActiveSection}
        selectedProfile={selectedProfileLabel}
        suggestionsCount={suggestionsCount}
      />

      {activeSection === "propose" ? (
        <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div className="space-y-6">
            <SuggestionsToolbar
              description="Choose the terminology namespace for the proposal."
              isLoading={profilesQuery.isLoading}
              loadErrorMessage={
                profilesQuery.isError ? profilesQuery.error.message : null
              }
              onSelectProfile={(profileName) => {
                setSelectedProfile(profileName);
                setSelectedSuggestionId(null);
                createSuggestionMutation.reset();
                approveSuggestionMutation.reset();
                rejectSuggestionMutation.reset();
                refreshEvidenceMutation.reset();
              }}
              onSetStatusFilter={(status) => {
                setStatusFilter(status);
                setSelectedSuggestionId(null);
              }}
              profiles={profilesQuery.data ?? []}
              selectedProfile={selectedProfile}
              showStatusFilter={false}
              statusFilter={statusFilter}
              title="Proposal scope"
            />

            <CreateSuggestionForm
              disabled={!selectedProfile || !permissions.canCreateSuggestions}
              errorMessage={errorMessage(createSuggestionMutation.error)}
              isSubmitting={createSuggestionMutation.isPending}
              onSubmit={handleCreateSuggestion}
              readOnlyMessage={
                permissions.canCreateSuggestions
                  ? null
                  : "Your role can inspect suggestions, but cannot create new proposals."
              }
              terms={termsQuery.data ?? []}
              termsErrorMessage={
                termsQuery.isError ? termsQuery.error.message : null
              }
              termsLoading={termsQuery.isLoading && Boolean(selectedProfile)}
            />
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Proposal workflow</CardTitle>
              <CardDescription>
                Create a candidate change without mutating active terminology.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-slate-600 dark:text-slate-300">
              <WorkflowStep number="1" title="Pick a profile" />
              <WorkflowStep number="2" title="Propose an alias or canonical term" />
              <WorkflowStep number="3" title="Moderator reviews evidence" />
              <WorkflowStep number="4" title="Approved changes update Terms" />
            </CardContent>
          </Card>
        </section>
      ) : (
        <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
          <div className="space-y-6">
            <SuggestionsToolbar
              description="Filter proposals that need review or audit already reviewed changes."
              isLoading={profilesQuery.isLoading}
              loadErrorMessage={
                profilesQuery.isError ? profilesQuery.error.message : null
              }
              onSelectProfile={(profileName) => {
                setSelectedProfile(profileName);
                setSelectedSuggestionId(null);
                createSuggestionMutation.reset();
                approveSuggestionMutation.reset();
                rejectSuggestionMutation.reset();
                refreshEvidenceMutation.reset();
              }}
              onSetStatusFilter={(status) => {
                setStatusFilter(status);
                setSelectedSuggestionId(null);
              }}
              profiles={profilesQuery.data ?? []}
              selectedProfile={selectedProfile}
              showStatusFilter
              statusFilter={statusFilter}
              title="Review scope"
            />

            <SuggestionsTable
              isLoading={suggestionsQuery.isLoading && Boolean(selectedProfile)}
              loadErrorMessage={
                suggestionsQuery.isError ? suggestionsQuery.error.message : null
              }
              onSelectSuggestion={(suggestion) => {
                setSelectedSuggestionId(suggestion.id);
                approveSuggestionMutation.reset();
                rejectSuggestionMutation.reset();
                refreshEvidenceMutation.reset();
              }}
              selectedSuggestionId={selectedSuggestionId}
              suggestions={suggestionsQuery.data ?? []}
            />
          </div>

          <SuggestionDetailsPanel
            bindings={bindingsQuery.data ?? []}
            bindingsErrorMessage={
              bindingsQuery.isError ? bindingsQuery.error.message : null
            }
            bindingsLoading={bindingsQuery.isLoading && Boolean(selectedProfile)}
            canReview={permissions.canReviewSuggestions}
            evidenceErrorMessage={errorMessage(refreshEvidenceMutation.error)}
            isApproving={approveSuggestionMutation.isPending}
            isRefreshingEvidence={refreshEvidenceMutation.isPending}
            isRejecting={rejectSuggestionMutation.isPending}
            onApprove={handleApproveSuggestion}
            onRefreshEvidence={handleRefreshSuggestionEvidence}
            onReject={handleRejectSuggestion}
            reviewErrorMessage={
              errorMessage(approveSuggestionMutation.error) ??
              errorMessage(rejectSuggestionMutation.error)
            }
            suggestion={selectedSuggestion}
          />
        </section>
      )}
    </div>
  );
}

function SuggestionsSectionTabs({
  activeSection,
  onSelectSection,
  selectedProfile,
  suggestionsCount,
}: {
  activeSection: SuggestionsSection;
  onSelectSection: (section: SuggestionsSection) => void;
  selectedProfile: string;
  suggestionsCount: number;
}) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-800 dark:bg-slate-950">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-base font-semibold tracking-tight text-slate-950 dark:text-slate-50">
            Suggestion workspace
          </h2>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Propose terminology changes separately from moderator review.
          </p>
        </div>
        <div
          aria-label="Suggestion section"
          className="inline-flex w-full rounded-2xl border border-slate-200 bg-slate-50 p-1 dark:border-slate-800 dark:bg-slate-900 lg:w-auto"
          role="tablist"
        >
          <SuggestionsTabButton
            isActive={activeSection === "propose"}
            label="Propose"
            meta={selectedProfile}
            onClick={() => onSelectSection("propose")}
          />
          <SuggestionsTabButton
            isActive={activeSection === "review"}
            label="Review queue"
            meta={`${suggestionsCount} visible`}
            onClick={() => onSelectSection("review")}
          />
        </div>
      </div>
    </section>
  );
}

function SuggestionsTabButton({
  isActive,
  label,
  meta,
  onClick,
}: {
  isActive: boolean;
  label: string;
  meta: string;
  onClick: () => void;
}) {
  return (
    <button
      aria-selected={isActive}
      className={`flex min-w-0 flex-1 flex-col rounded-xl px-4 py-2 text-left transition-colors lg:min-w-40 lg:flex-none ${
        isActive
          ? "bg-white text-slate-950 shadow-sm dark:bg-slate-950 dark:text-slate-50"
          : "text-slate-500 hover:text-slate-950 dark:text-slate-400 dark:hover:text-slate-100"
      }`}
      onClick={onClick}
      role="tab"
      type="button"
    >
      <span className="text-sm font-semibold">{label}</span>
      <span className="mt-0.5 truncate text-xs text-slate-500 dark:text-slate-400">
        {meta}
      </span>
    </button>
  );
}

function WorkflowStep({ number, title }: { number: string; title: string }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-slate-100 px-3 py-2 dark:border-slate-800">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold text-slate-600 dark:bg-slate-900 dark:text-slate-300">
        {number}
      </span>
      <span>{title}</span>
    </div>
  );
}

function SuggestionsToolbar({
  description,
  isLoading,
  loadErrorMessage,
  onSelectProfile,
  onSetStatusFilter,
  profiles,
  selectedProfile,
  showStatusFilter = true,
  statusFilter,
  title,
}: {
  description: string;
  isLoading: boolean;
  loadErrorMessage?: string | null;
  onSelectProfile: (profileName: string) => void;
  onSetStatusFilter: (status: SuggestionStatus | "all") => void;
  profiles: Profile[];
  selectedProfile: string | null;
  showStatusFilter?: boolean;
  statusFilter: SuggestionStatus | "all";
  title: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {loadErrorMessage ? <InlineError message={loadErrorMessage} /> : null}
        {isLoading ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Loading profiles...
          </p>
        ) : null}
        {profiles.length > 0 ? (
          <div className="space-y-2">
            <div className="text-sm font-medium text-slate-700 dark:text-slate-200">
              Profile
            </div>
            <div className="flex flex-wrap gap-2">
              {profiles.map((profile) => (
                <button
                  className={`rounded-full border px-3 py-1.5 text-sm font-medium transition-colors ${
                    selectedProfile === profile.name
                      ? "border-slate-950 bg-slate-950 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-950"
                      : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300 dark:hover:bg-slate-900"
                  }`}
                  key={profile.id}
                  onClick={() => onSelectProfile(profile.name)}
                  type="button"
                >
                  {profile.name}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <p className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
            No profiles found. Create a terminology profile before collecting
            suggestions.
          </p>
        )}

        {showStatusFilter ? (
          <label className="block space-y-1.5">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
              Suggestion status
            </span>
            <select
              className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:focus:border-slate-500 dark:focus:ring-slate-800"
              onChange={(event) =>
                onSetStatusFilter(event.target.value as SuggestionStatus | "all")
              }
              value={statusFilter}
            >
              {statusFilters.map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </CardContent>
    </Card>
  );
}

function CreateSuggestionForm({
  disabled = false,
  errorMessage,
  isSubmitting = false,
  onSubmit,
  readOnlyMessage,
  terms,
  termsErrorMessage,
  termsLoading = false,
}: {
  disabled?: boolean;
  errorMessage?: string | null;
  isSubmitting?: boolean;
  onSubmit: (payload: SuggestionCreateRequest) => Promise<void> | void;
  readOnlyMessage?: string | null;
  terms: CanonicalTerm[];
  termsErrorMessage?: string | null;
  termsLoading?: boolean;
}) {
  const [suggestionType, setSuggestionType] = useState<SuggestionType>("alias");
  const [termSearch, setTermSearch] = useState("");
  const [selectedCanonicalValue, setSelectedCanonicalValue] = useState("");
  const [aliasValue, setAliasValue] = useState("");
  const [newCanonicalValue, setNewCanonicalValue] = useState("");
  const [newSlot, setNewSlot] = useState("");
  const [description, setDescription] = useState("");
  const [context, setContext] = useState("");

  const selectedTerm = useMemo(() => {
    return (
      terms.find((term) => term.canonical_value === selectedCanonicalValue) ??
      null
    );
  }, [selectedCanonicalValue, terms]);

  useEffect(() => {
    if (
      selectedCanonicalValue &&
      !terms.some((term) => term.canonical_value === selectedCanonicalValue)
    ) {
      setSelectedCanonicalValue("");
      setTermSearch("");
    }
  }, [selectedCanonicalValue, terms]);

  const filteredTerms = useMemo(() => {
    const normalizedSearch = termSearch.trim().toLowerCase();
    if (!normalizedSearch) {
      return terms.slice(0, 8);
    }
    return terms
      .filter(
        (term) =>
          term.canonical_value.toLowerCase().includes(normalizedSearch) ||
          term.slot.toLowerCase().includes(normalizedSearch) ||
          term.aliases.some((alias) =>
            alias.alias_value.toLowerCase().includes(normalizedSearch),
          ),
      )
      .slice(0, 8);
  }, [termSearch, terms]);

  const normalizedSuggestedAlias = aliasValue.trim().toLowerCase();
  const duplicateAlias = Boolean(
    selectedTerm &&
    normalizedSuggestedAlias &&
    selectedTerm.aliases.some(
      (alias) =>
        alias.normalized_alias === normalizedSuggestedAlias ||
        alias.alias_value.toLowerCase() === normalizedSuggestedAlias,
    ),
  );
  const normalizedNewCanonical = newCanonicalValue.trim().toLowerCase();
  const duplicateCanonical = Boolean(
    normalizedNewCanonical &&
    terms.some(
      (term) =>
        term.normalized_value === normalizedNewCanonical ||
        term.canonical_value.toLowerCase() === normalizedNewCanonical,
    ),
  );

  const canSubmitAlias =
    !disabled &&
    suggestionType === "alias" &&
    Boolean(selectedTerm) &&
    aliasValue.trim().length > 0 &&
    !duplicateAlias &&
    !isSubmitting;
  const canSubmitCanonical =
    !disabled &&
    suggestionType === "canonical_term" &&
    newCanonicalValue.trim().length > 0 &&
    newSlot.trim().length > 0 &&
    !duplicateCanonical &&
    !isSubmitting;
  const canSubmit = canSubmitAlias || canSubmitCanonical;

  function handleSelectTerm(term: CanonicalTerm) {
    setSelectedCanonicalValue(term.canonical_value);
    setTermSearch(term.canonical_value);
  }

  function handleSetSuggestionType(nextType: SuggestionType) {
    setSuggestionType(nextType);
    setAliasValue("");
    setNewCanonicalValue("");
    setNewSlot("");
    setDescription("");
    setContext("");
    if (nextType === "canonical_term") {
      setSelectedCanonicalValue("");
      setTermSearch("");
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }

    try {
      if (suggestionType === "alias") {
        if (!selectedTerm) {
          return;
        }
        await onSubmit({
          suggestion_type: "alias",
          canonical_value: selectedTerm.canonical_value,
          alias_value: aliasValue.trim(),
          slot: selectedTerm.slot,
          confidence: 1,
          source: "manual",
          context: context.trim() || null,
        });
        setAliasValue("");
        setContext("");
        return;
      }

      await onSubmit({
        suggestion_type: "canonical_term",
        canonical_value: newCanonicalValue.trim(),
        alias_value: null,
        slot: newSlot.trim(),
        description: description.trim() || null,
        confidence: 1,
        source: "manual",
        context: context.trim() || null,
      });
      setNewCanonicalValue("");
      setNewSlot("");
      setDescription("");
      setContext("");
    } catch {
      // Parent mutation owns user-facing error rendering.
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Create suggestion</CardTitle>
        <CardDescription>
          Propose an alias for an existing canonical term or suggest a new
          canonical term for moderator review.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {readOnlyMessage ? (
          <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
            {readOnlyMessage}
          </div>
        ) : null}
        {termsErrorMessage ? (
          <div className="mb-4">
            <InlineError message={termsErrorMessage} />
          </div>
        ) : null}
        <form className="space-y-4" onSubmit={handleSubmit}>
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium text-slate-700 dark:text-slate-200">
              Suggestion type
            </legend>
            <div className="grid gap-2 sm:grid-cols-2">
              <button
                className={suggestionTypeButtonClass(
                  suggestionType === "alias",
                )}
                disabled={disabled || isSubmitting}
                onClick={() => handleSetSuggestionType("alias")}
                type="button"
              >
                <span className="block text-sm font-semibold">
                  Alias for existing term
                </span>
                <span className="mt-1 block text-xs opacity-75">
                  Propose slang, abbreviation, or jargon.
                </span>
              </button>
              <button
                className={suggestionTypeButtonClass(
                  suggestionType === "canonical_term",
                )}
                disabled={disabled || isSubmitting}
                onClick={() => handleSetSuggestionType("canonical_term")}
                type="button"
              >
                <span className="block text-sm font-semibold">
                  New canonical term
                </span>
                <span className="mt-1 block text-xs opacity-75">
                  Propose a new approved term.
                </span>
              </button>
            </div>
          </fieldset>

          {suggestionType === "alias" ? (
            <div className="space-y-4">
              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-2 md:col-span-2">
                  <label className="space-y-1.5">
                    <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
                      Canonical term
                    </span>
                    <Input
                      disabled={disabled || isSubmitting || termsLoading}
                      onChange={(event) => {
                        setTermSearch(event.target.value);
                        if (
                          event.target.value !== selectedTerm?.canonical_value
                        ) {
                          setSelectedCanonicalValue("");
                        }
                      }}
                      placeholder="Search canonical terms or existing aliases..."
                      value={termSearch}
                    />
                  </label>
                  {termsLoading ? (
                    <p className="text-sm text-slate-500 dark:text-slate-400">
                      Loading canonical terms...
                    </p>
                  ) : null}
                  {!termsLoading && terms.length === 0 ? (
                    <p className="rounded-lg border border-dashed border-slate-200 px-3 py-2 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
                      No canonical terms found. Suggest a new canonical term
                      instead.
                    </p>
                  ) : null}
                  {!termsLoading && filteredTerms.length > 0 ? (
                    <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                      {filteredTerms.map((term) => (
                        <button
                          className={`rounded-xl border px-3 py-2 text-left transition-colors ${selectedCanonicalValue === term.canonical_value ? "border-slate-950 bg-slate-950 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-950" : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200 dark:hover:bg-slate-900"}`}
                          disabled={disabled || isSubmitting}
                          key={term.id}
                          onClick={() => handleSelectTerm(term)}
                          type="button"
                        >
                          <span className="block text-sm font-semibold">
                            {term.canonical_value}
                          </span>
                          <span className="mt-1 block text-xs opacity-75">
                            {term.slot} · {term.aliases.length} aliases
                          </span>
                        </button>
                      ))}
                    </div>
                  ) : null}
                </div>

                <label className="space-y-1.5">
                  <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
                    Suggested alias
                  </span>
                  <Input
                    disabled={disabled || isSubmitting || !selectedTerm}
                    onChange={(event) => setAliasValue(event.target.value)}
                    placeholder="kube"
                    value={aliasValue}
                  />
                </label>
                <label className="space-y-1.5">
                  <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
                    Slot
                  </span>
                  <Input
                    disabled
                    placeholder="Select a canonical term"
                    readOnly
                    value={selectedTerm?.slot ?? ""}
                  />
                </label>
              </div>

              {selectedTerm ? (
                <div className="rounded-xl border border-slate-100 p-4 dark:border-slate-800">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="text-sm font-semibold text-slate-950 dark:text-slate-50">
                        Selected canonical term
                      </div>
                      <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                        {selectedTerm.canonical_value} · {selectedTerm.slot}
                      </div>
                    </div>
                    <Badge>{selectedTerm.status}</Badge>
                  </div>
                  <div className="mt-4">
                    <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                      Existing aliases
                    </div>
                    {selectedTerm.aliases.length > 0 ? (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {selectedTerm.aliases.map((alias) => (
                          <Badge
                            className="bg-slate-50 text-slate-700 dark:bg-slate-900 dark:text-slate-200"
                            key={alias.id}
                          >
                            {alias.alias_value}
                          </Badge>
                        ))}
                      </div>
                    ) : (
                      <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                        No aliases yet.
                      </p>
                    )}
                  </div>
                </div>
              ) : null}

              {duplicateAlias ? (
                <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
                  This alias already exists for {selectedTerm?.canonical_value}.
                  Choose a different alias or review the active terminology
                  first.
                </div>
              ) : null}
            </div>
          ) : (
            <div className="space-y-4">
              <div className="grid gap-3 md:grid-cols-2">
                <label className="space-y-1.5">
                  <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
                    New canonical term
                  </span>
                  <Input
                    disabled={disabled || isSubmitting}
                    onChange={(event) =>
                      setNewCanonicalValue(event.target.value)
                    }
                    placeholder="vector database"
                    value={newCanonicalValue}
                  />
                </label>
                <label className="space-y-1.5">
                  <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
                    Slot
                  </span>
                  <Input
                    disabled={disabled || isSubmitting}
                    onChange={(event) => setNewSlot(event.target.value)}
                    placeholder="TOOL"
                    value={newSlot}
                  />
                </label>
              </div>
              <label className="block space-y-1.5">
                <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
                  Description
                </span>
                <Input
                  disabled={disabled || isSubmitting}
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder="Optional note for moderators and future snapshots"
                  value={description}
                />
              </label>
              {duplicateCanonical ? (
                <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
                  This canonical term already exists. Switch to alias suggestion
                  if you want to propose slang or abbreviations for it.
                </div>
              ) : null}
            </div>
          )}

          <label className="block space-y-1.5">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
              Context
            </span>
            <textarea
              className="min-h-24 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-slate-400 focus:ring-2 focus:ring-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:border-slate-500 dark:focus:ring-slate-800"
              disabled={disabled || isSubmitting}
              onChange={(event) => setContext(event.target.value)}
              placeholder="Why should this suggestion be reviewed? Add source snippet, ticket, or discovery context."
              value={context}
            />
          </label>
          {errorMessage ? <InlineError message={errorMessage} /> : null}
          <Button disabled={!canSubmit} type="submit">
            {isSubmitting ? "Creating..." : "Create suggestion"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function suggestionTypeButtonClass(isActive: boolean) {
  return `rounded-xl border px-3 py-2 text-left transition-colors ${isActive ? "border-slate-950 bg-slate-950 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-950" : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200 dark:hover:bg-slate-900"}`;
}

function SuggestionsTable({
  isLoading,
  loadErrorMessage,
  onSelectSuggestion,
  selectedSuggestionId,
  suggestions,
}: {
  isLoading: boolean;
  loadErrorMessage?: string | null;
  onSelectSuggestion: (suggestion: GovernanceSuggestion) => void;
  selectedSuggestionId: number | null;
  suggestions: GovernanceSuggestion[];
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Review queue</CardTitle>
        <CardDescription>
          Pending, approved, and rejected alias/canonical term suggestions for
          the selected profile.
        </CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        {loadErrorMessage ? (
          <div className="p-5">
            <InlineError message={loadErrorMessage} />
          </div>
        ) : null}
        {isLoading ? (
          <p className="p-5 text-sm text-slate-500 dark:text-slate-400">
            Loading suggestions...
          </p>
        ) : null}
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-950 dark:text-slate-400">
              <tr>
                <th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">
                  Type
                </th>
                <th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">
                  Suggestion
                </th>
                <th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">
                  Slot
                </th>
                <th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">
                  Status
                </th>
                <th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">
                  Source
                </th>
                <th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">
                  Evidence
                </th>
              </tr>
            </thead>
            <tbody>
              {suggestions.length === 0 ? (
                <tr>
                  <td
                    className="px-5 py-8 text-center text-sm text-slate-500 dark:text-slate-400"
                    colSpan={6}
                  >
                    No suggestions found for this filter.
                  </td>
                </tr>
              ) : (
                suggestions.map((suggestion) => (
                  <tr
                    className={`cursor-pointer transition-colors ${selectedSuggestionId === suggestion.id ? "bg-slate-100 dark:bg-slate-800/70" : "hover:bg-slate-50 dark:hover:bg-slate-900"}`}
                    key={suggestion.id}
                    onClick={() => onSelectSuggestion(suggestion)}
                  >
                    <td className="border-b border-slate-100 px-5 py-4 dark:border-slate-800">
                      <Badge>
                        {suggestionTypeLabel(suggestion.suggestion_type)}
                      </Badge>
                    </td>
                    <td className="border-b border-slate-100 px-5 py-4 dark:border-slate-800">
                      <div className="font-medium text-slate-950 dark:text-slate-50">
                        {suggestionDisplayValue(suggestion)}
                      </div>
                      <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                        {suggestionSubtitle(suggestion)}
                      </div>
                    </td>
                    <td className="border-b border-slate-100 px-5 py-4 text-slate-600 dark:border-slate-800 dark:text-slate-300">
                      {suggestion.slot}
                    </td>
                    <td className="border-b border-slate-100 px-5 py-4 dark:border-slate-800">
                      <StatusBadge status={suggestion.status} />
                    </td>
                    <td className="border-b border-slate-100 px-5 py-4 text-slate-600 dark:border-slate-800 dark:text-slate-300">
                      {suggestion.source}
                    </td>
                    <td className="border-b border-slate-100 px-5 py-4 dark:border-slate-800">
                      {suggestion.evidence_snapshot ? (
                        <Badge className="bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200">
                          Evidence
                        </Badge>
                      ) : (
                        <span className="text-xs text-slate-400">—</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function SuggestionDetailsPanel({
  bindings,
  bindingsErrorMessage,
  bindingsLoading = false,
  canReview,
  evidenceErrorMessage,
  isApproving,
  isRefreshingEvidence = false,
  isRejecting,
  onApprove,
  onRefreshEvidence,
  onReject,
  reviewErrorMessage,
  suggestion,
}: {
  bindings: ElasticsearchBinding[];
  bindingsErrorMessage?: string | null;
  bindingsLoading?: boolean;
  canReview: boolean;
  evidenceErrorMessage?: string | null;
  isApproving?: boolean;
  isRefreshingEvidence?: boolean;
  isRejecting?: boolean;
  onApprove: (
    suggestion: GovernanceSuggestion,
    payload: SuggestionReviewRequest,
  ) => Promise<void> | void;
  onRefreshEvidence: (
    suggestion: GovernanceSuggestion,
    bindingId: number,
    query: string,
    maxDocuments: number,
  ) => Promise<void> | void;
  onReject: (
    suggestion: GovernanceSuggestion,
    payload: SuggestionReviewRequest,
  ) => Promise<void> | void;
  reviewErrorMessage?: string | null;
  suggestion: GovernanceSuggestion | null;
}) {
  const [reviewComment, setReviewComment] = useState("");
  const [selectedBindingId, setSelectedBindingId] = useState<number | null>(
    null,
  );
  const [evidenceQuery, setEvidenceQuery] = useState("");
  const [maxDocuments, setMaxDocuments] = useState(5);

  const defaultEvidenceQuery = suggestion
    ? suggestion.alias_value || suggestion.canonical_value
    : "";

  useEffect(() => {
    setReviewComment("");
    setEvidenceQuery(defaultEvidenceQuery);
    setMaxDocuments(5);
  }, [defaultEvidenceQuery, suggestion?.id]);

  useEffect(() => {
    if (!suggestion) {
      setSelectedBindingId(null);
      return;
    }
    if (bindings.length === 0) {
      setSelectedBindingId(null);
      return;
    }
    if (
      !selectedBindingId ||
      !bindings.some((binding) => binding.id === selectedBindingId)
    ) {
      const snapshotBindingId = suggestion.evidence_snapshot?.binding_id;
      const snapshotBinding = snapshotBindingId
        ? bindings.find((binding) => binding.id === snapshotBindingId)
        : null;
      setSelectedBindingId(snapshotBinding?.id ?? bindings[0].id);
    }
  }, [bindings, selectedBindingId, suggestion]);

  if (!suggestion) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Suggestion details</CardTitle>
          <CardDescription>
            Select a suggestion to inspect context and review actions.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            No suggestion selected.
          </p>
        </CardContent>
      </Card>
    );
  }

  const effectiveEvidenceQuery =
    evidenceQuery.trim() || defaultEvidenceQuery.trim();
  const canReviewPending = canReview && suggestion.status === "pending";
  const canCheckEvidence =
    suggestion.status === "pending" &&
    bindings.length > 0 &&
    Boolean(selectedBindingId) &&
    effectiveEvidenceQuery.length > 0 &&
    !isRefreshingEvidence;

  async function handleApprove() {
    if (!suggestion || !canReviewPending) return;
    await onApprove(suggestion, {
      review_comment: reviewComment.trim() || null,
    });
  }

  async function handleReject() {
    if (!suggestion || !canReviewPending) return;
    await onReject(suggestion, {
      review_comment: reviewComment.trim() || null,
    });
  }

  async function handleRefreshEvidence() {
    if (!suggestion || !selectedBindingId || !canCheckEvidence) {
      return;
    }
    await onRefreshEvidence(
      suggestion,
      selectedBindingId,
      effectiveEvidenceQuery,
      maxDocuments,
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>{suggestionDisplayValue(suggestion)}</CardTitle>
            <CardDescription>{suggestionSubtitle(suggestion)}</CardDescription>
          </div>
          <StatusBadge status={suggestion.status} />
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <dl className="grid gap-3 text-sm">
          <DetailRow
            label="Type"
            value={suggestionTypeLabel(suggestion.suggestion_type)}
          />
          <DetailRow
            label="Canonical term"
            value={suggestion.canonical_value}
          />
          {suggestion.suggestion_type === "alias" ? (
            <DetailRow
              label="Suggested alias"
              value={suggestion.alias_value ?? "—"}
            />
          ) : null}
          <DetailRow label="Slot" value={suggestion.slot} />
          {suggestion.description ? (
            <DetailRow label="Description" value={suggestion.description} />
          ) : null}
          <DetailRow label="Source" value={suggestion.source} />
          <DetailRow
            label="Confidence"
            value={formatConfidence(suggestion.confidence)}
          />
          <DetailRow
            label="Created by"
            value={suggestion.created_by ?? "Unknown"}
          />
          {suggestion.reviewed_by ? (
            <DetailRow label="Reviewed by" value={suggestion.reviewed_by} />
          ) : null}
          {suggestion.review_comment ? (
            <DetailRow
              label="Review comment"
              value={suggestion.review_comment}
            />
          ) : null}
          {suggestion.evidence_checked_by ? (
            <DetailRow
              label="Evidence checked by"
              value={suggestion.evidence_checked_by}
            />
          ) : null}
        </dl>

        <div className="rounded-xl border border-slate-100 p-4 dark:border-slate-800">
          <div className="text-sm font-semibold text-slate-950 dark:text-slate-50">
            Context
          </div>
          <p className="mt-2 whitespace-pre-wrap text-sm text-slate-600 dark:text-slate-300">
            {suggestion.context || "No context provided."}
          </p>
        </div>

        <div className="rounded-xl border border-slate-100 p-4 dark:border-slate-800">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-slate-950 dark:text-slate-50">
                Evidence from Elasticsearch
              </div>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                Save bounded snippets from the selected binding so reviewers can
                approve with document evidence.
              </p>
            </div>
            {suggestion.evidence_snapshot ? (
              <Badge className="bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200">
                Snapshot saved
              </Badge>
            ) : (
              <Badge className="bg-slate-50 text-slate-600 dark:bg-slate-900 dark:text-slate-300">
                No snapshot
              </Badge>
            )}
          </div>

          <div className="mt-4 space-y-3">
            {bindingsErrorMessage ? (
              <InlineError message={bindingsErrorMessage} />
            ) : null}
            {bindingsLoading ? (
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Loading Elasticsearch bindings...
              </p>
            ) : null}
            {!bindingsLoading && bindings.length === 0 ? (
              <div className="rounded-lg border border-dashed border-slate-200 px-3 py-2 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
                No Elasticsearch bindings are configured for this profile. Add
                one in Integrations before checking evidence.
              </div>
            ) : null}

            {bindings.length > 0 && suggestion.status === "pending" ? (
              <div className="space-y-3 rounded-lg bg-slate-50 p-3 dark:bg-slate-950">
                <label className="block space-y-1.5">
                  <span className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                    Binding
                  </span>
                  <select
                    className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100 disabled:cursor-not-allowed disabled:bg-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:disabled:bg-slate-900 dark:focus:border-slate-500 dark:focus:ring-slate-800"
                    disabled={isRefreshingEvidence}
                    onChange={(event) =>
                      setSelectedBindingId(Number(event.target.value))
                    }
                    value={selectedBindingId ?? ""}
                  >
                    {bindings.map((binding) => (
                      <option key={binding.id} value={binding.id}>
                        {binding.name} · {binding.index_name}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_110px]">
                  <label className="block space-y-1.5">
                    <span className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                      Evidence query
                    </span>
                    <Input
                      disabled={isRefreshingEvidence}
                      onChange={(event) => setEvidenceQuery(event.target.value)}
                      value={evidenceQuery}
                    />
                  </label>
                  <label className="block space-y-1.5">
                    <span className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                      Max docs
                    </span>
                    <Input
                      disabled={isRefreshingEvidence}
                      max={10}
                      min={1}
                      onChange={(event) =>
                        setMaxDocuments(Number(event.target.value) || 1)
                      }
                      type="number"
                      value={String(maxDocuments)}
                    />
                  </label>
                </div>
                <Button
                  disabled={!canCheckEvidence}
                  onClick={handleRefreshEvidence}
                  type="button"
                  variant="secondary"
                >
                  <Search className="mr-2 h-4 w-4" />
                  {isRefreshingEvidence
                    ? "Checking evidence..."
                    : suggestion.evidence_snapshot
                      ? "Refresh evidence"
                      : "Check evidence"}
                </Button>
              </div>
            ) : null}

            {suggestion.status !== "pending" &&
            !suggestion.evidence_snapshot ? (
              <p className="text-sm text-slate-500 dark:text-slate-400">
                No evidence snapshot was saved before review.
              </p>
            ) : null}
            {evidenceErrorMessage ? (
              <InlineError message={evidenceErrorMessage} />
            ) : null}
            {suggestion.evidence_snapshot ? (
              <SuggestionEvidenceSnapshotPanel
                snapshot={suggestion.evidence_snapshot}
              />
            ) : null}
          </div>
        </div>

        {!canReview ? (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
            Contributors can create suggestions, but only admins and moderators
            can approve or reject them.
          </div>
        ) : null}

        {suggestion.status !== "pending" ? (
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300">
            This suggestion has already been reviewed.
          </div>
        ) : null}

        {reviewErrorMessage ? (
          <InlineError message={reviewErrorMessage} />
        ) : null}

        <label className="block space-y-1.5">
          <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
            Review comment
          </span>
          <textarea
            className="min-h-24 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-slate-400 focus:ring-2 focus:ring-slate-100 disabled:cursor-not-allowed disabled:bg-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-500 dark:disabled:bg-slate-900 dark:focus:border-slate-500 dark:focus:ring-slate-800"
            disabled={!canReviewPending || isApproving || isRejecting}
            onChange={(event) => setReviewComment(event.target.value)}
            placeholder="Optional reason for approve/reject."
            value={reviewComment}
          />
        </label>

        <div className="flex flex-wrap gap-2">
          <Button
            disabled={!canReviewPending || isApproving || isRejecting}
            onClick={handleApprove}
            type="button"
          >
            <CheckCircle className="mr-2 h-4 w-4" />
            {isApproving ? "Approving..." : "Approve suggestion"}
          </Button>
          <Button
            disabled={!canReviewPending || isApproving || isRejecting}
            onClick={handleReject}
            type="button"
            variant="secondary"
          >
            <XCircle className="mr-2 h-4 w-4" />
            {isRejecting ? "Rejecting..." : "Reject suggestion"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function SuggestionEvidenceSnapshotPanel({
  snapshot,
}: {
  snapshot: SuggestionEvidenceSnapshot;
}) {
  return (
    <div className="space-y-3 rounded-lg border border-slate-200 p-3 dark:border-slate-800">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-sm font-medium text-slate-950 dark:text-slate-50">
            {snapshot.query}
          </div>
          <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            {snapshot.binding_name} · {snapshot.index_name} · max{" "}
            {snapshot.max_documents} docs
          </div>
        </div>
        <Badge>{snapshot.documents.length} snippets</Badge>
      </div>
      {snapshot.warnings.length > 0 ? (
        <div className="space-y-1">
          {snapshot.warnings.map((warning) => (
            <div
              className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200"
              key={warning}
            >
              {warning}
            </div>
          ))}
        </div>
      ) : null}
      <EvidenceDocumentsList documents={snapshot.documents} />
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-1 rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-950">
      <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {label}
      </dt>
      <dd className="text-sm font-medium text-slate-900 dark:text-slate-100">
        {value}
      </dd>
    </div>
  );
}

function StatusBadge({ status }: { status: SuggestionStatus }) {
  const className =
    status === "approved"
      ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200"
      : status === "rejected"
        ? "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-200"
        : "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-200";
  return <Badge className={className}>{status}</Badge>;
}

function InlineError({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200">
      {message}
    </div>
  );
}

function errorMessage(error: unknown) {
  if (!error) {
    return null;
  }
  return error instanceof Error
    ? error.message
    : "Request failed. Check the governance API and try again.";
}

function formatConfidence(confidence: number) {
  return confidence.toFixed(2);
}

function suggestionTypeLabel(type: SuggestionType) {
  return type === "canonical_term" ? "Canonical term" : "Alias";
}

function suggestionDisplayValue(suggestion: GovernanceSuggestion) {
  return suggestion.suggestion_type === "canonical_term"
    ? suggestion.canonical_value
    : (suggestion.alias_value ?? "—");
}

function suggestionSubtitle(suggestion: GovernanceSuggestion) {
  return suggestion.suggestion_type === "canonical_term"
    ? "Proposed new canonical term"
    : `Proposed alias for ${suggestion.canonical_value}`;
}

function upsertSuggestion(
  queryClient: ReturnType<typeof useQueryClient>,
  profileName: string | null,
  statusFilter: SuggestionStatus | "all",
  suggestion: GovernanceSuggestion,
) {
  queryClient.setQueryData<GovernanceSuggestion[]>(
    ["suggestions", profileName, statusFilter],
    (currentSuggestions = []) => {
      const shouldStayVisible =
        statusFilter === "all" || suggestion.status === statusFilter;
      const withoutSuggestion = currentSuggestions.filter(
        (currentSuggestion) => currentSuggestion.id !== suggestion.id,
      );
      if (!shouldStayVisible) {
        return withoutSuggestion;
      }
      return [suggestion, ...withoutSuggestion].sort(sortSuggestions);
    },
  );
}

function syncReviewedSuggestion(
  queryClient: ReturnType<typeof useQueryClient>,
  profileName: string | null,
  currentStatusFilter: SuggestionStatus | "all",
  suggestion: GovernanceSuggestion,
) {
  upsertSuggestion(queryClient, profileName, "all", suggestion);
  upsertSuggestion(queryClient, profileName, suggestion.status, suggestion);

  if (
    currentStatusFilter !== "all" &&
    currentStatusFilter !== suggestion.status
  ) {
    removeSuggestion(
      queryClient,
      profileName,
      currentStatusFilter,
      suggestion.id,
    );
  }
}

function removeSuggestion(
  queryClient: ReturnType<typeof useQueryClient>,
  profileName: string | null,
  statusFilter: SuggestionStatus | "all",
  suggestionId: number,
) {
  queryClient.setQueryData<GovernanceSuggestion[]>(
    ["suggestions", profileName, statusFilter],
    (currentSuggestions = []) =>
      currentSuggestions.filter((suggestion) => suggestion.id !== suggestionId),
  );
}

function sortSuggestions(
  left: GovernanceSuggestion,
  right: GovernanceSuggestion,
) {
  if (left.status !== right.status) {
    return left.status.localeCompare(right.status);
  }
  return right.id - left.id;
}
