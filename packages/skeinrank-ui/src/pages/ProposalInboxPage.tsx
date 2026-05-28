import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle, Clock3, FileText, GitPullRequest, Inbox, ShieldCheck, XCircle } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useState } from "react";

import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { ConsolePage, EntityDetailPanel, MasterDetailLayout, MetricPill, SectionCard, WorkspaceHeader } from "../components/layout/ConsolePrimitives";
import { approveSuggestion, listProfiles, listSuggestions, rejectSuggestion } from "../lib/api";
import { permissionsForUser } from "../permissions";
import type { AuthUser, GovernanceSuggestion, Profile, SuggestionReviewRequest, SuggestionStatus } from "../types";

const inboxStatusFilters: Array<SuggestionStatus | "all"> = ["pending", "approved", "rejected", "all"];

export function ProposalInboxPage({ currentUser }: { currentUser: AuthUser }) {
  const permissions = permissionsForUser(currentUser);
  const queryClient = useQueryClient();
  const [selectedProfile, setSelectedProfile] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<SuggestionStatus | "all">("pending");
  const [selectedSuggestionId, setSelectedSuggestionId] = useState<number | null>(null);
  const [reviewComment, setReviewComment] = useState("");
  const [lastActionMessage, setLastActionMessage] = useState<string | null>(null);

  const profilesQuery = useQuery({
    queryKey: ["profiles"],
    queryFn: listProfiles,
  });

  useEffect(() => {
    if (!profilesQuery.data || profilesQuery.data.length === 0) {
      setSelectedProfile(null);
      setSelectedSuggestionId(null);
      return;
    }

    if (!selectedProfile || !profilesQuery.data.some((profile) => profile.name === selectedProfile)) {
      setSelectedProfile(profilesQuery.data[0].name);
      setSelectedSuggestionId(null);
      setLastActionMessage(null);
    }
  }, [profilesQuery.data, selectedProfile]);

  const suggestionsQuery = useQuery({
    queryKey: ["suggestions", selectedProfile, statusFilter],
    queryFn: () => listSuggestions(selectedProfile ?? "", statusFilter),
    enabled: Boolean(selectedProfile),
  });

  const suggestions = suggestionsQuery.data ?? [];
  const selectedSuggestion = useMemo(() => {
    if (!selectedSuggestionId) return null;
    return suggestions.find((suggestion) => suggestion.id === selectedSuggestionId) ?? null;
  }, [selectedSuggestionId, suggestions]);

  useEffect(() => {
    if (suggestions.length === 0) {
      setSelectedSuggestionId(null);
      return;
    }
    if (!selectedSuggestionId || !suggestions.some((suggestion) => suggestion.id === selectedSuggestionId)) {
      setSelectedSuggestionId(suggestions[0].id);
      setReviewComment("");
    }
  }, [selectedSuggestionId, suggestions]);

  const approveMutation = useMutation({
    mutationFn: ({ suggestion, payload }: { suggestion: GovernanceSuggestion; payload: SuggestionReviewRequest }) => {
      if (!selectedProfile) {
        throw new Error("Select a profile before approving a proposal.");
      }
      return approveSuggestion(selectedProfile, suggestion.id, payload);
    },
    onSuccess: (suggestion) => {
      setReviewComment("");
      setLastActionMessage(`Approved proposal #${suggestion.id}.`);
      syncReviewedSuggestion(queryClient, selectedProfile, statusFilter, suggestion);
      if (statusFilter === "all" || statusFilter === suggestion.status) {
        setSelectedSuggestionId(suggestion.id);
      } else {
        setSelectedSuggestionId(null);
      }
      void queryClient.invalidateQueries({ queryKey: ["suggestions", selectedProfile] });
      void queryClient.invalidateQueries({ queryKey: ["terms", selectedProfile] });
    },
  });

  const rejectMutation = useMutation({
    mutationFn: ({ suggestion, payload }: { suggestion: GovernanceSuggestion; payload: SuggestionReviewRequest }) => {
      if (!selectedProfile) {
        throw new Error("Select a profile before rejecting a proposal.");
      }
      return rejectSuggestion(selectedProfile, suggestion.id, payload);
    },
    onSuccess: (suggestion) => {
      setReviewComment("");
      setLastActionMessage(`Rejected proposal #${suggestion.id}.`);
      syncReviewedSuggestion(queryClient, selectedProfile, statusFilter, suggestion);
      if (statusFilter === "all" || statusFilter === suggestion.status) {
        setSelectedSuggestionId(suggestion.id);
      } else {
        setSelectedSuggestionId(null);
      }
      void queryClient.invalidateQueries({ queryKey: ["suggestions", selectedProfile] });
    },
  });

  const pendingCount = suggestions.filter((suggestion) => suggestion.status === "pending").length;
  const evidenceReadyCount = suggestions.filter((suggestion) => suggestion.evidence_snapshot).length;
  const lowRiskCount = suggestions.filter((suggestion) => proposalRiskLevel(suggestion) === "low").length;
  const selectedProfileLabel = selectedProfile ?? "No profile";
  const isReviewActionPending = approveMutation.isPending || rejectMutation.isPending;

  function handleSelectProfile(profileName: string) {
    setSelectedProfile(profileName);
    setSelectedSuggestionId(null);
    setReviewComment("");
    setLastActionMessage(null);
  }

  function handleSetStatusFilter(status: SuggestionStatus | "all") {
    setStatusFilter(status);
    setSelectedSuggestionId(null);
    setReviewComment("");
    setLastActionMessage(null);
  }

  function handleApprove() {
    if (!selectedSuggestion || selectedSuggestion.status !== "pending") return;
    approveMutation.mutate({ suggestion: selectedSuggestion, payload: { review_comment: reviewComment.trim() || null } });
  }

  function handleReject() {
    if (!selectedSuggestion || selectedSuggestion.status !== "pending") return;
    rejectMutation.mutate({ suggestion: selectedSuggestion, payload: { review_comment: reviewComment.trim() || null } });
  }

  return (
    <ConsolePage>
      <WorkspaceHeader
        eyebrow="Human-in-the-loop"
        title="AI Proposals Inbox"
        description="Review agent-submitted terminology proposals without turning the UI into a manual CRUD editor. Approve or reject pending items after checking risk, policy, and evidence context."
        actions={
          <div className="flex flex-wrap gap-2">
            <Badge>{selectedProfileLabel}</Badge>
            <Badge>{permissions.canReviewSuggestions ? "Reviewer mode" : "Read-only mode"}</Badge>
          </div>
        }
      />

      <div className="grid gap-4 md:grid-cols-4">
        <MetricPill label="Visible proposals" value={suggestions.length} />
        <MetricPill label="Pending" value={pendingCount} />
        <MetricPill label="Evidence ready" value={evidenceReadyCount} />
        <MetricPill label="Low risk" value={lowRiskCount} />
      </div>

      <MasterDetailLayout>
        <div className="space-y-4">
          <InboxToolbar
            isLoading={profilesQuery.isLoading}
            loadErrorMessage={profilesQuery.isError ? profilesQuery.error.message : null}
            onSelectProfile={handleSelectProfile}
            onSetStatusFilter={handleSetStatusFilter}
            profiles={profilesQuery.data ?? []}
            selectedProfile={selectedProfile}
            statusFilter={statusFilter}
          />

          <SectionCard
            title="Proposal queue"
            description="Cards are intentionally review-focused: source, risk, validation, confidence, and evidence readiness."
            contentClassName="space-y-3"
          >
            {suggestionsQuery.isLoading ? (
              <p className="text-sm text-slate-500 dark:text-slate-400">Loading proposals...</p>
            ) : null}
            {suggestionsQuery.isError ? <InlineError message={suggestionsQuery.error.message} /> : null}
            {!suggestionsQuery.isLoading && !suggestionsQuery.isError && suggestions.length === 0 ? (
              <EmptyInbox statusFilter={statusFilter} />
            ) : null}
            {suggestions.map((suggestion) => (
              <ProposalCard
                isSelected={selectedSuggestionId === suggestion.id}
                key={suggestion.id}
                onSelect={() => {
                  setSelectedSuggestionId(suggestion.id);
                  setReviewComment(suggestion.review_comment ?? "");
                  setLastActionMessage(null);
                }}
                suggestion={suggestion}
              />
            ))}
          </SectionCard>
        </div>
        <ProposalDetail
          actionErrorMessage={errorMessage(approveMutation.error) ?? errorMessage(rejectMutation.error)}
          canReview={permissions.canReviewSuggestions}
          isActionPending={isReviewActionPending}
          lastActionMessage={lastActionMessage}
          onApprove={handleApprove}
          onReject={handleReject}
          reviewComment={reviewComment}
          setReviewComment={setReviewComment}
          suggestion={selectedSuggestion}
        />
      </MasterDetailLayout>
    </ConsolePage>
  );
}

