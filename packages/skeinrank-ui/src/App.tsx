import { QueryClient, QueryClientProvider, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { LoginPage } from "./components/LoginPage";
import { AppSection, AppShell } from "./components/layout/AppShell";
import { UsersManager } from "./components/UsersManager";
import { clearAuthToken, createUser, deleteUser, getAuthToken, getCurrentUser, GovernanceApiError, listUsers, login, logout, setAuthToken, updateUser } from "./lib/api";
import { GovernanceDashboard } from "./pages/GovernanceDashboard";
import { SuggestionsPage } from "./pages/SuggestionsPage";
import { permissionsForUser } from "./permissions";
import { ThemeProvider } from "./theme";
import type { AuthUser, LoginRequest, UserCreateRequest, UserUpdateRequest } from "./types";

function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 30_000,
      },
    },
  });
}

export function App() {
  const [queryClient] = useState(createQueryClient);

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthGate />
      </ThemeProvider>
    </QueryClientProvider>
  );
}

function AuthGate() {
  const queryClient = useQueryClient();
  const [tokenVersion, setTokenVersion] = useState(() => getAuthToken() ?? "anonymous");
  const [activeSection, setActiveSection] = useState<AppSection>("terms");

  const meQuery = useQuery({
    queryKey: ["auth", "me", tokenVersion],
    queryFn: getCurrentUser,
  });

  const loginMutation = useMutation({
    mutationFn: (payload: LoginRequest) => login(payload),
    onSuccess: (response) => {
      setAuthToken(response.access_token);
      setTokenVersion(response.access_token);
      queryClient.setQueryData(["auth", "me", response.access_token], response.user);
      void queryClient.invalidateQueries({ queryKey: ["profiles"] });
    },
  });

  const logoutMutation = useMutation({
    mutationFn: logout,
    onSettled: () => {
      clearAuthToken();
      setTokenVersion("anonymous");
      setActiveSection("terms");
      queryClient.clear();
    },
  });

  async function handleLogin(payload: LoginRequest) {
    await loginMutation.mutateAsync(payload);
  }

  function handleLogout() {
    logoutMutation.mutate();
  }

  if (meQuery.isLoading) {
    return <AuthLoading />;
  }

  if (meQuery.error) {
    if (meQuery.error instanceof GovernanceApiError && meQuery.error.status === 401) {
      return <LoginPage errorMessage={loginErrorMessage(loginMutation.error)} isSubmitting={loginMutation.isPending} onSubmit={handleLogin} />;
    }

    return <AuthError message={meQuery.error instanceof Error ? meQuery.error.message : "Unable to load current user."} />;
  }

  const currentUser = meQuery.data;
  if (!currentUser) {
    return <LoginPage errorMessage={loginErrorMessage(loginMutation.error)} isSubmitting={loginMutation.isPending} onSubmit={handleLogin} />;
  }

  const permissions = permissionsForUser(currentUser);
  const safeActiveSection = activeSection === "users" && !permissions.canManageUsers ? "terms" : activeSection;

  return (
    <AppShell
      activeSection={safeActiveSection}
      canManageUsers={permissions.canManageUsers}
      currentUser={currentUser}
      onLogout={handleLogout}
      onNavigate={setActiveSection}
    >
      {safeActiveSection === "users" ? (
        <UsersPage currentUser={currentUser} />
      ) : safeActiveSection === "suggestions" ? (
        <SuggestionsPage currentUser={currentUser} />
      ) : (
        <GovernanceDashboard currentUser={currentUser} />
      )}
    </AppShell>
  );
}

function UsersPage({ currentUser }: { currentUser: AuthUser }) {
  const queryClient = useQueryClient();
  const usersQuery = useQuery({
    queryKey: ["auth", "users"],
    queryFn: listUsers,
  });

  const createUserMutation = useMutation({
    mutationFn: (payload: UserCreateRequest) => createUser(payload),
    onSuccess: (user) => {
      queryClient.setQueryData<AuthUser[]>(["auth", "users"], (users = []) => [...users, user].sort(sortUsers));
      void queryClient.invalidateQueries({ queryKey: ["auth", "users"] });
    },
  });

  const updateUserMutation = useMutation({
    mutationFn: ({ username, payload }: { username: string; payload: UserUpdateRequest }) => updateUser(username, payload),
    onSuccess: (user) => {
      queryClient.setQueryData<AuthUser[]>(["auth", "users"], (users = []) => users.map((current) => (current.id === user.id ? user : current)).sort(sortUsers));
      if (user.id === currentUser.id) {
        queryClient.setQueryData(["auth", "me", getAuthToken() ?? "anonymous"], user);
      }
      void queryClient.invalidateQueries({ queryKey: ["auth", "users"] });
    },
  });

  const deleteUserMutation = useMutation({
    mutationFn: (username: string) => deleteUser(username),
    onSuccess: (_result, username) => {
      queryClient.setQueryData<AuthUser[]>(["auth", "users"], (users = []) => users.filter((user) => user.username !== username));
      void queryClient.invalidateQueries({ queryKey: ["auth", "users"] });
    },
  });

  async function handleCreateUser(payload: UserCreateRequest) {
    await createUserMutation.mutateAsync(payload);
  }

  async function handleUpdateUser(username: string, payload: UserUpdateRequest) {
    await updateUserMutation.mutateAsync({ username, payload });
  }

  async function handleDeleteUser(username: string) {
    await deleteUserMutation.mutateAsync(username);
  }

  return (
    <UsersManager
      createErrorMessage={errorMessage(createUserMutation.error)}
      deleteErrorMessage={errorMessage(deleteUserMutation.error)}
      isCreating={createUserMutation.isPending}
      isDeleting={deleteUserMutation.isPending}
      isLoading={usersQuery.isLoading}
      isUpdating={updateUserMutation.isPending}
      loadErrorMessage={usersQuery.isError ? usersQuery.error.message : null}
      onCreateUser={handleCreateUser}
      onDeleteUser={handleDeleteUser}
      onUpdateUser={handleUpdateUser}
      updateErrorMessage={errorMessage(updateUserMutation.error)}
      users={usersQuery.data ?? []}
    />
  );
}

function AuthLoading() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 text-sm text-slate-500 dark:bg-slate-950 dark:text-slate-400">
      Loading governance session...
    </div>
  );
}

function AuthError({ message }: { message: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 dark:bg-slate-950">
      <div className="max-w-md rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200">
        <div className="font-medium">Unable to load governance session</div>
        <div className="mt-1">{message}</div>
      </div>
    </div>
  );
}

function loginErrorMessage(error: unknown) {
  if (!error) {
    return null;
  }
  return error instanceof Error ? error.message : "Sign in failed. Check your username and password.";
}

function errorMessage(error: unknown) {
  if (!error) {
    return null;
  }
  return error instanceof Error ? error.message : "Request failed. Check the governance API and try again.";
}

function sortUsers(left: AuthUser, right: AuthUser) {
  return left.normalized_username.localeCompare(right.normalized_username);
}
