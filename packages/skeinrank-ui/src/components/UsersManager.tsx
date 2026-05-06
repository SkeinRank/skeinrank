import { type FormEvent, useEffect, useState } from "react";
import { Users } from "lucide-react";

import type { AuthUser, UserCreateRequest, UserRole, UserUpdateRequest } from "../types";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Input } from "./ui/input";

const USER_ROLES: UserRole[] = ["admin", "moderator", "contributor"];

type UsersManagerProps = {
  createErrorMessage?: string | null;
  deleteErrorMessage?: string | null;
  isCreating?: boolean;
  isDeleting?: boolean;
  isLoading?: boolean;
  isUpdating?: boolean;
  loadErrorMessage?: string | null;
  onCreateUser: (payload: UserCreateRequest) => Promise<void> | void;
  onDeleteUser: (username: string) => Promise<void> | void;
  onUpdateUser: (username: string, payload: UserUpdateRequest) => Promise<void> | void;
  updateErrorMessage?: string | null;
  users: AuthUser[];
};

export function UsersManager({
  createErrorMessage,
  deleteErrorMessage,
  isCreating = false,
  isDeleting = false,
  isLoading = false,
  isUpdating = false,
  loadErrorMessage,
  onCreateUser,
  onDeleteUser,
  onUpdateUser,
  updateErrorMessage,
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
  const [editIsActive, setEditIsActive] = useState(true);

  const editingUser = users.find((user) => user.username === editingUsername) ?? null;
  const canCreate = newUsername.trim().length > 0 && newPassword.length > 0 && !isCreating;
  const canUpdate = Boolean(editingUser) && editUsername.trim().length > 0 && !isUpdating;

  useEffect(() => {
    if (!editingUser) {
      return;
    }
    setEditUsername(editingUser.username);
    setEditDisplayName(editingUser.display_name ?? "");
    setEditPassword("");
    setEditRole(editingUser.role);
    setEditIsActive(editingUser.is_active);
  }, [editingUser?.id, editingUser?.is_active, editingUser?.display_name, editingUser?.role, editingUser?.username]);

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
        is_active: true,
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
        is_active: editIsActive,
      });
      setEditPassword("");
    } catch {
      // Parent mutation owns user-facing error rendering.
    }
  }

  async function handleDelete(username: string) {
    const confirmed = window.confirm(`Delete user "${username}"? This will revoke their governance access.`);
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
      <section className="grid gap-4 md:grid-cols-3">
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
            <CardTitle>Roles</CardTitle>
            <CardDescription>Admin, Moderator, Contributor.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {USER_ROLES.map((role) => (
                <Badge key={role}>{role}</Badge>
              ))}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Access model</CardTitle>
            <CardDescription>Backend-enforced permissions.</CardDescription>
          </CardHeader>
          <CardContent>
            <Badge>Bearer token → Role checks</Badge>
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
                  <CardDescription>Create users and assign platform roles.</CardDescription>
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
                          <Badge className={user.is_active ? undefined : "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-200"}>
                            {user.is_active ? "active" : "inactive"}
                          </Badge>
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
              <CardDescription>Update role, active state, display name, or password.</CardDescription>
            </CardHeader>
            <CardContent>
              {editingUser ? (
                <form className="space-y-3" onSubmit={handleUpdate}>
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
                  <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
                    <input checked={editIsActive} onChange={(event) => setEditIsActive(event.target.checked)} type="checkbox" />
                    Active user
                  </label>
                  {updateErrorMessage ? <InlineError message={updateErrorMessage} /> : null}
                  {deleteErrorMessage ? <InlineError message={deleteErrorMessage} /> : null}
                  <div className="flex flex-wrap gap-2">
                    <Button disabled={!canUpdate} type="submit">
                      {isUpdating ? "Saving..." : "Save user"}
                    </Button>
                    <Button disabled={isDeleting} onClick={() => handleDelete(editingUser.username)} type="button" variant="secondary">
                      {isDeleting ? "Deleting..." : "Delete user"}
                    </Button>
                  </div>
                </form>
              ) : (
                <p className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-800 dark:text-slate-400">
                  Select a user to update their role, display name, active state, or password.
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Role permissions</CardTitle>
              <CardDescription>UI follows the backend permission model.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3 text-sm text-slate-600 dark:text-slate-300">
                <p>
                  <strong className="text-slate-950 dark:text-slate-50">Admin:</strong> users, profiles, terminology CRUD, snapshot export.
                </p>
                <p>
                  <strong className="text-slate-950 dark:text-slate-50">Moderator:</strong> terminology CRUD and snapshot export.
                </p>
                <p>
                  <strong className="text-slate-950 dark:text-slate-50">Contributor:</strong> read-only terminology access until suggestions are added.
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>
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