function InboxToolbar({
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
    <SectionCard
      contentClassName="space-y-4"
      title="Inbox scope"
      description="Filter proposals by profile and lifecycle status. Pending stays the default for day-to-day moderation."
    >
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
                    ? "border-slate-950 bg-slate-950 text-white shadow-sm dark:border-slate-100 dark:bg-slate-100 dark:text-slate-950"
                    : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300 dark:hover:bg-slate-900"
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
          No profiles found. Seed a profile before reviewing agent proposals.
        </p>
      )}

      <label className="block space-y-1.5">
        <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Inbox status</span>
        <select
          className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:focus:border-slate-500 dark:focus:ring-slate-800"
          onChange={(event) => onSetStatusFilter(event.target.value as SuggestionStatus | "all")}
          value={statusFilter}
        >
          {inboxStatusFilters.map((status) => (
            <option key={status} value={status}>
              {status}
            </option>
          ))}
        </select>
      </label>
    </SectionCard>
  );
}

function ProposalCard({ isSelected, onSelect, suggestion }: { isSelected: boolean; onSelect: () => void; suggestion: GovernanceSuggestion }) {
  const riskLevel = proposalRiskLevel(suggestion);
  const validationStatus = suggestion.validation_status ?? validationStatusFromSummary(suggestion);
  return (
    <button
      aria-current={isSelected ? "true" : undefined}
      className={`w-full rounded-2xl border p-4 text-left transition-colors ${
        isSelected
          ? "border-slate-950 bg-slate-950 text-white shadow-sm dark:border-slate-100 dark:bg-slate-100 dark:text-slate-950"
          : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-950 dark:hover:bg-slate-900"
      }`}
      onClick={onSelect}
      type="button"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold">{proposalTitle(suggestion)}</div>
          <div className={`mt-1 truncate text-xs ${isSelected ? "text-slate-300 dark:text-slate-600" : "text-slate-500 dark:text-slate-400"}`}>
            {suggestion.proposal_source_name || suggestion.created_by || "unknown source"} · {formatConfidence(suggestion.confidence)} confidence
          </div>
        </div>
        <StatusBadge status={suggestion.status} />
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-xs">
        <Badge>Risk: {riskLevel}</Badge>
        <Badge>Validation: {validationStatus}</Badge>
        <Badge>{suggestion.evidence_snapshot ? "Evidence ready" : "No evidence"}</Badge>
      </div>
      {suggestion.context ? (
        <p className={`mt-3 line-clamp-2 text-xs leading-5 ${isSelected ? "text-slate-200 dark:text-slate-700" : "text-slate-500 dark:text-slate-400"}`}>
          {suggestion.context}
        </p>
      ) : null}
    </button>
  );
}

