import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle, XCircle } from "lucide-react";
import { type FormEvent, useEffect, useMemo, useState } from "react";

import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { approveSuggestion, createSuggestion, listProfiles, listSuggestions, rejectSuggestion } from "../lib/api";
import { permissionsForUser } from "../permissions";
import type {
  AuthUser,
  GovernanceSuggestion,
  Profile,
  SuggestionCreateRequest,
  SuggestionReviewRequest,
  SuggestionSource,
  SuggestionStatus,
} from "../types";

const statusFilters: Array<SuggestionStatus | "all"> = ["pending", "approved", "rejected", "all"];
const suggestionSources: SuggestionSource[] = ["manual", "discovery", "import"];

export function SuggestionsPage({ currentUser }: { currentUser: AuthUser }) {
  const permissions = permissionsForUser(currentUser);
  const queryClient = useQueryClient();
  const profilesQuery = useQuery({
    queryKey: ["profiles"],
    queryFn: listProfiles,
  });
  const [selectedProfile, setSelectedProfile] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<SuggestionStatus | "all">("pending");
  const [selectedSuggestionId, setSelectedSuggestionId] = useState<number | null>(null);

  useEffect(() => {
    if (!profilesQuery.data || profilesQuery.data.length === 0) {
      setSelectedProfile(null);
      setSelectedSuggestionId(null);
      return;
    }

    if (!selectedProfile || !profilesQuery.data.some((profile) => profile.name === selectedProfile)) {
      setSelectedProfile(profilesQuery.data[0].name);
      setSelectedSuggestionId(null);
    }
  }, [profilesQuery.data, selectedProfile]);

  const suggestionsQuery = useQuery({
    queryKey: ["suggestions", selectedProfile, statusFilter],
    queryFn: () => listSuggestions(selectedProfile ?? "", statusFilter),
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
    if (!selectedSuggestionId || !suggestionsQuery.data.some((suggestion) => suggestion.id === selectedSuggestionId)) {
      setSelectedSuggestionId(suggestionsQuery.data[0].id);
    }
  }, [selectedSuggestionId, suggestionsQuery.data]);

  const selectedSuggestion = useMemo(() => {
    if (!suggestionsQuery.data || !selectedSuggestionId) {
      return null;
    }
    return suggestionsQuery.data.find((suggestion) => suggestion.id === selectedSuggestionId) ?? null;
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
      setSelectedSuggestionId(suggestion.id);
      upsertSuggestion(queryClient, selectedProfile, statusFilter, suggestion);
      upsertSuggestion(queryClient, selectedProfile, "pending", suggestion);
      void queryClient.invalidateQueries({ queryKey: ["suggestions", selectedProfile] });
    },
  });

  const approveSuggestionMutation = useMutation({
    mutationFn: ({ suggestion, payload }: { suggestion: GovernanceSuggestion; payload: SuggestionReviewRequest }) => {
      if (!selectedProfile) {
        throw new Error("Select a profile before approving a suggestion.");
      }
      return approveSuggestion(selectedProfile, suggestion.id, payload);
    },
    onSuccess: (suggestion) => {
      setStatusFilter("approved");
      setSelectedSuggestionId(suggestion.id);
      upsertSuggestion(queryClient, selectedProfile, statusFilter, suggestion);
      upsertSuggestion(queryClient, selectedProfile, "approved", suggestion);
      void queryClient.invalidateQueries({ queryKey: ["suggestions", selectedProfile] });
      void queryClient.invalidateQueries({ queryKey: ["terms", selectedProfile] });
    },
  });

  const rejectSuggestionMutation = useMutation({
    mutationFn: ({ suggestion, payload }: { suggestion: GovernanceSuggestion; payload: SuggestionReviewRequest }) => {
      if (!selectedProfile) {
        throw new Error("Select a profile before rejecting a suggestion.");
      }
      return rejectSuggestion(selectedProfile, suggestion.id, payload);
    },
    onSuccess: (suggestion) => {
      setStatusFilter("rejected");
      setSelectedSuggestionId(suggestion.id);
      upsertSuggestion(queryClient, selectedProfile, statusFilter, suggestion);
      upsertSuggestion(queryClient, selectedProfile, "rejected", suggestion);
      void queryClient.invalidateQueries({ queryKey: ["suggestions", selectedProfile] });
    },
  });

  async function handleCreateSuggestion(payload: SuggestionCreateRequest) {
    await createSuggestionMutation.mutateAsync(payload);
  }

  async function handleApproveSuggestion(suggestion: GovernanceSuggestion, payload: SuggestionReviewRequest) {
    await approveSuggestionMutation.mutateAsync({ suggestion, payload });
  }

  async function handleRejectSuggestion(suggestion: GovernanceSuggestion, payload: SuggestionReviewRequest) {
    await rejectSuggestionMutation.mutateAsync({ suggestion, payload });
  }

  return (
    <div className="space-y-6">
      <section className="grid gap-4 md:grid-cols-3">
        <StatCard description="Terminology namespace currently under review." title="Profile" value={selectedProfile ?? "None"} />
        <StatCard description="Suggestions visible under the current filter." title="Suggestions" value={String(suggestionsQuery.data?.length ?? 0)} />
        <Card>
          <CardHeader>
            <CardTitle>Review model</CardTitle>
            <CardDescription>Contributor proposes, moderator approves.</CardDescription>
          </CardHeader>
          <CardContent>
            <Badge>Suggestion → Approval → Alias</Badge>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="space-y-6">
          <SuggestionsToolbar
            isLoading={profilesQuery.isLoading}
            loadErrorMessage={profilesQuery.isError ? profilesQuery.error.message : null}
            onSelectProfile={(profileName) => {
              setSelectedProfile(profileName);
              setSelectedSuggestionId(null);
              createSuggestionMutation.reset();
              approveSuggestionMutation.reset();
              rejectSuggestionMutation.reset();
            }}
            onSetStatusFilter={(status) => {
              setStatusFilter(status);
              setSelectedSuggestionId(null);
            }}
            profiles={profilesQuery.data ?? []}
            selectedProfile={selectedProfile}
            statusFilter={statusFilter}
          />

          <CreateSuggestionForm
            disabled={!selectedProfile || !permissions.canCreateSuggestions}
            errorMessage={errorMessage(createSuggestionMutation.error)}
            isSubmitting={createSuggestionMutation.isPending}
            onSubmit={handleCreateSuggestion}
            readOnlyMessage={permissions.canCreateSuggestions ? null : "Your role can inspect suggestions, but cannot create new proposals."}
          />

          <SuggestionsTable
            isLoading={suggestionsQuery.isLoading && Boolean(selectedProfile)}
            loadErrorMessage={suggestionsQuery.isError ? suggestionsQuery.error.message : null}
            onSelectSuggestion={(suggestion) => {
              setSelectedSuggestionId(suggestion.id);
              approveSuggestionMutation.reset();
              rejectSuggestionMutation.reset();
            }}
            selectedSuggestionId={selectedSuggestionId}
            suggestions={suggestionsQuery.data ?? []}
          />
        </div>

        <SuggestionDetailsPanel
          canReview={permissions.canReviewSuggestions}
          isApproving={approveSuggestionMutation.isPending}
          isRejecting={rejectSuggestionMutation.isPending}
          onApprove={handleApproveSuggestion}
          onReject={handleRejectSuggestion}
          reviewErrorMessage={errorMessage(approveSuggestionMutation.error) ?? errorMessage(rejectSuggestionMutation.error)}
          suggestion={selectedSuggestion}
        />
      </section>
    </div>
  );
}

