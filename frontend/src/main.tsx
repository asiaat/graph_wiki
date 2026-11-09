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

class AppErrorBoundary extends React.Component<
  React.PropsWithChildren,
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
          <section className="max-w-lg rounded-lg border border-red-200 bg-white p-6 shadow-sm">
            <h1 className="text-lg font-semibold text-slate-900">The workbench hit an error</h1>
            <p className="mt-2 text-sm text-slate-600">
              Reload the page to try again. If this keeps happening, share the browser console error with the project team.
            </p>
            <button className="btn btn-primary btn-sm mt-4" onClick={() => window.location.reload()}>
              Reload workbench
            </button>
          </section>
        </main>
      );
    }
    return this.props.children;
  }
}

function App() {
  return (
    <AppErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <WorkbenchShell />
      </QueryClientProvider>
    </AppErrorBoundary>
  );
}

const container = document.getElementById("root");
if (container) {
  createRoot(container).render(<App />);
}
