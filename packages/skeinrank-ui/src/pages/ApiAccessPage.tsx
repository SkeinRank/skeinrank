import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  Fingerprint,
  KeyRound,
  LockKeyhole,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import { type FormEvent, useEffect, useMemo, useState } from "react";

import {
  ConsolePage,
  EntityDetailPanel,
  MasterDetailLayout,
  MetricPill,
  SectionCard,
  WorkspaceHeader,
} from "../components/layout/ConsolePrimitives";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import {
  createPersonalApiToken,
  createServiceAccount,
  createServiceAccountToken,
  listPersonalApiTokens,
  listServiceAccounts,
  listServiceAccountTokens,
  revokePersonalApiToken,
  revokeServiceAccountToken,
  updateServiceAccount,
} from "../lib/api";
import { permissionsForUser } from "../permissions";
import type {
  ApiToken,
  ApiTokenCreateRequest,
  ApiTokenCreateResponse,
  ApiTokenScope,
  AuthUser,
  ServiceAccount,
  ServiceAccountCreateRequest,
  UserRole,
} from "../types";

const migrationScopes: ApiTokenScope[] = [
  "migration:validate",
  "migration:apply",
  "migration:export",
];
const userRoles: UserRole[] = ["admin", "moderator", "contributor"];

type TokenOwner = "personal" | "service";
type ApiAccessSection = "personal" | "service";

const apiAccessSections: Array<{
  id: ApiAccessSection;
  label: string;
  description: string;
}> = [
  {
    id: "personal",
    label: "Personal tokens",
    description: "Human-owned Bearer tokens for CLI, notebooks, and scripts.",
  },
  {
    id: "service",
    label: "Service accounts",
    description: "Bot identities for CI imports and scheduled automation.",
  },
];

type CopyOnceToken = {
  owner: TokenOwner;
  token: ApiTokenCreateResponse;
};

