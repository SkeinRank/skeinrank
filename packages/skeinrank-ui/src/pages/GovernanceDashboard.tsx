import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { AddTermForm } from "../components/AddTermForm";
import { SnapshotPanel } from "../components/SnapshotPanel";
import { TermDetailsPanel } from "../components/TermDetailsPanel";
import { TermsTable } from "../components/TermsTable";
import { Badge } from "../components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { createAlias, createTerm, listProfiles, listTerms } from "../lib/api";
import type { AliasCreateRequest, CanonicalTerm, TermCreateRequest } from "../types";

export function GovernanceDashboard() {
  const queryClient = useQueryClient();
  const profilesQuery = useQuery({
    queryKey: ["profiles"],
    queryFn: listProfiles,
  });

  const [selectedProfile, setSelectedProfile] = useState<string | null>(null);
  const [selectedTermId, setSelectedTermId] = useState<number | null>(null);

  useEffect(() => {
    if (!selectedProfile && profilesQuery.data && profilesQuery.data.length > 0) {
      setSelectedProfile(profilesQuery.data[0].name);
    }
  }, [profilesQuery.data, selectedProfile]);

  const termsQuery = useQuery({
    queryKey: ["terms", selectedProfile],
    queryFn: () => listTerms(selectedProfile ?? ""),
    enabled: Boolean(selectedProfile),
  });

  useEffect(() => {
    if (!termsQuery.data) {
      return;
    }

    if (termsQuery.data.length === 0) {
      setSelectedTermId(null);
      return;
    }

    if (!selectedTermId || !termsQuery.data.some((term) => term.id === selectedTermId)) {
      setSelectedTermId(termsQuery.data[0].id);
    }
  }, [selectedTermId, termsQuery.data]);

  const selectedTerm = useMemo(() => {
    if (!termsQuery.data || !selectedTermId) {
      return null;
    }
    return termsQuery.data.find((term) => term.id === selectedTermId) ?? null;
  }, [selectedTermId, termsQuery.data]);

  const createTermMutation = useMutation({
    mutationFn: (payload: TermCreateRequest) => {
      if (!selectedProfile) {
        throw new Error("Select a profile before creating a term.");
      }
      return createTerm(selectedProfile, payload);
    },
    onSuccess: (term) => {
      setSelectedTermId(term.id);
      queryClient.setQueryData<CanonicalTerm[]>(["terms", selectedProfile], (currentTerms = []) => {
        if (currentTerms.some((currentTerm) => currentTerm.id === term.id)) {
          return currentTerms;
        }
        return [...currentTerms, term];
      });
      void queryClient.invalidateQueries({ queryKey: ["terms", selectedProfile] });
    },
  });

  const createAliasMutation = useMutation({
    mutationFn: (payload: AliasCreateRequest) => {
      if (!selectedProfile || !selectedTerm) {
        throw new Error("Select a canonical term before creating an alias.");
      }
      return createAlias(selectedProfile, selectedTerm.canonical_value, payload);
    },
    onSuccess: (alias) => {
      queryClient.setQueryData<CanonicalTerm[]>(["terms", selectedProfile], (currentTerms = []) =>
        currentTerms.map((term) => {
          if (term.id !== selectedTerm?.id || term.aliases.some((currentAlias) => currentAlias.id === alias.id)) {
            return term;
          }
          return { ...term, aliases: [...term.aliases, alias] };
        }),
      );
      void queryClient.invalidateQueries({ queryKey: ["terms", selectedProfile] });
    },
  });

  function handleProfileSelect(profileName: string) {
    setSelectedProfile(profileName);
    setSelectedTermId(null);
    createTermMutation.reset();
    createAliasMutation.reset();
  }

  async function handleCreateTerm(payload: TermCreateRequest) {
    await createTermMutation.mutateAsync(payload);
  }

  async function handleCreateAlias(payload: AliasCreateRequest) {
    await createAliasMutation.mutateAsync(payload);
  }

  function handleTermSelect(termId: number) {
    setSelectedTermId(termId);
    createAliasMutation.reset();
  }

  return (
    <div className="space-y-6">
      <section className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Profiles</CardTitle>
            <CardDescription>Terminology namespaces.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">{profilesQuery.data?.length ?? 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Canonical terms</CardTitle>
            <CardDescription>Typed entities in the selected profile.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold">{termsQuery.data?.length ?? 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Runtime model</CardTitle>
            <CardDescription>Snapshot-based extraction path.</CardDescription>
          </CardHeader>
          <CardContent>
            <Badge>Postgres → Snapshot → Aho-Corasick</Badge>
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Profile selector</CardTitle>
              <CardDescription>Select the profile that the console should inspect.</CardDescription>
            </CardHeader>
            <CardContent>
              {profilesQuery.isError ? (
                <ErrorMessage message={profilesQuery.error.message} />
              ) : profilesQuery.isLoading ? (
                <p className="text-sm text-slate-500 dark:text-slate-400">Loading profiles...</p>
              ) : profilesQuery.data && profilesQuery.data.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {profilesQuery.data.map((profile) => (
                    <button
                      className={`rounded-full border px-3 py-1.5 text-sm font-medium transition-colors ${
                        selectedProfile === profile.name
                          ? "border-slate-950 bg-slate-950 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-950"
                          : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300 dark:hover:bg-slate-900"
                      }`}
                      key={profile.id}
                      onClick={() => handleProfileSelect(profile.name)}
                      type="button"
                    >
                      {profile.name}
                    </button>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  No profiles found. Create a profile through the governance API or admin CLI.
                </p>
              )}
            </CardContent>
          </Card>

          <AddTermForm
            disabled={!selectedProfile}
            errorMessage={errorMessage(createTermMutation.error)}
            isSubmitting={createTermMutation.isPending}
            onSubmit={handleCreateTerm}
          />

          {termsQuery.isError ? (
            <ErrorMessage message={termsQuery.error.message} />
          ) : termsQuery.isLoading && selectedProfile ? (
            <Card>
              <CardContent>
                <p className="text-sm text-slate-500 dark:text-slate-400">Loading terms...</p>
              </CardContent>
            </Card>
          ) : (
            <TermsTable onSelectTerm={(term) => handleTermSelect(term.id)} selectedTermId={selectedTermId} terms={termsQuery.data ?? []} />
          )}
        </div>

        <div className="space-y-6">
          <TermDetailsPanel
            errorMessage={errorMessage(createAliasMutation.error)}
            isAddingAlias={createAliasMutation.isPending}
            onAddAlias={handleCreateAlias}
            term={selectedTerm}
          />
          <SnapshotPanel profileName={selectedProfile} />
        </div>
      </section>
    </div>
  );
}

function ErrorMessage({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200">
      <AlertCircle className="mt-0.5 h-4 w-4" />
      <div>
        <div className="font-medium">Unable to load governance data</div>
        <div className="mt-1">{message}</div>
      </div>
    </div>
  );
}

function errorMessage(error: unknown) {
  if (!error) {
    return null;
  }
  return error instanceof Error ? error.message : "Request failed. Check the governance API and try again.";
}
