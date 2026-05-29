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
        <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50/60 p-4 text-sm dark:border-slate-800 dark:bg-slate-900/35">
          <div className="font-semibold text-slate-800 dark:text-slate-100">No profiles are ready for AI Inbox</div>
          <p className="mt-1 leading-6 text-slate-500 dark:text-slate-400">
            Seed a profile through the headless API, dictionary import, or GitOps workflow before reviewers triage agent proposals.
          </p>
        </div>
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
  const validationStatus = suggestion.validation_status ?? validationStatusFromSummary(suggestion);
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
          <DetailStat icon={<GitPullRequest className="h-4 w-4" />} label="Decision" value={applyPolicy?.decision ?? validationStatus} />
          <DetailStat icon={<Clock3 className="h-4 w-4" />} label="Status" value={suggestion.status} />
          <DetailStat icon={<FileText className="h-4 w-4" />} label="Evidence docs" value={evidenceDocuments.length} />
        </div>

        <RiskPolicyPanel applyPolicy={applyPolicy} riskLevel={riskLevel} validationStatus={validationStatus} />
        <ValidationFindingsPanel suggestion={suggestion} validationStatus={validationStatus} />
        <EvidenceSnapshotPanel suggestion={suggestion} />
        <SourceAndPayloadPanel suggestion={suggestion} />
        <ReviewActionPanel
          actionErrorMessage={actionErrorMessage}
          canReview={canReview}
          canTakeAction={canTakeAction}
          isActionPending={isActionPending}
          lastActionMessage={lastActionMessage}
          onApprove={onApprove}
          onReject={onReject}
          reviewComment={reviewComment}
          setReviewComment={setReviewComment}
          suggestion={suggestion}
        />
      </div>
    </EntityDetailPanel>
  );
}

