import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useMemo, useState } from "react";

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
    <div className="space-y-6">
      <section className="grid gap-4 md:grid-cols-3">
        <StatCard
          description="Tokens owned by your signed-in user."
          title="My active tokens"
          value={String(countActiveTokens(personalTokensQuery.data ?? []))}
        />
        <StatCard
          description="Available token permissions for migration workflows."
          title="Migration scopes"
          value="3"
        />
        <StatCard
          description="Admin-managed non-human identities."
          title="Service accounts"
          value={
            canManageServiceAccounts
              ? String(serviceAccountsQuery.data?.length ?? 0)
              : "Admin only"
          }
        />
      </section>

      {copyOnceToken ? (
        <CopyOnceTokenPanel
          token={copyOnceToken.token}
          onDismiss={() => setCopyOnceToken(null)}
        />
      ) : null}

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(360px,460px)]">
        <Card>
          <CardHeader>
            <CardTitle>My API tokens</CardTitle>
            <CardDescription>
              Create personal bearer tokens for Jupyter, CLI scripts, and
              migration tooling. Tokens are shown only once.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <TokenCreateForm
              defaultName="Jupyter migration token"
              errorMessage={errorMessage(createPersonalTokenMutation.error)}
              isSubmitting={createPersonalTokenMutation.isPending}
              onSubmit={handleCreatePersonalToken}
              submitLabel="Create personal token"
            />
            <TokenTable
              isLoading={personalTokensQuery.isLoading}
              onRevoke={handleRevokePersonalToken}
              revokeDisabled={revokePersonalTokenMutation.isPending}
              tokens={personalTokensQuery.data ?? []}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>API token usage</CardTitle>
            <CardDescription>
              Use personal tokens with the migration CLI or direct HTTP
              requests.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-sm text-slate-600 dark:text-slate-300">
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 font-mono text-xs text-slate-700 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200">
              export SKEINRANK_API_TOKEN=&quot;sk_pat_...&quot;
              <br />
              poetry run skeinrank-migrate validate dictionary.json
            </div>
            <p>
              Scopes limit what the token can do. Your user role is still
              checked by the API, so write scopes do not bypass governance
              roles.
            </p>
            <div className="flex flex-wrap gap-2">
              {migrationScopes.map((scope) => (
                <Badge key={scope}>{scope}</Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>Service accounts</CardTitle>
          <CardDescription>
            Admin-managed bot identities for CI imports, scheduled sync jobs,
            and dictionary migration automation.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {canManageServiceAccounts ? (
            <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(380px,480px)]">
              <div className="space-y-5">
                <ServiceAccountCreateForm
                  errorMessage={errorMessage(
                    createServiceAccountMutation.error,
                  )}
                  isSubmitting={createServiceAccountMutation.isPending}
                  onSubmit={handleCreateServiceAccount}
                />
                <ServiceAccountsTable
                  accounts={serviceAccountsQuery.data ?? []}
                  isLoading={serviceAccountsQuery.isLoading}
                  onSelect={setSelectedServiceAccountName}
                  selectedName={selectedServiceAccountName}
                />
              </div>
              <ServiceAccountDetailsPanel
                account={selectedServiceAccount}
                createErrorMessage={errorMessage(
                  createServiceTokenMutation.error,
                )}
                isCreatingToken={createServiceTokenMutation.isPending}
                isToggling={updateServiceAccountMutation.isPending}
                isRevokingToken={revokeServiceTokenMutation.isPending}
                onCreateToken={handleCreateServiceToken}
                onRevokeToken={handleRevokeServiceToken}
                onToggleAccount={handleToggleServiceAccount}
                tokens={serviceAccountTokensQuery.data ?? []}
                tokensLoading={serviceAccountTokensQuery.isLoading}
              />
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-slate-200 p-6 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
              Service accounts are visible to admins only. You can still create
              and revoke your own personal API tokens above.
            </div>
          )}
        </CardContent>
      </Card>
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
      className="space-y-4 rounded-2xl border border-slate-100 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950"
      onSubmit={handleSubmit}
    >
      <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_140px]">
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
      <Button disabled={Boolean(disabledReason) || isSubmitting || !name.trim()} type="submit">
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
      <div className="flex flex-wrap gap-2">
        {migrationScopes.map((scope) => (
          <label
            key={scope}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200"
          >
            <input
              checked={selectedScopes.includes(scope)}
              onChange={() => toggleScope(scope)}
              type="checkbox"
            />
            {scope}
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
    return (
      <div className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
        Loading API tokens...
      </div>
    );
  }
  if (tokens.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
        No API tokens yet.
      </div>
    );
  }
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-800">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-950 dark:text-slate-400">
          <tr>
            <th className="px-4 py-3">Name</th>
            <th className="px-4 py-3">Prefix</th>
            <th className="px-4 py-3">Scopes</th>
            <th className="px-4 py-3">Expires</th>
            <th className="px-4 py-3">Last used</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
          {tokens.map((token) => (
            <tr key={token.id}>
              <td className="px-4 py-3 font-medium text-slate-900 dark:text-slate-100">
                {token.name}
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
              <td className="px-4 py-3">
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
      className="space-y-4 rounded-2xl border border-slate-100 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950"
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
    return (
      <div className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
        Loading service accounts...
      </div>
    );
  }
  if (accounts.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
        No service accounts yet.
      </div>
    );
  }
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 dark:border-slate-800">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500 dark:bg-slate-950 dark:text-slate-400">
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
                  ? "bg-slate-50 dark:bg-slate-950"
                  : undefined
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
      <div className="rounded-2xl border border-dashed border-slate-200 p-6 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
        Select or create a service account to manage its tokens.
      </div>
    );
  }
  return (
    <div className="space-y-5 rounded-2xl border border-slate-200 p-4 dark:border-slate-800">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-slate-950 dark:text-slate-50">
            {account.display_name || account.name}
          </h3>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            {account.description || "No description."}
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            <Badge>{account.name}</Badge>
            <Badge>{account.role}</Badge>
            <ServiceAccountStatusBadge account={account} />
          </div>
        </div>
        <Button
          disabled={isToggling}
          onClick={() => onToggleAccount(account)}
          type="button"
          variant="secondary"
        >
          {account.is_active
            ? "Suspend service account"
            : "Reactivate service account"}
        </Button>
      </div>

      <div>
        <h4 className="text-sm font-semibold text-slate-800 dark:text-slate-200">
          Create service token
        </h4>
        <div className="mt-3">
          <TokenCreateForm
            defaultName="CI import token"
            disabledReason={account.is_active ? null : "Reactivate this service account before creating new tokens."}
            errorMessage={createErrorMessage}
            isSubmitting={isCreatingToken}
            onSubmit={onCreateToken}
            submitLabel="Create service token"
          />
        </div>
      </div>

      <div>
        <h4 className="mb-3 text-sm font-semibold text-slate-800 dark:text-slate-200">
          Service account tokens
        </h4>
        <TokenTable
          isLoading={tokensLoading}
          onRevoke={onRevokeToken}
          revokeDisabled={isRevokingToken}
          tokens={tokens}
        />
      </div>
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
    <Card className="border-amber-200 bg-amber-50 dark:border-amber-900/60 dark:bg-amber-950/30">
      <CardHeader>
        <CardTitle>Copy this API token now</CardTitle>
        <CardDescription>
          This token is shown only once. Store it securely before closing this
          panel.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div
          className="rounded-xl border border-amber-200 bg-white p-3 font-mono text-sm text-amber-950 dark:border-amber-900/60 dark:bg-slate-950 dark:text-amber-100"
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
      </CardContent>
    </Card>
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

function StatCard({
  description,
  title,
  value,
}: {
  description: string;
  title: string;
  value: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-semibold tracking-tight">{value}</div>
      </CardContent>
    </Card>
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