function StatCard({ description, title, value }: { description: string; title: string; value: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="text-3xl font-semibold">{value}</div>
      </CardContent>
    </Card>
  );
}

function SuggestionsToolbar({
  isLoading,
  loadErrorMessage,
  onSelectProfile,
  onSetStatusFilter,
  profiles,
  selectedProfile,
  statusFilter,
}: {
  isLoading: boolean;
  loadErrorMessage?: string | null;
  onSelectProfile: (profileName: string) => void;
  onSetStatusFilter: (status: SuggestionStatus | "all") => void;
  profiles: Profile[];
  selectedProfile: string | null;
  statusFilter: SuggestionStatus | "all";
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Suggestions queue</CardTitle>
        <CardDescription>Review proposed aliases before they mutate active runtime terminology.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {loadErrorMessage ? <InlineError message={loadErrorMessage} /> : null}
        {isLoading ? <p className="text-sm text-slate-500 dark:text-slate-400">Loading profiles...</p> : null}
        {profiles.length > 0 ? (
          <div className="space-y-2">
            <div className="text-sm font-medium text-slate-700 dark:text-slate-200">Profile</div>
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
            No profiles found. Create a terminology profile before collecting alias suggestions.
          </p>
        )}

        <label className="block space-y-1.5">
          <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Suggestion status</span>
          <select
            className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:focus:border-slate-500 dark:focus:ring-slate-800"
            onChange={(event) => onSetStatusFilter(event.target.value as SuggestionStatus | "all")}
            value={statusFilter}
          >
            {statusFilters.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </select>
        </label>
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
}: {
  disabled?: boolean;
  errorMessage?: string | null;
  isSubmitting?: boolean;
  onSubmit: (payload: SuggestionCreateRequest) => Promise<void> | void;
  readOnlyMessage?: string | null;
}) {
  const [canonicalValue, setCanonicalValue] = useState("");
  const [aliasValue, setAliasValue] = useState("");
  const [slot, setSlot] = useState("TOOL");
  const [confidence, setConfidence] = useState("1");
  const [source, setSource] = useState<SuggestionSource>("manual");
  const [context, setContext] = useState("");
  const canSubmit = !disabled && canonicalValue.trim().length > 0 && aliasValue.trim().length > 0 && slot.trim().length > 0 && !isSubmitting;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }

    try {
      await onSubmit({
        canonical_value: canonicalValue.trim(),
        alias_value: aliasValue.trim(),
        slot: slot.trim(),
        confidence: normalizeConfidence(confidence),
        source,
        context: context.trim() || null,
      });
      setAliasValue("");
      setContext("");
      setConfidence("1");
    } catch {
      // Parent mutation owns user-facing error rendering.
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Create suggestion</CardTitle>
        <CardDescription>Propose an alias for moderator review without changing active terminology.</CardDescription>
      </CardHeader>
      <CardContent>
        {readOnlyMessage ? (
          <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
            {readOnlyMessage}
          </div>
        ) : null}
        <form className="space-y-3" onSubmit={handleSubmit}>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Canonical term</span>
              <Input disabled={disabled || isSubmitting} onChange={(event) => setCanonicalValue(event.target.value)} placeholder="kubernetes" value={canonicalValue} />
            </label>
            <label className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Suggested alias</span>
              <Input disabled={disabled || isSubmitting} onChange={(event) => setAliasValue(event.target.value)} placeholder="kube" value={aliasValue} />
            </label>
            <label className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Slot</span>
              <Input disabled={disabled || isSubmitting} onChange={(event) => setSlot(event.target.value)} placeholder="TOOL" value={slot} />
            </label>
            <label className="space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Confidence</span>
              <Input disabled={disabled || isSubmitting} max="1" min="0" onChange={(event) => setConfidence(event.target.value)} step="0.01" type="number" value={confidence} />
            </label>
          </div>
          <label className="block space-y-1.5">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Source</span>
            <select
              className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:focus:border-slate-500 dark:focus:ring-slate-800"
              disabled={disabled || isSubmitting}
              onChange={(event) => setSource(event.target.value as SuggestionSource)}
              value={source}
            >
              {suggestionSources.map((sourceOption) => (
                <option key={sourceOption} value={sourceOption}>
                  {sourceOption}
                </option>
              ))}
            </select>
          </label>
          <label className="block space-y-1.5">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Context</span>
            <textarea
              className="min-h-24 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-slate-400 focus:ring-2 focus:ring-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:border-slate-500 dark:focus:ring-slate-800"
              disabled={disabled || isSubmitting}
              onChange={(event) => setContext(event.target.value)}
              placeholder="Why should this alias be reviewed? Add source snippet, ticket, or discovery context."
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
        <CardDescription>Pending, approved, and rejected suggestions for the selected profile.</CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        {loadErrorMessage ? <div className="p-5"><InlineError message={loadErrorMessage} /></div> : null}
        {isLoading ? <p className="p-5 text-sm text-slate-500 dark:text-slate-400">Loading suggestions...</p> : null}
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-950 dark:text-slate-400">
              <tr>
                <th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">Alias</th>
                <th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">Canonical</th>
                <th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">Status</th>
                <th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">Source</th>
                <th className="border-b border-slate-200 px-5 py-3 font-semibold dark:border-slate-800">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {suggestions.length === 0 ? (
                <tr>
                  <td className="px-5 py-8 text-center text-sm text-slate-500 dark:text-slate-400" colSpan={5}>
                    No suggestions found for this filter.
                  </td>
                </tr>
              ) : (
                suggestions.map((suggestion) => (
                  <tr
                    className={`cursor-pointer transition-colors ${
                      selectedSuggestionId === suggestion.id
                        ? "bg-slate-100 dark:bg-slate-800/70"
                        : "hover:bg-slate-50 dark:hover:bg-slate-900"
                    }`}
                    key={suggestion.id}
                    onClick={() => onSelectSuggestion(suggestion)}
                  >
                    <td className="border-b border-slate-100 px-5 py-4 font-medium text-slate-950 dark:border-slate-800 dark:text-slate-50">{suggestion.alias_value}</td>
                    <td className="border-b border-slate-100 px-5 py-4 text-slate-600 dark:border-slate-800 dark:text-slate-300">{suggestion.canonical_value}</td>
                    <td className="border-b border-slate-100 px-5 py-4 dark:border-slate-800"><StatusBadge status={suggestion.status} /></td>
                    <td className="border-b border-slate-100 px-5 py-4 text-slate-600 dark:border-slate-800 dark:text-slate-300">{suggestion.source}</td>
                    <td className="border-b border-slate-100 px-5 py-4 text-slate-600 dark:border-slate-800 dark:text-slate-300">{formatConfidence(suggestion.confidence)}</td>
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
  canReview,
  isApproving,
  isRejecting,
  onApprove,
  onReject,
  reviewErrorMessage,
  suggestion,
}: {
  canReview: boolean;
  isApproving?: boolean;
  isRejecting?: boolean;
  onApprove: (suggestion: GovernanceSuggestion, payload: SuggestionReviewRequest) => Promise<void> | void;
  onReject: (suggestion: GovernanceSuggestion, payload: SuggestionReviewRequest) => Promise<void> | void;
  reviewErrorMessage?: string | null;
  suggestion: GovernanceSuggestion | null;
}) {
  const [reviewComment, setReviewComment] = useState("");

  useEffect(() => {
    setReviewComment("");
  }, [suggestion?.id]);

  if (!suggestion) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Suggestion details</CardTitle>
          <CardDescription>Select a suggestion to inspect context and review actions.</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-slate-500 dark:text-slate-400">No suggestion selected.</p>
        </CardContent>
      </Card>
    );
  }

  const canReviewPending = canReview && suggestion.status === "pending";

  async function handleApprove() {
    if (!suggestion || !canReviewPending) {
      return;
    }
    await onApprove(suggestion, { review_comment: reviewComment.trim() || null });
  }

  async function handleReject() {
    if (!suggestion || !canReviewPending) {
      return;
    }
    await onReject(suggestion, { review_comment: reviewComment.trim() || null });
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle>{suggestion.alias_value}</CardTitle>
            <CardDescription>Proposed alias for {suggestion.canonical_value}</CardDescription>
          </div>
          <StatusBadge status={suggestion.status} />
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <dl className="grid gap-3 text-sm">
          <DetailRow label="Canonical term" value={suggestion.canonical_value} />
          <DetailRow label="Slot" value={suggestion.slot} />
          <DetailRow label="Source" value={suggestion.source} />
          <DetailRow label="Confidence" value={formatConfidence(suggestion.confidence)} />
          <DetailRow label="Created by" value={suggestion.created_by ?? "Unknown"} />
          {suggestion.reviewed_by ? <DetailRow label="Reviewed by" value={suggestion.reviewed_by} /> : null}
          {suggestion.review_comment ? <DetailRow label="Review comment" value={suggestion.review_comment} /> : null}
        </dl>

        <div className="rounded-xl border border-slate-100 p-4 dark:border-slate-800">
          <div className="text-sm font-semibold text-slate-950 dark:text-slate-50">Context</div>
          <p className="mt-2 whitespace-pre-wrap text-sm text-slate-600 dark:text-slate-300">
            {suggestion.context || "No context provided."}
          </p>
        </div>

        {!canReview ? (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
            Contributors can create suggestions, but only admins and moderators can approve or reject them.
          </div>
        ) : null}

        {suggestion.status !== "pending" ? (
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300">
            This suggestion has already been reviewed.
          </div>
        ) : null}

        {reviewErrorMessage ? <InlineError message={reviewErrorMessage} /> : null}

        <label className="block space-y-1.5">
          <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Review comment</span>
          <textarea
            className="min-h-24 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-slate-400 focus:ring-2 focus:ring-slate-100 disabled:cursor-not-allowed disabled:bg-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-500 dark:disabled:bg-slate-900 dark:focus:border-slate-500 dark:focus:ring-slate-800"
            disabled={!canReviewPending || isApproving || isRejecting}
            onChange={(event) => setReviewComment(event.target.value)}
            placeholder="Optional reason for approve/reject."
            value={reviewComment}
          />
        </label>

        <div className="flex flex-wrap gap-2">
          <Button disabled={!canReviewPending || isApproving || isRejecting} onClick={handleApprove} type="button">
            <CheckCircle className="mr-2 h-4 w-4" />
            {isApproving ? "Approving..." : "Approve suggestion"}
          </Button>
          <Button disabled={!canReviewPending || isApproving || isRejecting} onClick={handleReject} type="button" variant="secondary">
            <XCircle className="mr-2 h-4 w-4" />
            {isRejecting ? "Rejecting..." : "Reject suggestion"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-1 rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-950">
      <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="text-sm font-medium text-slate-900 dark:text-slate-100">{value}</dd>
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
  return error instanceof Error ? error.message : "Request failed. Check the governance API and try again.";
}

function formatConfidence(confidence: number) {
  return confidence.toFixed(2);
}

function normalizeConfidence(value: string) {
  const parsed = Number.parseFloat(value);
  if (Number.isNaN(parsed)) {
    return 1;
  }
  return Math.min(1, Math.max(0, parsed));
}

function upsertSuggestion(
  queryClient: ReturnType<typeof useQueryClient>,
  profileName: string | null,
  statusFilter: SuggestionStatus | "all",
  suggestion: GovernanceSuggestion,
) {
  queryClient.setQueryData<GovernanceSuggestion[]>(["suggestions", profileName, statusFilter], (currentSuggestions = []) => {
    const shouldStayVisible = statusFilter === "all" || suggestion.status === statusFilter;
    const withoutSuggestion = currentSuggestions.filter((currentSuggestion) => currentSuggestion.id !== suggestion.id);
    if (!shouldStayVisible) {
      return withoutSuggestion;
    }
    return [suggestion, ...withoutSuggestion].sort(sortSuggestions);
  });
}

function sortSuggestions(left: GovernanceSuggestion, right: GovernanceSuggestion) {
  if (left.status !== right.status) {
    return left.status.localeCompare(right.status);
  }
  return right.id - left.id;
}