function RiskPolicyPanel({
  applyPolicy,
  riskLevel,
  validationStatus,
}: {
  applyPolicy: GovernanceSuggestion["apply_policy"] | null;
  riskLevel: string;
  validationStatus: string;
}) {
  const policyBadges = applyPolicy
    ? [
        applyPolicy.can_batch_apply ? "batch apply candidate" : "batch apply blocked",
        applyPolicy.requires_admin ? "admin required" : "reviewer allowed",
        applyPolicy.requires_warning_override ? "warning override required" : "no warning override",
        applyPolicy.auto_apply_allowed ? "auto-apply allowed" : "auto-apply disabled",
      ]
    : ["policy not reported"];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Risk and apply policy</CardTitle>
        <CardDescription>
          The detail view mirrors backend policy output. It explains whether this is a low-risk review item, a warning case, or an admin-only change.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="grid gap-3 sm:grid-cols-3">
          <KeyValue label="Risk" value={riskLevel} />
          <KeyValue label="Validation" value={validationStatus} />
          <KeyValue label="Decision" value={applyPolicy?.decision ?? "not reported"} />
        </div>
        <div className="flex flex-wrap gap-2">
          {policyBadges.map((badge) => (
            <Badge key={badge}>{badge}</Badge>
          ))}
        </div>
        {applyPolicy?.reasons?.length ? (
          <div>
            <div className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">Policy reasons</div>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-slate-600 dark:text-slate-300">
              {applyPolicy.reasons.map((reason) => (
                <li key={reason}>{humanizeToken(reason)}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function ValidationFindingsPanel({ suggestion, validationStatus }: { suggestion: GovernanceSuggestion; validationStatus: string }) {
  const findings = validationFindings(suggestion);
  const signals = validationSignals(suggestion);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Validation findings</CardTitle>
        <CardDescription>Review blockers, warnings, and backend signals before pressing approve or reject.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="grid gap-3 sm:grid-cols-2">
          <KeyValue label="Status" value={validationStatus} />
          <KeyValue label="Can approve" value={suggestion.can_approve === undefined ? "not reported" : suggestion.can_approve ? "yes" : "no"} />
          <KeyValue label="Can apply" value={suggestion.can_apply === undefined ? "not reported" : suggestion.can_apply ? "yes" : "no"} />
          <KeyValue label="Lifecycle" value={suggestion.lifecycle_status ?? "not reported"} />
        </div>
        {suggestion.lifecycle_reason ? <KeyValue label="Lifecycle reason" value={humanizeToken(suggestion.lifecycle_reason)} /> : null}
        {findings.length ? (
          <div className="space-y-2">
            {findings.map((finding) => (
              <div
                className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200"
                key={`${finding.kind}-${finding.message}`}
              >
                <span className="font-medium capitalize">{finding.kind}: </span>
                {humanizeToken(finding.message)}
              </div>
            ))}
          </div>
        ) : (
          <p className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
            No blockers or warnings were reported by validation.
          </p>
        )}
        {signals.length ? (
          <div>
            <div className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">Policy signals</div>
            <div className="mt-2 flex flex-wrap gap-2">
              {signals.map(([key, value]) => (
                <Badge key={key}>{key}: {String(value)}</Badge>
              ))}
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function EvidenceSnapshotPanel({ suggestion }: { suggestion: GovernanceSuggestion }) {
  const snapshot = suggestion.evidence_snapshot;
  const documents = snapshot?.documents ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Evidence snapshot</CardTitle>
        <CardDescription>{snapshot ? evidenceSnapshotTitle(snapshot) : "No saved evidence snapshot yet."}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {snapshot ? (
          <div className="grid gap-3 text-sm sm:grid-cols-2">
            <KeyValue label="Binding" value={snapshot.binding_name} />
            <KeyValue label="Index" value={snapshot.index_name} />
            <KeyValue label="Query" value={snapshot.query} />
            <KeyValue label="Canonical" value={snapshot.canonical_value ?? "not set"} />
          </div>
        ) : null}
        {snapshot?.warnings?.length ? (
          <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
            <div className="font-medium">Evidence warnings</div>
            <ul className="mt-1 list-disc pl-5">
              {snapshot.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {documents.length ? (
          <div className="space-y-3">
            {documents.map((document) => (
              <EvidenceDocumentCard document={document} key={`${document.document_id}-${document.field}-${document.match_start}`} />
            ))}
          </div>
        ) : (
          <p className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
            No evidence snapshot is attached. Refresh evidence from the legacy Suggestions workflow, then return to Inbox for review.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function EvidenceDocumentCard({ document }: { document: NonNullable<GovernanceSuggestion["evidence_snapshot"]>["documents"][number] }) {
  return (
    <div className="rounded-xl border border-slate-200 p-3 text-sm dark:border-slate-800">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="font-medium text-slate-900 dark:text-slate-100">{document.document_id}</div>
          <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{document.index_name} · {document.field}</div>
        </div>
        <Badge>match: {document.matched_text || "unknown"}</Badge>
      </div>
      <p className="mt-3 leading-6 text-slate-600 dark:text-slate-300">{renderEvidenceFragment(document)}</p>
      <div className="mt-2 text-xs text-slate-500 dark:text-slate-400">
        Match range: {document.match_start}–{document.match_end}
      </div>
    </div>
  );
}

function SourceAndPayloadPanel({ suggestion }: { suggestion: GovernanceSuggestion }) {
  const sourcePayload = suggestion.source_payload;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Source and audit metadata</CardTitle>
        <CardDescription>Trace where the proposal came from and inspect agent payload details without leaving the review screen.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <KeyValue label="Source" value={suggestion.proposal_source_name || suggestion.created_by || "unknown"} />
        <KeyValue label="Source type" value={suggestion.proposal_source_type || suggestion.source} />
        <KeyValue label="Idempotency" value={suggestion.idempotency_key ?? "not provided"} />
        <KeyValue label="Created" value={formatDateTime(suggestion.created_at)} />
        <KeyValue label="Updated" value={formatDateTime(suggestion.updated_at)} />
        {sourcePayload ? (
          <details className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
            <summary className="cursor-pointer text-sm font-medium text-slate-700 dark:text-slate-200">Source payload JSON</summary>
            <pre className="mt-3 max-h-72 overflow-auto rounded-lg bg-slate-950 p-3 text-xs text-slate-100">{safeJson(sourcePayload)}</pre>
          </details>
        ) : (
          <p className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
            No source payload was saved for this proposal.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function ReviewActionPanel({
  actionErrorMessage,
  canReview,
  canTakeAction,
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
  canTakeAction: boolean;
  isActionPending: boolean;
  lastActionMessage?: string | null;
  onApprove: () => void;
  onReject: () => void;
  reviewComment: string;
  setReviewComment: (value: string) => void;
  suggestion: GovernanceSuggestion;
}) {
  return (
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
            className="min-h-24 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:focus:border-slate-500 dark:ring-slate-800 dark:disabled:bg-slate-900"
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
  const scope = statusFilter === "all" ? "proposals" : `${statusFilter} proposals`;
  return (
    <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50/60 p-8 text-center dark:border-slate-800 dark:bg-slate-900/35">
      <Inbox className="mx-auto h-8 w-8 text-slate-400" />
      <h3 className="mt-3 text-sm font-semibold text-slate-900 dark:text-slate-100">No {scope} in this inbox view</h3>
      <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-slate-400">
        {statusFilter === "pending"
          ? "The human review queue is empty. New agent proposals will appear here after scout workers submit candidates."
          : "Switch back to pending to see active moderation work, or keep this filter to audit already processed proposals."}
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


function validationFindings(suggestion: GovernanceSuggestion) {
  const summary = suggestion.validation_summary;
  const findings: Array<{ kind: string; message: string }> = [];
  if (!summary || typeof summary !== "object") {
    return findings;
  }

  const buckets: Array<[string, unknown]> = [
    ["blocker", (summary as { blockers?: unknown }).blockers],
    ["blocker", (summary as { blocked_reasons?: unknown }).blocked_reasons],
    ["warning", (summary as { warnings?: unknown }).warnings],
    ["warning", (summary as { warning_reasons?: unknown }).warning_reasons],
    ["reason", (summary as { reasons?: unknown }).reasons],
    ["reason", (summary as { validation_reasons?: unknown }).validation_reasons],
  ];

  for (const [kind, value] of buckets) {
    for (const message of stringList(value)) {
      findings.push({ kind, message });
    }
  }

  const applyPolicy = suggestion.apply_policy ?? policyFromSummary(suggestion);
  if (applyPolicy?.requires_admin) {
    findings.push({ kind: "policy", message: "admin_required" });
  }
  if (applyPolicy?.requires_warning_override) {
    findings.push({ kind: "policy", message: "warning_override_required" });
  }
  if (applyPolicy && !applyPolicy.can_batch_apply) {
    findings.push({ kind: "policy", message: "batch_apply_not_allowed" });
  }

  return dedupeFindings(findings);
}

function validationSignals(suggestion: GovernanceSuggestion) {
  const applyPolicy = suggestion.apply_policy ?? policyFromSummary(suggestion);
  if (!applyPolicy?.signals || typeof applyPolicy.signals !== "object") {
    return [] as Array<[string, unknown]>;
  }
  return Object.entries(applyPolicy.signals)
    .filter(([, value]) => typeof value === "string" || typeof value === "number" || typeof value === "boolean")
    .slice(0, 6);
}

function stringList(value: unknown) {
  if (!Array.isArray(value)) {
    return [] as string[];
  }
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function dedupeFindings(findings: Array<{ kind: string; message: string }>) {
  const seen = new Set<string>();
  return findings.filter((finding) => {
    const key = `${finding.kind}:${finding.message}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function renderEvidenceFragment(document: NonNullable<GovernanceSuggestion["evidence_snapshot"]>["documents"][number]) {
  const fragment = document.fragment || document.highlighted_fragment || "";
  const matchedText = document.matched_text;
  if (!matchedText) {
    return fragment;
  }

  const matchIndex = fragment.toLowerCase().indexOf(matchedText.toLowerCase());
  if (matchIndex < 0) {
    return (
      <>
        {fragment} <mark className="rounded bg-amber-100 px-1 text-amber-950 dark:bg-amber-300/20 dark:text-amber-100">{matchedText}</mark>
      </>
    );
  }

  const before = fragment.slice(0, matchIndex);
  const match = fragment.slice(matchIndex, matchIndex + matchedText.length);
  const after = fragment.slice(matchIndex + matchedText.length);
  return (
    <>
      {before}
      <mark className="rounded bg-amber-100 px-1 text-amber-950 dark:bg-amber-300/20 dark:text-amber-100">{match}</mark>
      {after}
    </>
  );
}

function safeJson(value: unknown) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "Unable to render source payload.";
  }
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return "not reported";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function humanizeToken(value: string) {
  return value.split("_").join(" ");
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