function ProposalDetail({
  actionErrorMessage,
  canReview,
  isActionPending,
  lastActionMessage,
  onApprove,
  onReject,
  reviewComment,
  setReviewComment,
  suggestion,
}: {
  actionErrorMessage?: string | null;
  canReview: boolean;
  isActionPending: boolean;
  lastActionMessage?: string | null;
  onApprove: () => void;
  onReject: () => void;
  reviewComment: string;
  setReviewComment: (value: string) => void;
  suggestion: GovernanceSuggestion | null;
}) {
  if (!suggestion) {
    return (
      <EntityDetailPanel
        title="Select a proposal"
        description="Choose a proposal card to inspect evidence, risk, policy, and review actions."
      >
        <div className="rounded-2xl border border-dashed border-slate-200 p-6 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
          The Inbox only shows moderation work. Manual term editing remains outside this screen.
        </div>
      </EntityDetailPanel>
    );
  }

  const riskLevel = proposalRiskLevel(suggestion);
  const applyPolicy = suggestion.apply_policy ?? policyFromSummary(suggestion);
  const canTakeAction = canReview && suggestion.status === "pending";
  const evidenceDocuments = suggestion.evidence_snapshot?.documents ?? [];

  return (
    <EntityDetailPanel
      badge={<Badge>#{suggestion.id}</Badge>}
      title={proposalTitle(suggestion)}
      description={suggestion.context || "No context was supplied by the proposal source."}
    >
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <DetailStat icon={<ShieldCheck className="h-4 w-4" />} label="Risk level" value={riskLevel} />
          <DetailStat icon={<GitPullRequest className="h-4 w-4" />} label="Decision" value={applyPolicy?.decision ?? suggestion.validation_status ?? "unknown"} />
          <DetailStat icon={<Clock3 className="h-4 w-4" />} label="Status" value={suggestion.status} />
          <DetailStat icon={<FileText className="h-4 w-4" />} label="Evidence docs" value={evidenceDocuments.length} />
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Policy and source</CardTitle>
            <CardDescription>Human reviewers see the same proposal source and safety policy before acting.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <KeyValue label="Source" value={suggestion.proposal_source_name || suggestion.created_by || "unknown"} />
            <KeyValue label="Source type" value={suggestion.proposal_source_type || suggestion.source} />
            <KeyValue label="Validation" value={suggestion.validation_status ?? validationStatusFromSummary(suggestion)} />
            <KeyValue label="Can apply" value={suggestion.can_apply === undefined ? "not reported" : suggestion.can_apply ? "yes" : "no"} />
            {applyPolicy?.reasons?.length ? (
              <div>
                <div className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">Policy reasons</div>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-slate-600 dark:text-slate-300">
                  {applyPolicy.reasons.map((reason) => (
                    <li key={reason}>{reason}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Evidence snapshot</CardTitle>
            <CardDescription>{suggestion.evidence_snapshot ? evidenceSnapshotTitle(suggestion.evidence_snapshot) : "No saved evidence snapshot yet."}</CardDescription>
          </CardHeader>
          <CardContent>
            {evidenceDocuments.length ? (
              <div className="space-y-3">
                {evidenceDocuments.slice(0, 3).map((document) => (
                  <div className="rounded-xl border border-slate-200 p-3 text-sm dark:border-slate-800" key={`${document.document_id}-${document.field}`}>
                    <div className="font-medium text-slate-900 dark:text-slate-100">{document.document_id}</div>
                    <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{document.index_name} · {document.field}</div>
                    <p className="mt-2 text-slate-600 dark:text-slate-300">{document.fragment}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
                No evidence snapshot is attached. Open the legacy suggestions workflow to refresh evidence until the detail evidence view is added in 58B.
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Review action</CardTitle>
            <CardDescription>Actions use existing approve/reject endpoints and rely on backend optimistic state checks.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {lastActionMessage ? (
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/40 dark:text-emerald-200">
                {lastActionMessage}
              </div>
            ) : null}
            {actionErrorMessage ? <InlineError message={actionErrorMessage} /> : null}
            {!canReview ? (
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
                Your role can inspect proposals but cannot approve or reject them.
              </div>
            ) : null}
            {suggestion.status !== "pending" ? (
              <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
                This proposal has already been reviewed by {suggestion.reviewed_by ?? "another reviewer"}.
              </div>
            ) : null}
            <label className="block space-y-1.5">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Review comment</span>
              <textarea
                className="min-h-24 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:focus:border-slate-500 dark:focus:ring-slate-800 dark:disabled:bg-slate-900"
                disabled={!canTakeAction || isActionPending}
                onChange={(event) => setReviewComment(event.target.value)}
                placeholder="Why is this safe to approve or why should it be rejected?"
                value={reviewComment}
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <Button disabled={!canTakeAction || isActionPending} onClick={onApprove} type="button">
                <CheckCircle className="mr-2 h-4 w-4" />
                Approve proposal
              </Button>
              <Button disabled={!canTakeAction || isActionPending} onClick={onReject} type="button">
                <XCircle className="mr-2 h-4 w-4" />
                Reject proposal
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </EntityDetailPanel>
  );
}

function DetailStat({ icon, label, value }: { icon: ReactNode; label: string; value: number | string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-950">
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {icon}
        {label}
      </div>
      <div className="mt-2 text-lg font-semibold text-slate-950 dark:text-slate-50">{value}</div>
    </div>
  );
}

function KeyValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-xl border border-slate-100 px-3 py-2 dark:border-slate-800">
      <span className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</span>
      <span className="text-right text-sm font-medium text-slate-700 dark:text-slate-200">{value}</span>
    </div>
  );
}

function StatusBadge({ status }: { status: SuggestionStatus }) {
  const icon = status === "approved" ? CheckCircle : status === "rejected" ? XCircle : Inbox;
  const Icon = icon;
  return (
    <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-slate-200 bg-white px-2 py-1 text-xs font-medium capitalize text-slate-700 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-200">
      <Icon className="h-3.5 w-3.5" />
      {status}
    </span>
  );
}

function EmptyInbox({ statusFilter }: { statusFilter: SuggestionStatus | "all" }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-200 p-8 text-center dark:border-slate-800">
      <Inbox className="mx-auto h-8 w-8 text-slate-400" />
      <h3 className="mt-3 text-sm font-semibold text-slate-900 dark:text-slate-100">No proposals match this filter.</h3>
      <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
        {statusFilter === "pending" ? "The human review queue is empty." : "Switch back to pending to see active moderation work."}
      </p>
    </div>
  );
}

function InlineError({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200">
      {message}
    </div>
  );
}

function proposalTitle(suggestion: GovernanceSuggestion) {
  if (suggestion.suggestion_type === "canonical_term") {
    return `New canonical: ${suggestion.canonical_value}`;
  }
  return `${suggestion.alias_value ?? "alias"} → ${suggestion.canonical_value}`;
}

function formatConfidence(confidence: number) {
  return `${Math.round(confidence * 100)}%`;
}

function proposalRiskLevel(suggestion: GovernanceSuggestion) {
  return suggestion.risk_level ?? suggestion.apply_policy?.risk_level ?? policyFromSummary(suggestion)?.risk_level ?? "unknown";
}

function validationStatusFromSummary(suggestion: GovernanceSuggestion) {
  const summary = suggestion.validation_summary;
  if (summary && typeof summary === "object" && "status" in summary) {
    const status = (summary as { status?: unknown }).status;
    if (typeof status === "string") return status;
  }
  return "unknown";
}

function policyFromSummary(suggestion: GovernanceSuggestion) {
  const summary = suggestion.validation_summary;
  if (!summary || typeof summary !== "object" || !("apply_policy" in summary)) {
    return null;
  }
  const policy = (summary as { apply_policy?: unknown }).apply_policy;
  if (!policy || typeof policy !== "object") {
    return null;
  }
  return policy as NonNullable<GovernanceSuggestion["apply_policy"]>;
}

function evidenceSnapshotTitle(snapshot: NonNullable<GovernanceSuggestion["evidence_snapshot"]>) {
  return `${snapshot.documents.length} documents from ${snapshot.binding_name} / ${snapshot.index_name}`;
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : null;
}

function syncReviewedSuggestion(
  queryClient: ReturnType<typeof useQueryClient>,
  profileName: string | null,
  statusFilter: SuggestionStatus | "all",
  suggestion: GovernanceSuggestion,
) {
  if (!profileName) return;

  queryClient.setQueryData<GovernanceSuggestion[]>(["suggestions", profileName, statusFilter], (items = []) => {
    if (statusFilter !== "all" && statusFilter !== suggestion.status) {
      return items.filter((item) => item.id !== suggestion.id);
    }
    return items.map((item) => (item.id === suggestion.id ? suggestion : item));
  });

  queryClient.setQueryData<GovernanceSuggestion[]>(["suggestions", profileName, suggestion.status], (items = []) => {
    if (items.some((item) => item.id === suggestion.id)) {
      return items.map((item) => (item.id === suggestion.id ? suggestion : item));
    }
    return [suggestion, ...items];
  });
}
