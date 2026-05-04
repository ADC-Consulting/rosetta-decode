import { ThemeProvider } from "next-themes";
import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AppSidebar from "./components/AppSidebar";
import { Toaster } from "./components/ui/sonner";
import { UploadStateProvider } from "./context/UploadStateContext";
import JobsPage from "./pages/JobsPage";

const JobDetailPage = lazy(() => import("./pages/JobDetailPage"));
const EditorFullPage = lazy(() => import("./pages/EditorFullPage"));
const GlobalLineagePage = lazy(() => import("./pages/GlobalLineagePage"));
const DocsPage = lazy(() => import("./pages/DocsPage"));
const ExplainPage = lazy(() => import("./pages/ExplainPage"));

function App(): React.ReactElement {
  return (
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
      <UploadStateProvider>
        <div className="flex h-screen overflow-hidden bg-background text-foreground">
          <AppSidebar />
          <main className="flex-1 overflow-hidden flex flex-col">
            <Suspense
              fallback={
                <div className="text-sm text-muted-foreground p-8">
                  Loading…
                </div>
              }
            >
              <Routes>
                <Route path="/" element={<Navigate to="/jobs" replace />} />
                <Route path="/jobs" element={<JobsPage />} />
                <Route path="/jobs/:id" element={<JobDetailPage />} />
                <Route path="/jobs/:id/editor" element={<EditorFullPage />} />
                <Route path="/lineage" element={<GlobalLineagePage />} />
                <Route path="/docs" element={<DocsPage />} />
                <Route path="/explain" element={<ExplainPage />} />
              </Routes>
            </Suspense>
          </main>
        </div>
        <Toaster position="top-right" richColors closeButton />
      </UploadStateProvider>
    </ThemeProvider>
  );
}

export default App;
