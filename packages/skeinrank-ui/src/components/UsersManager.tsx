import { type FormEvent, type ReactNode, useEffect, useState } from "react";
import { KeyRound, ShieldAlert, UserCheck, UserPlus, Users } from "lucide-react";

import type { AuthUser, UserCreateRequest, UserRole, UserStatus, UserUpdateRequest } from "../types";
import {
  ConsolePage,
  EntityDetailPanel,
  MasterDetailLayout,
  MetricPill,
  SectionCard,
  WorkspaceHeader,
} from "./layout/ConsolePrimitives";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Input } from "./ui/input";

const USER_ROLES: UserRole[] = ["admin", "moderator", "contributor"];
const USER_STATUSES: UserStatus[] = ["active", "suspended", "deactivated"];

const SELECTED_USER_FORM_ID = "selected-user-form";

type UsersManagerProps = {
  createErrorMessage?: string | null;
  deleteErrorMessage?: string | null;
  isCreating?: boolean;
  isDeleting?: boolean;
  isLoading?: boolean;
  isRevokingTokens?: boolean;
  isUpdating?: boolean;
  isUpdatingStatus?: boolean;
  loadErrorMessage?: string | null;
  onCreateUser: (payload: UserCreateRequest) => Promise<void> | void;
  onDeleteUser: (username: string) => Promise<void> | void;
  onRevokeUserApiTokens: (username: string) => Promise<void> | void;
  onUpdateUser: (username: string, payload: UserUpdateRequest) => Promise<void> | void;
  onUpdateUserStatus: (username: string, status: UserStatus) => Promise<void> | void;
  revokeTokensErrorMessage?: string | null;
  updateErrorMessage?: string | null;
  updateStatusErrorMessage?: string | null;
  users: AuthUser[];
};