export function ApiAccessPage({ currentUser }: { currentUser: AuthUser }) {
  const permissions = permissionsForUser(currentUser);
  const canManageServiceAccounts = permissions.canManageServiceAccounts;
  const queryClient = useQueryClient();
  const [selectedServiceAccountName, setSelectedServiceAccountName] = useState<
    string | null
  >(null);
  const [copyOnceToken, setCopyOnceToken] = useState<CopyOnceToken | null>(
    null,
  );
  const [activeSection, setActiveSection] =
    useState<ApiAccessSection>("personal");

  const personalTokensQuery = useQuery({
    queryKey: ["auth", "api-tokens", "personal"],
    queryFn: listPersonalApiTokens,
  });

  const serviceAccountsQuery = useQuery({
    queryKey: ["auth", "service-accounts"],
    queryFn: listServiceAccounts,
    enabled: canManageServiceAccounts,
  });

  useEffect(() => {
    if (!serviceAccountsQuery.data || serviceAccountsQuery.data.length === 0) {
      setSelectedServiceAccountName(null);
      return;
    }
    if (
      !selectedServiceAccountName ||
      !serviceAccountsQuery.data.some(
        (account) => account.name === selectedServiceAccountName,
      )
    ) {
      setSelectedServiceAccountName(serviceAccountsQuery.data[0].name);
    }
  }, [selectedServiceAccountName, serviceAccountsQuery.data]);

  const selectedServiceAccount = useMemo(() => {
    if (!selectedServiceAccountName || !serviceAccountsQuery.data) {
      return null;
    }
    return (
      serviceAccountsQuery.data.find(
        (account) => account.name === selectedServiceAccountName,
      ) ?? null
    );
  }, [selectedServiceAccountName, serviceAccountsQuery.data]);

  const serviceAccountTokensQuery = useQuery({
    queryKey: [
      "auth",
      "service-accounts",
      selectedServiceAccountName,
      "tokens",
    ],
    queryFn: () => listServiceAccountTokens(selectedServiceAccountName ?? ""),
    enabled: canManageServiceAccounts && Boolean(selectedServiceAccountName),
  });

  const createPersonalTokenMutation = useMutation({
    mutationFn: (payload: ApiTokenCreateRequest) =>
      createPersonalApiToken(payload),
    onSuccess: (token) => {
      setCopyOnceToken({ owner: "personal", token });
      upsertPersonalToken(queryClient, token);
      void queryClient.invalidateQueries({
        queryKey: ["auth", "api-tokens", "personal"],
      });
    },
  });

  const revokePersonalTokenMutation = useMutation({
    mutationFn: (tokenId: number) => revokePersonalApiToken(tokenId),
    onSuccess: (_result, tokenId) => {
      markPersonalTokenRevoked(queryClient, tokenId);
      void queryClient.invalidateQueries({
        queryKey: ["auth", "api-tokens", "personal"],
      });
    },
  });

  const createServiceAccountMutation = useMutation({
    mutationFn: (payload: ServiceAccountCreateRequest) =>
      createServiceAccount(payload),
    onSuccess: (account) => {
      setSelectedServiceAccountName(account.name);
      upsertServiceAccount(queryClient, account);
      void queryClient.invalidateQueries({
        queryKey: ["auth", "service-accounts"],
      });
    },
  });

  const updateServiceAccountMutation = useMutation({
    mutationFn: ({
      accountName,
      isActive,
    }: {
      accountName: string;
      isActive: boolean;
    }) => updateServiceAccount(accountName, { is_active: isActive }),
    onSuccess: (account) => {
      setSelectedServiceAccountName(account.name);
      upsertServiceAccount(queryClient, account);
      void queryClient.invalidateQueries({
        queryKey: ["auth", "service-accounts"],
      });
      void queryClient.invalidateQueries({
        queryKey: ["auth", "service-accounts", account.name, "tokens"],
      });
    },
  });

  const createServiceTokenMutation = useMutation({
    mutationFn: ({
      accountName,
      payload,
    }: {
      accountName: string;
      payload: ApiTokenCreateRequest;
    }) => createServiceAccountToken(accountName, payload),
    onSuccess: (token, variables) => {
      setCopyOnceToken({ owner: "service", token });
      upsertServiceAccountToken(queryClient, variables.accountName, token);
      void queryClient.invalidateQueries({
        queryKey: ["auth", "service-accounts", variables.accountName, "tokens"],
      });
    },
  });

  const revokeServiceTokenMutation = useMutation({
    mutationFn: ({
      accountName,
      tokenId,
    }: {
      accountName: string;
      tokenId: number;
    }) => revokeServiceAccountToken(accountName, tokenId),
    onSuccess: (_result, variables) => {
      markServiceTokenRevoked(
        queryClient,
        variables.accountName,
        variables.tokenId,
      );
      void queryClient.invalidateQueries({
        queryKey: ["auth", "service-accounts", variables.accountName, "tokens"],
      });
    },
  });

  const personalTokens = personalTokensQuery.data ?? [];
  const serviceAccounts = serviceAccountsQuery.data ?? [];
  const serviceTokens = serviceAccountTokensQuery.data ?? [];
  const activePersonalTokens = countActiveTokens(personalTokens);
  const activeServiceAccounts = serviceAccounts.filter(
    (account) => account.is_active,
  ).length;
  const activeServiceTokens = countActiveTokens(serviceTokens);

  async function handleCreatePersonalToken(payload: ApiTokenCreateRequest) {
    await createPersonalTokenMutation.mutateAsync(payload);
  }

  async function handleRevokePersonalToken(tokenId: number) {
    if (
      !window.confirm(
        "Revoke this personal API token? Existing scripts using it will stop working.",
      )
    ) {
      return;
    }
    await revokePersonalTokenMutation.mutateAsync(tokenId);
  }

  async function handleCreateServiceAccount(
    payload: ServiceAccountCreateRequest,
  ) {
    await createServiceAccountMutation.mutateAsync(payload);
  }

  async function handleToggleServiceAccount(account: ServiceAccount) {
    await updateServiceAccountMutation.mutateAsync({
      accountName: account.name,
      isActive: !account.is_active,
    });
  }

  async function handleCreateServiceToken(payload: ApiTokenCreateRequest) {
    if (!selectedServiceAccount) {
      throw new Error("Select a service account before creating a token.");
    }
    await createServiceTokenMutation.mutateAsync({
      accountName: selectedServiceAccount.name,
      payload,
    });
  }

  async function handleRevokeServiceToken(tokenId: number) {
    if (!selectedServiceAccount) {
      return;
    }
    if (
      !window.confirm(
        "Revoke this service account token? Existing automation using it will stop working.",
      )
    ) {
      return;
    }
    await revokeServiceTokenMutation.mutateAsync({
      accountName: selectedServiceAccount.name,
      tokenId,
    });
  }

  return (
    <ConsolePage>
      <WorkspaceHeader
        actions={
          <ApiAccessTabs
            activeSection={activeSection}
            canManageServiceAccounts={canManageServiceAccounts}
            onChange={setActiveSection}
          />
        }
        description="Issue scoped tokens, manage automation identities, and keep migration access separate from human reviewer sessions."
        eyebrow="Security workspace"
        meta={
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MetricPill
              helper="Human-owned active keys"
              icon={KeyRound}
              label="Personal tokens"
              tone={activePersonalTokens > 0 ? "emerald" : "slate"}
              value={activePersonalTokens}
            />
            <MetricPill
              helper="Validate, apply, export"
              icon={ShieldCheck}
              label="Migration scopes"
              tone="cyan"
              value={migrationScopes.length}
            />
            <MetricPill
              helper={
                canManageServiceAccounts
                  ? "Active automation identities"
                  : "Admin-only automation"
              }
              icon={Bot}
              label="Service accounts"
              tone={canManageServiceAccounts ? "violet" : "amber"}
              value={
                canManageServiceAccounts ? activeServiceAccounts : "Admin"
              }
            />
            <MetricPill
              helper="Current selected service account"
              icon={Fingerprint}
              label="Service tokens"
              tone={activeServiceTokens > 0 ? "emerald" : "slate"}
              value={canManageServiceAccounts ? activeServiceTokens : "—"}
            />
          </div>
        }
        title="API security control plane"
      />

      {copyOnceToken ? (
        <CopyOnceTokenPanel
          token={copyOnceToken.token}
          onDismiss={() => setCopyOnceToken(null)}
        />
      ) : null}

      {activeSection === "personal" ? (
        <MasterDetailLayout asideWidthClassName="xl:grid-cols-[minmax(0,1fr)_390px] 2xl:grid-cols-[minmax(0,1fr)_430px]">
          <SectionCard
            actions={
              <Badge className="bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-200">
                {activePersonalTokens} active
              </Badge>
            }
            contentClassName="space-y-4"
            description="Monitor human-owned Bearer tokens used by notebooks, local CLI commands, and migration workflows."
            title="My API tokens"
          >
            <TokenTable
              isLoading={personalTokensQuery.isLoading}
              onRevoke={handleRevokePersonalToken}
              revokeDisabled={revokePersonalTokenMutation.isPending}
              tokens={personalTokens}
            />
          </SectionCard>

          <EntityDetailPanel
            badge={<Badge>Human access</Badge>}
            description="Create a scoped token and copy it once into your local environment."
            footer={
              <div className="text-xs leading-5 text-slate-500 dark:text-slate-400">
                Tokens inherit your role permissions. Scopes limit what the token
                can do, but they do not bypass governance roles.
              </div>
            }
            title="Issue personal token"
          >
            <TokenCreateForm
              defaultName="Jupyter migration token"
              errorMessage={errorMessage(createPersonalTokenMutation.error)}
              isSubmitting={createPersonalTokenMutation.isPending}
              onSubmit={handleCreatePersonalToken}
              submitLabel="Create personal token"
            />
            <TokenUsagePanel />
          </EntityDetailPanel>
        </MasterDetailLayout>
      ) : null}

      {activeSection === "service" ? (
        <MasterDetailLayout asideWidthClassName="xl:grid-cols-[minmax(0,1fr)_430px] 2xl:grid-cols-[minmax(0,1fr)_480px]">
          {canManageServiceAccounts ? (
            <SectionCard
              actions={
                <Badge className="bg-violet-50 text-violet-700 dark:bg-violet-950/40 dark:text-violet-200">
                  {serviceAccounts.length} identities
                </Badge>
              }
              contentClassName="space-y-5"
              description="Create and select bot identities for CI imports, scheduled sync jobs, and governance automation."
              title="Service account identities"
            >
              <ServiceAccountCreateForm
                errorMessage={errorMessage(createServiceAccountMutation.error)}
                isSubmitting={createServiceAccountMutation.isPending}
                onSubmit={handleCreateServiceAccount}
              />
              <ServiceAccountsTable
                accounts={serviceAccounts}
                isLoading={serviceAccountsQuery.isLoading}
                onSelect={setSelectedServiceAccountName}
                selectedName={selectedServiceAccountName}
              />
            </SectionCard>
          ) : (
            <SectionCard
              description="Ask an administrator to create bot identities for CI or scheduled automation."
              title="Service accounts"
            >
              <div className="rounded-xl border border-dashed border-slate-200 p-6 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
                Service accounts are visible to admins only. You can still create
                and revoke your own personal API tokens from the Personal tokens
                section.
              </div>
            </SectionCard>
          )}

          {canManageServiceAccounts ? (
            <ServiceAccountDetailsPanel
              account={selectedServiceAccount}
              createErrorMessage={errorMessage(createServiceTokenMutation.error)}
              isCreatingToken={createServiceTokenMutation.isPending}
              isToggling={updateServiceAccountMutation.isPending}
              isRevokingToken={revokeServiceTokenMutation.isPending}
              onCreateToken={handleCreateServiceToken}
              onRevokeToken={handleRevokeServiceToken}
              onToggleAccount={handleToggleServiceAccount}
              tokens={serviceTokens}
              tokensLoading={serviceAccountTokensQuery.isLoading}
            />
          ) : (
            <EntityDetailPanel
              badge={<Badge>Read only</Badge>}
              description="Automation keys require administrator access."
              title="Admin-managed automation"
            >
              <p className="text-sm leading-6 text-slate-600 dark:text-slate-300">
                Personal tokens are enough for local validation and export
                workflows. Service accounts are intended for CI, scheduled sync,
                and agent-owned migration jobs.
              </p>
            </EntityDetailPanel>
          )}
        </MasterDetailLayout>
      ) : null}
    </ConsolePage>
  );
}

