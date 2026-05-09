import { type FormEvent, useEffect, useState } from "react";
import { ShieldAlert, Users } from "lucide-react";

import type { AuthUser, UserCreateRequest, UserRole, UserStatus, UserUpdateRequest } from "../types";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Input } from "./ui/input";

const USER_ROLES: UserRole[] = ["admin", "moderator", "contributor"];
const USER_STATUSES: UserStatus[] = ["active", "suspended", "deactivated"];

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
  const [editingUsername, setEditingUsername] = useState<string | null>(null);
  const [editUsername, setEditUsername] = useState("");
  const [editDisplayName, setEditDisplayName] = useState("");
  const [editPassword, setEditPassword] = useState("");
  const [editRole, setEditRole] = useState<UserRole>("contributor");

  const editingUser = users.find((user) => user.username === editingUsername) ?? null;
  const canCreate = newUsername.trim().length > 0 && newPassword.length > 0 && !isCreating;
  const canUpdate = Boolean(editingUser) && editUsername.trim().length > 0 && !isUpdating;
  const activeCount = users.filter((user) => user.status === "active").length;
  const suspendedCount = users.filter((user) => user.status === "suspended").length;
  const deactivatedCount = users.filter((user) => user.status === "deactivated").length;

  useEffect(() => {
    if (!editingUser) {
      return;
    }
    setEditUsername(editingUser.username);
    setEditDisplayName(editingUser.display_name ?? "");
    setEditPassword("");
    setEditRole(editingUser.role);
  }, [editingUser?.id, editingUser?.display_name, editingUser?.role, editingUser?.username]);

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
    if (!editingUser || !canUpdate) {
      return;
    }

    try {
      await onUpdateUser(editingUser.username, {
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
      if (editingUsername === username) {
        setEditingUsername(null);
      }
    } catch {
      // Parent mutation owns user-facing error rendering.
    }
  }

  return (
    <div className="space-y-6">
      <section className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader>
            <CardTitle>Users</CardTitle>
            <CardDescription>Local governance accounts.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">{users.length}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Active</CardTitle>
            <CardDescription>Can sign in and use API tokens.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">{activeCount}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Suspended</CardTitle>
            <CardDescription>Temporarily blocked accounts.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">{suspendedCount}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Deactivated</CardTitle>
            <CardDescription>Closed user accounts.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">{deactivatedCount}</div>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Users className="h-5 w-5" />
                <div>
                  <CardTitle>Governance users</CardTitle>
                  <CardDescription>Manage account status, roles, and personal API-token access.</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-5">
              {loadErrorMessage ? <InlineError message={loadErrorMessage} /> : null}
              {isLoading ? (
                <p className="text-sm text-slate-500 dark:text-slate-400">Loading users...</p>
              ) : users.length > 0 ? (
                <div className="space-y-2">
                  {users.map((user) => (
                    <button
                      className={`w-full rounded-xl border p-4 text-left transition-colors ${
                        editingUsername === user.username
                          ? "border-slate-950 bg-slate-50 dark:border-slate-100 dark:bg-slate-900"
                          : "border-slate-200 bg-white hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-950 dark:hover:bg-slate-900"
                      }`}
                      key={user.id}
                      onClick={() => setEditingUsername(user.username)}
                      type="button"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <div className="font-medium text-slate-950 dark:text-slate-50">{user.username}</div>
                          <div className="text-sm text-slate-500 dark:text-slate-400">{user.display_name || "No display name"}</div>
                        </div>
                        <div className="flex gap-2">
                          <Badge>{user.role}</Badge>
                          <StatusBadge status={user.status} />
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              ) : (
                <p className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
                  No users found. Bootstrap an admin user or create a local governance user.
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Create user</CardTitle>
              <CardDescription>Create a local user with a temporary password and role.</CardDescription>
            </CardHeader>
            <CardContent>
              <form className="space-y-3" onSubmit={handleCreate}>
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
                  <select
                    className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:focus:border-slate-500 dark:focus:ring-slate-800"
                    onChange={(event) => setNewRole(event.target.value as UserRole)}
                    value={newRole}
                  >
                    {USER_ROLES.map((role) => (
                      <option key={role} value={role}>
                        {role}
                      </option>
                    ))}
                  </select>
                </label>
                {createErrorMessage ? <InlineError message={createErrorMessage} /> : null}
                <Button disabled={!canCreate} type="submit">
                  {isCreating ? "Creating..." : "Create user"}
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Selected user</CardTitle>
              <CardDescription>Update role/display name/password or control account access.</CardDescription>
            </CardHeader>
            <CardContent>
              {editingUser ? (
                <form className="space-y-3" onSubmit={handleUpdate}>
                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-900/60">
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <div className="text-sm font-medium text-slate-950 dark:text-slate-50">Account status</div>
                        <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">Suspended and deactivated users cannot sign in or use personal API tokens.</div>
                      </div>
                      <StatusBadge status={editingUser.status} />
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
                    <select
                      className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-100 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:focus:border-slate-500 dark:focus:ring-slate-800"
                      onChange={(event) => setEditRole(event.target.value as UserRole)}
                      value={editRole}
                    >
                      {USER_ROLES.map((role) => (
                        <option key={role} value={role}>
                          {role}
                        </option>
                      ))}
                    </select>
                  </label>
                  {updateErrorMessage ? <InlineError message={updateErrorMessage} /> : null}
                  {updateStatusErrorMessage ? <InlineError message={updateStatusErrorMessage} /> : null}
                  {revokeTokensErrorMessage ? <InlineError message={revokeTokensErrorMessage} /> : null}
                  {deleteErrorMessage ? <InlineError message={deleteErrorMessage} /> : null}
                  <div className="flex flex-wrap gap-2">
                    <Button disabled={!canUpdate} type="submit">
                      {isUpdating ? "Saving..." : "Save user"}
                    </Button>
                    {editingUser.status !== "active" ? (
                      <Button disabled={isUpdatingStatus} onClick={() => handleStatusChange(editingUser.username, "active")} type="button" variant="secondary">
                        {isUpdatingStatus ? "Updating..." : "Reactivate"}
                      </Button>
                    ) : (
                      <Button disabled={isUpdatingStatus} onClick={() => handleStatusChange(editingUser.username, "suspended")} type="button" variant="secondary">
                        {isUpdatingStatus ? "Updating..." : "Suspend"}
                      </Button>
                    )}
                    {editingUser.status !== "deactivated" ? (
                      <Button disabled={isUpdatingStatus} onClick={() => handleStatusChange(editingUser.username, "deactivated")} type="button" variant="secondary">
                        Deactivate
                      </Button>
                    ) : null}
                    <Button disabled={isRevokingTokens} onClick={() => handleRevokeTokens(editingUser.username)} type="button" variant="secondary">
                      {isRevokingTokens ? "Revoking..." : "Revoke all API tokens"}
                    </Button>
                    <Button disabled={isDeleting} onClick={() => handleDelete(editingUser.username)} type="button" variant="ghost">
                      {isDeleting ? "Deleting..." : "Delete user"}
                    </Button>
                  </div>
                </form>
              ) : (
                <p className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
                  Select a user to update their role, display name, account status, password, or API-token access.
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <ShieldAlert className="h-5 w-5" />
                <div>
                  <CardTitle>Status semantics</CardTitle>
                  <CardDescription>Backend-enforced account controls.</CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="space-y-3 text-sm text-slate-600 dark:text-slate-300">
                <p>
                  <strong className="text-slate-950 dark:text-slate-50">Active:</strong> user can sign in and use personal API tokens.
                </p>
                <p>
                  <strong className="text-slate-950 dark:text-slate-50">Suspended:</strong> temporary block. The account can be reactivated later.
                </p>
                <p>
                  <strong className="text-slate-950 dark:text-slate-50">Deactivated:</strong> closed account state for offboarding or permanent access removal.
                </p>
                <p>
                  <strong className="text-slate-950 dark:text-slate-50">Revoke all API tokens:</strong> disables existing personal tokens without deleting the user.
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>
    </div>
  );
}

function StatusBadge({ status }: { status: UserStatus }) {
  const className =
    status === "active"
      ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200"
      : status === "suspended"
        ? "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-200"
        : "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-200";
  return <Badge className={className}>{status}</Badge>;
}

function InlineError({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200">
      {message}
    </div>
  );
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
