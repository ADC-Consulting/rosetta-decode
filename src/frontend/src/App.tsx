import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AppSidebar from "./components/AppSidebar";
import { UploadStateProvider } from "./context/UploadStateContext";
import JobsPage from "./pages/JobsPage";
import UploadPage from "./pages/UploadPage";

const JobDetailPage = lazy(() => import("./pages/JobDetailPage"));
const GlobalLineagePage = lazy(() => import("./pages/GlobalLineagePage"));
const DocsPage = lazy(() => import("./pages/DocsPage"));
const ExplainPage = lazy(() => import("./pages/ExplainPage"));

function App(): React.ReactElement {
  return (
    <UploadStateProvider>
    <div className="flex h-screen overflow-hidden bg-background text-foreground">
      <AppSidebar />
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-5xl mx-auto px-6 py-8">
          <Suspense fallback={<div className="text-sm text-muted-foreground">Loading…</div>}>
            <Routes>
              <Route path="/" element={<Navigate to="/jobs" replace />} />
              <Route path="/upload" element={<UploadPage />} />
              <Route path="/jobs" element={<JobsPage />} />
              <Route path="/jobs/:id" element={<JobDetailPage />} />
              <Route path="/lineage" element={<GlobalLineagePage />} />
              <Route path="/docs" element={<DocsPage />} />
              <Route path="/explain" element={<ExplainPage />} />
            </Routes>
          </Suspense>
        </div>
      </main>
    </div>
    </UploadStateProvider>
  );
}

export default App;