export function UsersManager({
  createErrorMessage,
  deleteErrorMessage,
  isCreating = false,
  isDeleting = false,
  isRevokingTokens = false,
  isLoading = false,
  isUpdating = false,
  isUpdatingStatus = false,
  loadErrorMessage,
  onCreateUser,
  onDeleteUser,
  onRevokeUserApiTokens,
  onUpdateUser,
  onUpdateUserStatus,
  revokeTokensErrorMessage,
  updateErrorMessage,
  updateStatusErrorMessage,
  users,
}: UsersManagerProps) {
  const [newUsername, setNewUsername] = useState("");
  const [newDisplayName, setNewDisplayName] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState<UserRole>("contributor");
  const [selectedUsername, setSelectedUsername] = useState<string | null>(null);
  const [editUsername, setEditUsername] = useState("");
  const [editDisplayName, setEditDisplayName] = useState("");
  const [editPassword, setEditPassword] = useState("");
  const [editRole, setEditRole] = useState<UserRole>("contributor");

  const selectedUser = users.find((user) => user.username === selectedUsername) ?? null;
  const canCreate = newUsername.trim().length > 0 && newPassword.length > 0 && !isCreating;
  const canUpdate = Boolean(selectedUser) && editUsername.trim().length > 0 && !isUpdating;
  const activeCount = users.filter((user) => user.status === "active").length;
  const suspendedCount = users.filter((user) => user.status === "suspended").length;
  const deactivatedCount = users.filter((user) => user.status === "deactivated").length;
  const adminCount = users.filter((user) => user.role === "admin").length;

  useEffect(() => {
    if (users.length === 0) {
      setSelectedUsername(null);
      return;
    }

    if (!selectedUsername || !users.some((user) => user.username === selectedUsername)) {
      setSelectedUsername(users[0].username);
    }
  }, [selectedUsername, users]);

  useEffect(() => {
    if (!selectedUser) {
      setEditUsername("");
      setEditDisplayName("");
      setEditPassword("");
      setEditRole("contributor");
      return;
    }
    setEditUsername(selectedUser.username);
    setEditDisplayName(selectedUser.display_name ?? "");
    setEditPassword("");
    setEditRole(selectedUser.role);
  }, [selectedUser?.id, selectedUser?.display_name, selectedUser?.role, selectedUser?.username]);

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canCreate) {
      return;
    }

    try {
      await onCreateUser({
        username: newUsername.trim(),
        password: newPassword,
        display_name: newDisplayName.trim() || null,
        role: newRole,
        status: "active",
      });
      setNewUsername("");
      setNewDisplayName("");
      setNewPassword("");
      setNewRole("contributor");
    } catch {
      // Parent mutation owns user-facing error rendering.
    }
  }

  async function handleUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedUser || !canUpdate) {
      return;
    }

    try {
      await onUpdateUser(selectedUser.username, {
        username: editUsername.trim(),
        display_name: editDisplayName.trim() || null,
        password: editPassword || null,
        role: editRole,
      });
      setEditPassword("");
    } catch {
      // Parent mutation owns user-facing error rendering.
    }
  }

  async function handleStatusChange(username: string, nextStatus: UserStatus) {
    const verb = nextStatus === "active" ? "reactivate" : nextStatus;
    const confirmed = window.confirm(
      `${capitalize(verb)} user "${username}"? ${statusConfirmation(nextStatus)}`,
    );
    if (!confirmed) {
      return;
    }

    try {
      await onUpdateUserStatus(username, nextStatus);
    } catch {
      // Parent mutation owns user-facing error rendering.
    }
  }

  async function handleRevokeTokens(username: string) {
    const confirmed = window.confirm(
      `Revoke all personal API tokens for "${username}"? Existing scripts and notebooks using these tokens will stop working.`,
    );
    if (!confirmed) {
      return;
    }

    try {
      await onRevokeUserApiTokens(username);
    } catch {
      // Parent mutation owns user-facing error rendering.
    }
  }

  async function handleDelete(username: string) {
    const confirmed = window.confirm(`Delete user "${username}"? This will remove the account and revoke their governance access.`);
    if (!confirmed) {
      return;
    }

    try {
      await onDeleteUser(username);
      if (selectedUsername === username) {
        setSelectedUsername(null);
      }
    } catch {
      // Parent mutation owns user-facing error rendering.
    }
  }

  return (
    <ConsolePage className="space-y-4">
      <WorkspaceHeader
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={suspendedCount > 0 ? "suspended" : "active"}>
              {suspendedCount > 0 ? `${suspendedCount} suspended` : "Access healthy"}
            </StatusBadge>
            <Badge className="bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">Local users</Badge>
          </div>
        }
        description="Manage local governance accounts, roles, account status, and personal API-token access from one review-oriented workspace."
        eyebrow="Users and roles"
        meta={
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MetricPill helper="Local governance accounts" icon={Users} label="Users" tone="cyan" value={users.length} />
            <MetricPill helper="Can sign in and use tokens" icon={UserCheck} label="Active" tone="emerald" value={activeCount} />
            <MetricPill helper="Temporarily blocked" icon={ShieldAlert} label="Suspended" tone={suspendedCount > 0 ? "amber" : "slate"} value={suspendedCount} />
            <MetricPill helper="Admin role assignments" icon={KeyRound} label="Admins" tone="violet" value={adminCount} />
          </div>
        }
        title="Access management control plane"
      />

      <MasterDetailLayout asideWidthClassName="xl:grid-cols-[minmax(0,1fr)_420px] 2xl:grid-cols-[minmax(0,1fr)_440px]">
        <div className="space-y-4">
          <SectionCard
            actions={<Badge className="bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">{users.length} accounts</Badge>}
            contentClassName="space-y-4"
            description="Select a user to inspect role, status, authentication state, and offboarding actions."
            title="Governance users"
          >
            {loadErrorMessage ? <InlineError message={loadErrorMessage} /> : null}
            {isLoading ? (
              <p className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">Loading users...</p>
            ) : users.length > 0 ? (
              <div className="max-h-[520px] overflow-auto rounded-2xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
                <table className="min-w-full divide-y divide-slate-100 text-sm dark:divide-slate-800">
                  <thead className="sticky top-0 z-10 bg-slate-50/95 text-xs uppercase tracking-[0.16em] text-slate-500 backdrop-blur dark:bg-slate-900/95 dark:text-slate-400">
                    <tr>
                      <th className="px-4 py-3 text-left font-semibold">Identity</th>
                      <th className="px-4 py-3 text-left font-semibold">Role</th>
                      <th className="px-4 py-3 text-left font-semibold">Status</th>
                      <th className="px-4 py-3 text-left font-semibold">Last login</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                    {users.map((user) => {
                      const selected = selectedUser?.username === user.username;
                      return (
                        <tr
                          className={selected ? "bg-cyan-50/60 dark:bg-cyan-500/10" : "bg-white dark:bg-slate-950"}
                          key={user.id}
                        >
                          <td className="px-4 py-3 align-top">
                            <button
                              className="group block max-w-[260px] text-left"
                              onClick={() => setSelectedUsername(user.username)}
                              type="button"
                            >
                              <span className="block truncate font-medium text-slate-950 group-hover:text-cyan-700 dark:text-slate-50 dark:group-hover:text-cyan-200">
                                {user.username}
                              </span>
                              <span className="mt-1 block truncate text-xs text-slate-500 dark:text-slate-400">
                                {user.display_name || "No display name"}
                              </span>
                            </button>
                          </td>
                          <td className="px-4 py-3 align-top">
                            <RoleBadge role={user.role} />
                          </td>
                          <td className="px-4 py-3 align-top">
                            <StatusBadge status={user.status} />
                          </td>
                          <td className="px-4 py-3 align-top text-xs text-slate-500 dark:text-slate-400">
                            {formatDate(user.last_login_at)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
                No users found. Bootstrap an admin user or create a local governance user.
              </p>
            )}
          </SectionCard>

          <SectionCard
            actions={<UserPlus className="h-5 w-5 text-cyan-600 dark:text-cyan-300" />}
            contentClassName="space-y-4"
            description="Create a local user with a temporary password and least-privilege role."
            title="Create user"
          >
            <form className="grid gap-3 lg:grid-cols-2" onSubmit={handleCreate}>
              <label className="space-y-1.5">
                <span className="text-sm font-medium text-slate-700 dark:text-slate-200">New username</span>
                <Input onChange={(event) => setNewUsername(event.target.value)} placeholder="alex" value={newUsername} />
              </label>
              <label className="space-y-1.5">
                <span className="text-sm font-medium text-slate-700 dark:text-slate-200">New display name</span>
                <Input onChange={(event) => setNewDisplayName(event.target.value)} placeholder="Alex Kim" value={newDisplayName} />
              </label>
              <label className="space-y-1.5">
                <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Temporary password</span>
                <Input onChange={(event) => setNewPassword(event.target.value)} placeholder="change-me" type="password" value={newPassword} />
              </label>
              <label className="space-y-1.5">
                <span className="text-sm font-medium text-slate-700 dark:text-slate-200">New user role</span>
                <Select value={newRole} onChange={(value) => setNewRole(value as UserRole)} options={USER_ROLES} />
              </label>
              <div className="space-y-3 lg:col-span-2">
                {createErrorMessage ? <InlineError message={createErrorMessage} /> : null}
                <Button disabled={!canCreate} type="submit">
                  {isCreating ? "Creating..." : "Create user"}
                </Button>
              </div>
            </form>
          </SectionCard>
        </div>

        <div className="space-y-4">
          <EntityDetailPanel
            badge={selectedUser ? <StatusBadge status={selectedUser.status} /> : null}
            description={selectedUser ? selectedUser.display_name || "No display name configured" : "Select a row to edit account controls."}
            footer={
              selectedUser ? (
                <div className="flex flex-wrap gap-2">
                  <Button disabled={!canUpdate} form={SELECTED_USER_FORM_ID} type="submit">
                    {isUpdating ? "Saving..." : "Save user"}
                  </Button>
                  {selectedUser.status !== "active" ? (
                    <Button disabled={isUpdatingStatus} onClick={() => handleStatusChange(selectedUser.username, "active")} type="button" variant="secondary">
                      {isUpdatingStatus ? "Updating..." : "Reactivate"}
                    </Button>
                  ) : (
                    <Button disabled={isUpdatingStatus} onClick={() => handleStatusChange(selectedUser.username, "suspended")} type="button" variant="secondary">
                      {isUpdatingStatus ? "Updating..." : "Suspend"}
                    </Button>
                  )}
                  {selectedUser.status !== "deactivated" ? (
                    <Button disabled={isUpdatingStatus} onClick={() => handleStatusChange(selectedUser.username, "deactivated")} type="button" variant="secondary">
                      Deactivate
                    </Button>
                  ) : null}
                  <Button disabled={isRevokingTokens} onClick={() => handleRevokeTokens(selectedUser.username)} type="button" variant="secondary">
                    {isRevokingTokens ? "Revoking..." : "Revoke all API tokens"}
                  </Button>
                  <Button disabled={isDeleting} onClick={() => handleDelete(selectedUser.username)} type="button" variant="ghost">
                    {isDeleting ? "Deleting..." : "Delete user"}
                  </Button>
                </div>
              ) : null
            }
            title={selectedUser ? selectedUser.username : "Selected user"}
          >
            {selectedUser ? (
              <form className="space-y-4" id={SELECTED_USER_FORM_ID} onSubmit={handleUpdate}>
                <div className="grid grid-cols-2 gap-3">
                  <DetailStat label="Role" value={<RoleBadge role={selectedUser.role} />} />
                  <DetailStat label="Status" value={<StatusBadge status={selectedUser.status} />} />
                  <DetailStat label="Created" value={formatDate(selectedUser.created_at)} />
                  <DetailStat label="Updated" value={formatDate(selectedUser.updated_at)} />
                </div>
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-900/60">
                  <div className="text-sm font-medium text-slate-950 dark:text-slate-50">Account controls</div>
                  <div className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">
                    Suspended and deactivated users cannot sign in or authenticate with personal API tokens. Token revocation disables existing scripts without deleting the account.
                  </div>
                </div>
                <label className="space-y-1.5">
                  <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Username</span>
                  <Input onChange={(event) => setEditUsername(event.target.value)} value={editUsername} />
                </label>
                <label className="space-y-1.5">
                  <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Display name</span>
                  <Input onChange={(event) => setEditDisplayName(event.target.value)} placeholder="Optional display name" value={editDisplayName} />
                </label>
                <label className="space-y-1.5">
                  <span className="text-sm font-medium text-slate-700 dark:text-slate-200">New password</span>
                  <Input onChange={(event) => setEditPassword(event.target.value)} placeholder="Leave empty to keep current password" type="password" value={editPassword} />
                </label>
                <label className="space-y-1.5">
                  <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Role</span>
                  <Select value={editRole} onChange={(value) => setEditRole(value as UserRole)} options={USER_ROLES} />
                </label>
                {updateErrorMessage ? <InlineError message={updateErrorMessage} /> : null}
                {updateStatusErrorMessage ? <InlineError message={updateStatusErrorMessage} /> : null}
                {revokeTokensErrorMessage ? <InlineError message={revokeTokensErrorMessage} /> : null}
                {deleteErrorMessage ? <InlineError message={deleteErrorMessage} /> : null}
              </form>
            ) : (
              <p className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
                Select a user to update their role, display name, account status, password, or API-token access.
              </p>
            )}
          </EntityDetailPanel>

          <SectionCard
            actions={<ShieldAlert className="h-5 w-5 text-amber-600 dark:text-amber-300" />}
            contentClassName="space-y-3 text-sm text-slate-600 dark:text-slate-300"
            description="Backend-enforced account controls."
            title="Status semantics"
          >
            <StatusDefinition label="Active" value="User can sign in and use personal API tokens." />
            <StatusDefinition label="Suspended" value="Temporary block. The account can be reactivated later." />
            <StatusDefinition label="Deactivated" value="Closed account state for offboarding or permanent access removal." />
            <StatusDefinition label="Revoke all API tokens" value="Disables existing personal tokens without deleting the user." />
            <div className="pt-2 text-xs text-slate-500 dark:text-slate-400">Supported statuses: {USER_STATUSES.join(", ")}.</div>
          </SectionCard>
        </div>
      </MasterDetailLayout>
    </ConsolePage>
  );
}

function StatusBadge({ children, status }: { children?: string; status: UserStatus }) {
  const className =
    status === "active"
      ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200"
      : status === "suspended"
        ? "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-200"
        : "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-200";
  return <Badge className={className}>{children ?? status}</Badge>;
}

function RoleBadge({ role }: { role: UserRole }) {
  const className =
    role === "admin"
      ? "bg-violet-50 text-violet-700 dark:bg-violet-950 dark:text-violet-200"
      : role === "moderator"
        ? "bg-cyan-50 text-cyan-700 dark:bg-cyan-950 dark:text-cyan-200"
        : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300";
  return <Badge className={className}>{role}</Badge>;
}

function DetailStat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-950">
      <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-slate-400">{label}</div>
      <div className="mt-2 min-h-6 text-sm font-medium text-slate-950 dark:text-slate-50">{value}</div>
    </div>
  );
}

function StatusDefinition({ label, value }: { label: string; value: string }) {
  return (
    <p>
      <strong className="text-slate-950 dark:text-slate-50">{label}:</strong> {value}
    </p>
  );
}

function Select({ onChange, options, value }: { onChange: (value: string) => void; options: readonly string[]; value: string }) {
  return (
    <select
      className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:focus:border-slate-500 dark:focus:ring-slate-800"
      onChange={(event) => onChange(event.target.value)}
      value={value}
    >
      {options.map((option) => (
        <option key={option} value={option}>
          {option}
        </option>
      ))}
    </select>
  );
}

function InlineError({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200">
      {message}
    </div>
  );
}

function formatDate(value: string | null | undefined) {
  if (!value) {
    return "Never";
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
  }).format(new Date(value));
}

function capitalize(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function statusConfirmation(status: UserStatus) {
  if (status === "active") {
    return "The user will be able to sign in and use non-revoked personal API tokens again.";
  }
  if (status === "suspended") {
    return "This will temporarily block UI login and personal API-token authentication.";
  }
  return "This will close the account and block UI login and personal API-token authentication.";
}
