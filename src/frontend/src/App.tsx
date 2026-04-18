import { Link, Routes, Route } from 'react-router-dom'
import UploadPage from './pages/UploadPage'
import JobsPage from './pages/JobsPage'

function App() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border">
        <nav className="max-w-5xl mx-auto px-4 h-14 flex items-center gap-6">
          <span className="font-semibold text-foreground">Rosetta Decode</span>
          <Link
            to="/"
            className="text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            Upload
          </Link>
          <Link
            to="/jobs"
            className="text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            Jobs
          </Link>
        </nav>
      </header>
      <main className="max-w-5xl mx-auto px-4 py-8">
        <Routes>
          <Route path="/" element={<UploadPage />} />
          <Route path="/jobs" element={<JobsPage />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
