import { type FormEvent, useState } from "react";
import { LogIn } from "lucide-react";

import type { LoginRequest } from "../types";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Input } from "./ui/input";

export type LoginPageProps = {
  errorMessage?: string | null;
  isSubmitting?: boolean;
  onSubmit: (payload: LoginRequest) => Promise<void> | void;
};

export function LoginPage({ errorMessage, isSubmitting = false, onSubmit }: LoginPageProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const canSubmit = username.trim().length > 0 && password.length > 0 && !isSubmitting;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }

    try {
      await onSubmit({ username: username.trim(), password });
      setPassword("");
    } catch {
      // Parent mutation owns user-facing error rendering.
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 px-4 py-10 text-slate-950 transition-colors dark:bg-slate-950 dark:text-slate-50">
      <div className="mx-auto flex min-h-[calc(100vh-5rem)] max-w-md items-center">
        <Card className="w-full">
          <CardHeader>
            <div className="mb-2 inline-flex h-10 w-10 items-center justify-center rounded-xl bg-slate-950 text-white dark:bg-slate-100 dark:text-slate-950">
              <LogIn className="h-5 w-5" />
            </div>
            <CardTitle>SkeinRank sign in</CardTitle>
            <CardDescription>Sign in to manage terminology governance, users, and role-aware workflows.</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={handleSubmit}>
              <label className="space-y-1.5">
                <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Username</span>
                <Input autoComplete="username" onChange={(event) => setUsername(event.target.value)} placeholder="admin" value={username} />
              </label>
              <label className="space-y-1.5">
                <span className="text-sm font-medium text-slate-700 dark:text-slate-200">Password</span>
                <Input
                  autoComplete="current-password"
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="••••••••"
                  type="password"
                  value={password}
                />
              </label>
              {errorMessage ? (
                <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200">
                  {errorMessage}
                </div>
              ) : null}
              <Button className="w-full" disabled={!canSubmit} type="submit">
                {isSubmitting ? "Signing in..." : "Sign in"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
