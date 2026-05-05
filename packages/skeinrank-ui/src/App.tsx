import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

import { AppShell } from "./components/layout/AppShell";
import { GovernanceDashboard } from "./pages/GovernanceDashboard";
import { ThemeProvider } from "./theme";

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
        <AppShell>
          <GovernanceDashboard />
        </AppShell>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