function ApiAccessTabs({
  activeSection,
  canManageServiceAccounts,
  onChange,
}: {
  activeSection: ApiAccessSection;
  canManageServiceAccounts: boolean;
  onChange: (section: ApiAccessSection) => void;
}) {
  return (
    <div
      aria-label="API access sections"
      className="inline-flex w-full rounded-2xl border border-slate-200 bg-slate-100/80 p-1 dark:border-slate-800 dark:bg-slate-900/80 lg:w-auto"
      role="tablist"
    >
      {apiAccessSections.map((section) => (
        <button
          aria-selected={activeSection === section.id}
          className={`min-w-0 flex-1 rounded-xl px-3 py-2 text-left text-sm font-semibold transition-colors lg:min-w-44 ${
            activeSection === section.id
              ? "bg-white text-slate-950 shadow-sm dark:bg-slate-800 dark:text-slate-50"
              : "text-slate-500 hover:text-slate-950 dark:text-slate-400 dark:hover:text-slate-50"
          }`}
          key={section.id}
          onClick={() => onChange(section.id)}
          role="tab"
          type="button"
        >
          <span className="block truncate">{section.label}</span>
          <span className="mt-0.5 block truncate text-xs font-normal text-slate-500 dark:text-slate-400">
            {section.id === "service" && !canManageServiceAccounts
              ? "Admin only"
              : section.description}
          </span>
        </button>
      ))}
    </div>
  );
}

