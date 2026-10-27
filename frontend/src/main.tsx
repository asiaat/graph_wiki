import React from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import WorkbenchShell from "./components/layout/WorkbenchShell";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5000,
      retry: 1,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <WorkbenchShell />
    </QueryClientProvider>
  );
}

const container = document.getElementById("root");
if (container) {
  createRoot(container).render(<App />);
}
