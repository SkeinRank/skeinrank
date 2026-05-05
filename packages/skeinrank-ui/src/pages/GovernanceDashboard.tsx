import { useQuery } from "@tanstack/react-query";
import { AlertCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { SnapshotPanel } from "../components/SnapshotPanel";
import { TermsTable } from "../components/TermsTable";
import { Badge } from "../components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { listProfiles, listTerms } from "../lib/api";

export function GovernanceDashboard() {
  const profilesQuery = useQuery({
    queryKey: ["profiles"],
    queryFn: listProfiles,
  });

  const [selectedProfile, setSelectedProfile] = useState<string | null>(null);

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
                <p className="text-sm text-slate-500">Loading profiles...</p>
              ) : profilesQuery.data && profilesQuery.data.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {profilesQuery.data.map((profile) => (
                    <button
                      className={`rounded-full border px-3 py-1.5 text-sm font-medium transition-colors ${
                        selectedProfile === profile.name
                          ? "border-slate-950 bg-slate-950 text-white"
                          : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                      }`}
                      key={profile.id}
                      onClick={() => setSelectedProfile(profile.name)}
                      type="button"
                    >
                      {profile.name}
                    </button>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-slate-500">
                  No profiles found. Create a profile through the governance API or admin CLI.
                </p>
              )}
            </CardContent>
          </Card>

          {termsQuery.isError ? (
            <ErrorMessage message={termsQuery.error.message} />
          ) : termsQuery.isLoading && selectedProfile ? (
            <Card>
              <CardContent>
                <p className="text-sm text-slate-500">Loading terms...</p>
              </CardContent>
            </Card>
          ) : (
            <TermsTable terms={termsQuery.data ?? []} />
          )}
        </div>

        <SnapshotPanel profileName={selectedProfile} />
      </section>
    </div>
  );
}

function ErrorMessage({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
      <AlertCircle className="mt-0.5 h-4 w-4" />
      <div>
        <div className="font-medium">Unable to load governance data</div>
        <div className="mt-1">{message}</div>
      </div>
    </div>
  );
}