function TokenCreateForm({
  defaultName,
  disabledReason,
  errorMessage,
  isSubmitting,
  onSubmit,
  submitLabel,
}: {
  defaultName: string;
  disabledReason?: string | null;
  errorMessage: string | null;
  isSubmitting: boolean;
  onSubmit: (payload: ApiTokenCreateRequest) => Promise<void>;
  submitLabel: string;
}) {
  const [name, setName] = useState(defaultName);
  const [expiresInDays, setExpiresInDays] = useState("90");
  const [selectedScopes, setSelectedScopes] = useState<string[]>([
    "migration:validate",
    "migration:export",
  ]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) {
      return;
    }
    const parsedExpiresInDays = expiresInDays.trim()
      ? Number(expiresInDays)
      : null;
    await onSubmit({
      name: trimmedName,
      scopes: selectedScopes,
      expires_in_days:
        parsedExpiresInDays && Number.isFinite(parsedExpiresInDays)
          ? parsedExpiresInDays
          : null,
    });
    setName(defaultName);
    setExpiresInDays("90");
  }

  return (
    <form
      className="space-y-4 rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-900/50"
      onSubmit={handleSubmit}
    >
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_140px]">
        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300">
          Token name
          <Input
            aria-label={`${submitLabel} name`}
            className="mt-1"
            onChange={(event) => setName(event.target.value)}
            placeholder="Jupyter migration token"
            value={name}
          />
        </label>
        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300">
          Expires in days
          <Input
            aria-label={`${submitLabel} expiration days`}
            className="mt-1"
            min={1}
            onChange={(event) => setExpiresInDays(event.target.value)}
            type="number"
            value={expiresInDays}
          />
        </label>
      </div>
      <ScopePicker
        selectedScopes={selectedScopes}
        onChange={setSelectedScopes}
      />
      {disabledReason ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200">
          {disabledReason}
        </div>
      ) : null}
      {errorMessage ? <ErrorMessage message={errorMessage} /> : null}
      <Button
        className="w-full justify-center"
        disabled={Boolean(disabledReason) || isSubmitting || !name.trim()}
        type="submit"
      >
        {isSubmitting ? "Creating..." : submitLabel}
      </Button>
    </form>
  );
}

