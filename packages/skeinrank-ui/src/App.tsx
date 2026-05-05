import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AppShell } from "./components/layout/AppShell";
import { GovernanceDashboard } from "./pages/GovernanceDashboard";
import { ThemeProvider } from "./theme";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      staleTime: 30_000,
    },
  },
});

export function App() {
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