function ScopePicker({
  onChange,
  selectedScopes,
}: {
  onChange: (scopes: string[]) => void;
  selectedScopes: string[];
}) {
  function toggleScope(scope: string) {
    if (selectedScopes.includes(scope)) {
      onChange(selectedScopes.filter((item) => item !== scope));
      return;
    }
    onChange([...selectedScopes, scope]);
  }

  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium text-slate-700 dark:text-slate-300">
        Scopes
      </legend>
      <div className="grid gap-2 sm:grid-cols-3 xl:grid-cols-1 2xl:grid-cols-3">
        {migrationScopes.map((scope) => (
          <label
            key={scope}
            className="inline-flex min-w-0 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200"
          >
            <input
              checked={selectedScopes.includes(scope)}
              onChange={() => toggleScope(scope)}
              type="checkbox"
            />
            <span className="truncate">{scope}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function TokenTable({
  isLoading,
  onRevoke,
  revokeDisabled,
  tokens,
}: {
  isLoading: boolean;
  onRevoke: (tokenId: number) => void;
  revokeDisabled: boolean;
  tokens: ApiToken[];
}) {
  if (isLoading) {
    return <EmptyState message="Loading API tokens..." />;
  }
  if (tokens.length === 0) {
    return <EmptyState message="No API tokens yet." />;
  }
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-800">
      <div className="max-h-[520px] overflow-auto">
        <table className="w-full min-w-[840px] text-left text-sm">
          <thead className="sticky top-0 z-10 bg-slate-50 text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-950 dark:text-slate-400">
            <tr>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Prefix</th>
              <th className="px-4 py-3">Scopes</th>
              <th className="px-4 py-3">Expires</th>
              <th className="px-4 py-3">Last used</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {tokens.map((token) => (
              <tr
                className="bg-white transition-colors hover:bg-slate-50 dark:bg-slate-950 dark:hover:bg-slate-900"
                key={token.id}
              >
                <td className="px-4 py-3 font-medium text-slate-900 dark:text-slate-100">
                  {token.name}
                  <div className="mt-1 text-xs font-normal text-slate-500 dark:text-slate-400">
                    {token.owner_type === "service_account"
                      ? `service:${token.owner_name}`
                      : token.owner_name}
                  </div>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-slate-500 dark:text-slate-400">
                  {token.token_prefix}
                </td>
                <td className="px-4 py-3">
                  <ScopeBadges scopes={token.scopes} />
                </td>
                <td className="px-4 py-3 text-slate-500 dark:text-slate-400">
                  {formatDate(token.expires_at)}
                </td>
                <td className="px-4 py-3 text-slate-500 dark:text-slate-400">
                  {formatDate(token.last_used_at)}
                </td>
                <td className="px-4 py-3">
                  <TokenStatusBadge token={token} />
                </td>
                <td className="px-4 py-3 text-right">
                  <Button
                    disabled={revokeDisabled || isTokenInactive(token)}
                    onClick={() => onRevoke(token.id)}
                    type="button"
                    variant="secondary"
                  >
                    Revoke
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TokenUsagePanel() {
  return (
    <div className="space-y-4 text-sm text-slate-600 dark:text-slate-300">
      <div className="rounded-xl border border-slate-200 bg-slate-950 p-4 font-mono text-xs leading-6 text-slate-100 dark:border-slate-800">
        export SKEINRANK_API_TOKEN=&quot;sk_pat_...&quot;
        <br />
        poetry run skeinrank-migrate validate dictionary.json
      </div>
      <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          Available scopes
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          {migrationScopes.map((scope) => (
            <Badge key={scope}>{scope}</Badge>
          ))}
        </div>
      </div>
    </div>
  );
}

function ServiceAccountCreateForm({
  errorMessage,
  isSubmitting,
  onSubmit,
}: {
  errorMessage: string | null;
  isSubmitting: boolean;
  onSubmit: (payload: ServiceAccountCreateRequest) => Promise<void>;
}) {
  const [name, setName] = useState("migration-bot");
  const [displayName, setDisplayName] = useState("Migration Bot");
  const [description, setDescription] = useState(
    "Dictionary migration automation account",
  );
  const [role, setRole] = useState<UserRole>("admin");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedName = name.trim();
    if (!trimmedName) {
      return;
    }
    await onSubmit({
      name: trimmedName,
      display_name: displayName.trim() || null,
      description: description.trim() || null,
      role,
      is_active: true,
    });
    setName("migration-bot");
    setDisplayName("Migration Bot");
    setDescription("Dictionary migration automation account");
    setRole("admin");
  }

  return (
    <form
      className="space-y-4 rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-900/50"
      onSubmit={handleSubmit}
    >
      <div className="grid gap-3 md:grid-cols-2">
        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300">
          Service account name
          <Input
            aria-label="Service account name"
            className="mt-1"
            onChange={(event) => setName(event.target.value)}
            value={name}
          />
        </label>
        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300">
          Display name
          <Input
            aria-label="Service account display name"
            className="mt-1"
            onChange={(event) => setDisplayName(event.target.value)}
            value={displayName}
          />
        </label>
      </div>
      <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_160px]">
        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300">
          Description
          <Input
            aria-label="Service account description"
            className="mt-1"
            onChange={(event) => setDescription(event.target.value)}
            value={description}
          />
        </label>
        <label className="block text-sm font-medium text-slate-700 dark:text-slate-300">
          Role
          <select
            aria-label="Service account role"
            className="mt-1 h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm dark:border-slate-700 dark:bg-slate-950"
            onChange={(event) => setRole(event.target.value as UserRole)}
            value={role}
          >
            {userRoles.map((currentRole) => (
              <option key={currentRole} value={currentRole}>
                {currentRole}
              </option>
            ))}
          </select>
        </label>
      </div>
      {errorMessage ? <ErrorMessage message={errorMessage} /> : null}
      <Button disabled={isSubmitting || !name.trim()} type="submit">
        {isSubmitting ? "Creating..." : "Create service account"}
      </Button>
    </form>
  );
}

function ServiceAccountsTable({
  accounts,
  isLoading,
  onSelect,
  selectedName,
}: {
  accounts: ServiceAccount[];
  isLoading: boolean;
  onSelect: (name: string) => void;
  selectedName: string | null;
}) {
  if (isLoading) {
    return <EmptyState message="Loading service accounts..." />;
  }
  if (accounts.length === 0) {
    return <EmptyState message="No service accounts yet." />;
  }
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-800">
      <div className="max-h-[520px] overflow-auto">
        <table className="w-full min-w-[680px] text-left text-sm">
          <thead className="sticky top-0 z-10 bg-slate-50 text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-950 dark:text-slate-400">
            <tr>
              <th className="px-4 py-3">Account</th>
              <th className="px-4 py-3">Role</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Last used</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {accounts.map((account) => (
              <tr
                key={account.id}
                className={
                  selectedName === account.name
                    ? "bg-cyan-50/60 dark:bg-cyan-500/10"
                    : "bg-white hover:bg-slate-50 dark:bg-slate-950 dark:hover:bg-slate-900"
                }
              >
                <td className="px-4 py-3">
                  <button
                    className="text-left font-medium text-slate-900 hover:underline dark:text-slate-100"
                    onClick={() => onSelect(account.name)}
                    type="button"
                  >
                    {account.display_name || account.name}
                  </button>
                  <div className="text-xs text-slate-500 dark:text-slate-400">
                    {account.name}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <Badge>{account.role}</Badge>
                </td>
                <td className="px-4 py-3">
                  <ServiceAccountStatusBadge account={account} />
                </td>
                <td className="px-4 py-3 text-slate-500 dark:text-slate-400">
                  {formatDate(account.last_used_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ServiceAccountDetailsPanel({
  account,
  createErrorMessage,
  isCreatingToken,
  isRevokingToken,
  isToggling,
  onCreateToken,
  onRevokeToken,
  onToggleAccount,
  tokens,
  tokensLoading,
}: {
  account: ServiceAccount | null;
  createErrorMessage: string | null;
  isCreatingToken: boolean;
  isRevokingToken: boolean;
  isToggling: boolean;
  onCreateToken: (payload: ApiTokenCreateRequest) => Promise<void>;
  onRevokeToken: (tokenId: number) => void;
  onToggleAccount: (account: ServiceAccount) => void;
  tokens: ApiToken[];
  tokensLoading: boolean;
}) {
  if (!account) {
    return (
      <EntityDetailPanel
        badge={<Badge>Empty</Badge>}
        description="Select a service account to issue scoped automation tokens."
        title="Automation details"
      >
        <EmptyState message="Select or create a service account to manage its tokens." />
      </EntityDetailPanel>
    );
  }
  return (
    <EntityDetailPanel
      badge={<ServiceAccountStatusBadge account={account} />}
      description={account.description || "No description."}
      footer={
        <Button
          className="w-full justify-center"
          disabled={isToggling}
          onClick={() => onToggleAccount(account)}
          type="button"
          variant="secondary"
        >
          {account.is_active
            ? "Suspend service account"
            : "Reactivate service account"}
        </Button>
      }
      title={account.display_name || account.name}
    >
      <div className="grid gap-2 text-sm sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
        <DetailStat label="Account" value={account.name} />
        <DetailStat label="Role" value={account.role} />
        <DetailStat label="Last used" value={formatDate(account.last_used_at)} />
        <DetailStat label="Active tokens" value={countActiveTokens(tokens)} />
      </div>

      <div className="space-y-3">
        <div>
          <h4 className="text-sm font-semibold text-slate-800 dark:text-slate-200">
            Create service token
          </h4>
          <p className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">
            Issue a one-time visible token for this bot identity.
          </p>
        </div>
        <TokenCreateForm
          defaultName="CI import token"
          disabledReason={
            account.is_active
              ? null
              : "Reactivate this service account before creating new tokens."
          }
          errorMessage={createErrorMessage}
          isSubmitting={isCreatingToken}
          onSubmit={onCreateToken}
          submitLabel="Create service token"
        />
      </div>

      <div className="space-y-3">
        <h4 className="text-sm font-semibold text-slate-800 dark:text-slate-200">
          Service account tokens
        </h4>
        <TokenCards
          isLoading={tokensLoading}
          onRevoke={onRevokeToken}
          revokeDisabled={isRevokingToken}
          tokens={tokens}
        />
      </div>
    </EntityDetailPanel>
  );
}

function TokenCards({
  isLoading,
  onRevoke,
  revokeDisabled,
  tokens,
}: {
  isLoading: boolean;
  onRevoke: (tokenId: number) => void;
  revokeDisabled: boolean;
  tokens: ApiToken[];
}) {
  if (isLoading) {
    return <EmptyState message="Loading service account tokens..." />;
  }
  if (tokens.length === 0) {
    return <EmptyState message="No service account tokens yet." />;
  }
  return (
    <div className="space-y-2">
      {tokens.map((token) => (
        <div
          className="rounded-2xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-900/50"
          key={token.id}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">
                {token.name}
              </div>
              <div className="mt-1 font-mono text-xs text-slate-500 dark:text-slate-400">
                {token.token_prefix}
              </div>
            </div>
            <TokenStatusBadge token={token} />
          </div>
          <div className="mt-3">
            <ScopeBadges scopes={token.scopes} />
          </div>
          <div className="mt-3 flex items-center justify-between gap-3 text-xs text-slate-500 dark:text-slate-400">
            <span>Expires {formatDate(token.expires_at)}</span>
            <Button
              disabled={revokeDisabled || isTokenInactive(token)}
              onClick={() => onRevoke(token.id)}
              type="button"
              variant="secondary"
            >
              Revoke
            </Button>
          </div>
        </div>
      ))}
    </div>
  );
}

function CopyOnceTokenPanel({
  onDismiss,
  token,
}: {
  onDismiss: () => void;
  token: ApiTokenCreateResponse;
}) {
  async function handleCopy() {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      await navigator.clipboard.writeText(token.access_token);
    }
  }

  return (
    <SectionCard
      className="border-amber-200 bg-amber-50 dark:border-amber-900/60 dark:bg-amber-950/30"
      description="This token is shown only once. Store it securely before closing this panel."
      title="Copy this API token now"
    >
      <div className="space-y-3">
        <div
          className="break-all rounded-xl border border-amber-200 bg-white p-3 font-mono text-sm text-amber-950 dark:border-amber-900/60 dark:bg-slate-950 dark:text-amber-100"
          data-testid="copy-once-token"
        >
          {token.access_token}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={handleCopy} type="button" variant="secondary">
            Copy token
          </Button>
          <Button onClick={onDismiss} type="button" variant="ghost">
            I have saved it
          </Button>
        </div>
      </div>
    </SectionCard>
  );
}

function DetailStat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-900/50">
      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {label}
      </div>
      <div className="mt-1 truncate font-medium text-slate-950 dark:text-slate-50">
        {value}
      </div>
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
      {message}
    </div>
  );
}

function ScopeBadges({ scopes }: { scopes: string[] }) {
  if (scopes.length === 0) {
    return <span className="text-slate-400">No scopes</span>;
  }
  return (
    <div className="flex flex-wrap gap-1">
      {scopes.map((scope) => (
        <Badge key={scope}>{scope}</Badge>
      ))}
    </div>
  );
}

function TokenStatusBadge({ token }: { token: ApiToken }) {
  if (token.revoked_at) {
    return (
      <Badge className="bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-200">
        Revoked
      </Badge>
    );
  }
  if (token.expires_at && new Date(token.expires_at).getTime() < Date.now()) {
    return (
      <Badge className="bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-200">
        Expired
      </Badge>
    );
  }
  return (
    <Badge className="bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-200">
      Active
    </Badge>
  );
}

function ServiceAccountStatusBadge({ account }: { account: ServiceAccount }) {
  return account.is_active ? (
    <Badge className="bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-200">
      Active
    </Badge>
  ) : (
    <Badge className="bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-200">
      Suspended
    </Badge>
  );
}

function ErrorMessage({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200">
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

function isTokenInactive(token: ApiToken) {
  return (
    Boolean(token.revoked_at) ||
    Boolean(
      token.expires_at && new Date(token.expires_at).getTime() < Date.now(),
    )
  );
}

function countActiveTokens(tokens: ApiToken[]) {
  return tokens.filter((token) => !isTokenInactive(token)).length;
}

function formatDate(value: string | null) {
  if (!value) {
    return "Never";
  }
  return new Date(value).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
  });
}

function upsertPersonalToken(
  queryClient: ReturnType<typeof useQueryClient>,
  token: ApiToken,
) {
  queryClient.setQueryData<ApiToken[]>(
    ["auth", "api-tokens", "personal"],
    (tokens = []) => [
      token,
      ...tokens.filter((current) => current.id !== token.id),
    ],
  );
}

function markPersonalTokenRevoked(
  queryClient: ReturnType<typeof useQueryClient>,
  tokenId: number,
) {
  const revokedAt = new Date().toISOString();
  queryClient.setQueryData<ApiToken[]>(
    ["auth", "api-tokens", "personal"],
    (tokens = []) =>
      tokens.map((token) =>
        token.id === tokenId ? { ...token, revoked_at: revokedAt } : token,
      ),
  );
}

function upsertServiceAccount(
  queryClient: ReturnType<typeof useQueryClient>,
  account: ServiceAccount,
) {
  queryClient.setQueryData<ServiceAccount[]>(
    ["auth", "service-accounts"],
    (accounts = []) =>
      [
        account,
        ...accounts.filter((current) => current.id !== account.id),
      ].sort((left, right) =>
        left.normalized_name.localeCompare(right.normalized_name),
      ),
  );
}

function upsertServiceAccountToken(
  queryClient: ReturnType<typeof useQueryClient>,
  accountName: string,
  token: ApiToken,
) {
  queryClient.setQueryData<ApiToken[]>(
    ["auth", "service-accounts", accountName, "tokens"],
    (tokens = []) => [
      token,
      ...tokens.filter((current) => current.id !== token.id),
    ],
  );
}

function markServiceTokenRevoked(
  queryClient: ReturnType<typeof useQueryClient>,
  accountName: string,
  tokenId: number,
) {
  const revokedAt = new Date().toISOString();
  queryClient.setQueryData<ApiToken[]>(
    ["auth", "service-accounts", accountName, "tokens"],
    (tokens = []) =>
      tokens.map((token) =>
        token.id === tokenId ? { ...token, revoked_at: revokedAt } : token,
      ),
  );
}
