# F-UI-postmvp — Zone-Based Job Detail + Sidebar Nav + Zip Upload

**Status:** in-progress
**Branch:** feat/F-UI-postmvp
**Depends on:** F-UI (complete), F-backend-postmvp (S-BE1, S-BE3, S-BE4 for full feature set)

## Goal

Replace the MVP's flat `<pre>` output with a purpose-fit zone-based UI:
- Persistent sidebar navigation across all pages
- `JobDetailPage` with four tabs (Comparison / Edit / Report / Lineage), each using the right editor primitive
- Zip bulk upload with per-file manifest
- Global lineage page, docs page, and explain page stubs

## Target App Structure

```
/                 → redirect to /jobs
/upload           → UploadPage
/jobs             → JobsPage (list)
/jobs/:id         → JobDetailPage (Comparison | Edit | Report | Lineage tabs)
/lineage          → GlobalLineagePage (React Flow across all jobs)
/docs             → DocsPage (LLM doc summaries, card grid)
/explain          → ExplainPage (F2 stub — chat UI)
```

## New npm packages

```
@monaco-editor/react
@tiptap/react
@tiptap/starter-kit
@tiptap/extension-code-block-lowlight
lowlight
reactflow
```

## Subtasks

### Navigation scaffold
- [x] S-FE5 — `src/frontend/src/components/AppSidebar.tsx`
  - Persistent left sidebar: Upload, Migrations, Lineage, Docs, Explain nav items
  - Icon + label; collapses to icon-only on narrow viewports; active route highlighted
- [x] S-FE10 — `src/frontend/src/App.tsx`
  - Replace `<header>` nav with `AppSidebar` layout wrapper
  - Routes: `/upload`, `/jobs`, `/jobs/:id`, `/lineage`, `/docs`, `/explain`; `/` → redirect `/jobs`
- [x] S-FE11 — `src/frontend/src/pages/JobsPage.tsx`
  - Rows navigate to `/jobs/:id` via `useNavigate`; remove inline expansion + `selectedJobId` state
  - "New migration" button → `/upload`

### Editor components
- [x] S-FE1 — `src/frontend/src/components/MonacoDiffViewer.tsx`
  - Wraps `DiffEditor` from `@monaco-editor/react`
  - Props: `original: string`, `modified: string`, `onChange?: (value: string) => void`
  - Left pane (SAS) read-only; right pane (Python) editable
- [x] S-FE2 — `src/frontend/src/components/MonacoEditor.tsx`
  - Wraps `Editor` from `@monaco-editor/react`
  - Props: `value: string`, `onChange?: (value: string) => void`, `readOnly?: boolean`
- [x] S-FE3 — `src/frontend/src/components/TiptapEditor.tsx`
  - StarterKit + CodeBlockLowlight; toolbar: bold, italic, code block + language selector
  - Props: `content?: string`, `onChange?: (html: string) => void`, `readOnly?: boolean`
  - `readOnly=true`: non-editable mode with "Edit" toggle button top-right
- [x] S-FE4 — `src/frontend/src/components/LineageGraph.tsx`
  - React Flow canvas; node colours by status; dashed edges for inferred
  - Simple grid auto-layout (no dagre); `<Controls />` + `<Background />`

### New pages
- [x] S-FE6 — `src/frontend/src/pages/JobDetailPage.tsx` at `/jobs/:id`
  - Header: job ID (truncated), status badge, Download button, `← Migrations` back link
  - Tab 1 **Comparison**: `MonacoDiffViewer` (SAS from `GET /sources` + Python from job status)
  - Tab 2 **Edit**: `MonacoEditor` + "Save & Re-reconcile" (`PUT /python_code`) + "Refine migration" (`POST /refine` → navigate to new job)
  - Tab 3 **Report**: reconciliation JSON in code block + LLM doc rendered via `marked` → `prose` HTML
  - Tab 4 **Lineage**: `LineageGraph` (data from `GET /lineage`)
- [ ] S-FE7 — `src/frontend/src/pages/GlobalLineagePage.tsx` at `/lineage`
  - React Flow of all completed jobs as top-level nodes; click to expand internal lineage
  - Reuses `LineageGraph`
- [ ] S-FE8 — `src/frontend/src/pages/DocsPage.tsx` at `/docs`
  - Card grid: job ID, date, first paragraph of LLM doc
  - Click card → `/jobs/:id` (Report tab)
- [ ] S-FE9 — `src/frontend/src/pages/ExplainPage.tsx` at `/explain`
  - Chat-style stub: `TiptapEditor` input + placeholder response area (backend F2 endpoint out of scope)

### Upload UX
- [x] S-FE12 — `src/frontend/src/pages/UploadPage.tsx`
  - Persistent workspace — never navigates away; state held in `UploadStateProvider` (survives sidebar nav)
  - Phase 1: drop zone + zip tree (jszip client-side parse, `__MACOSX` filtered, per-file remove)
  - Migration name input above drop zone; name stored on Job and shown in result card + jobs table
  - Phase 2 (in-place): live job card with polling status, accepted/rejected manifest, Python preview, report collapsible
  - "Open full details →" shown only when done; "Start another" returns to form keeping result; "Accept & clear" full reset

### API client
- [x] S-FE13 — `src/frontend/src/api/types.ts`
  - Add: `JobSourcesResponse`, `LineageNode`, `LineageEdge`, `JobLineageResponse`, `JobDocResponse`
  - Extend `MigrateResponse` with `accepted: string[]`, `rejected: Array<{filename: string, reason: string}>`, `name?: string`
  - `JobSummary` gains `name: string | null`, `file_count: number`
- [x] S-FE13 — `src/frontend/src/api/jobs.ts`
  - Add: `getJobSources(id)`, `getJobLineage(id)`, `getJobDoc(id)`, `updateJobPythonCode(id, code)`, `refineJob(id, hint?)`
- [x] S-FE13 — `src/frontend/src/api/migrate.ts`
  - Extend `submitMigration` to accept `zipFile?: File`, `name?: string`

## Key constraints

- Stack: React 19, TypeScript strict, Tailwind v4, `@base-ui/react` primitives
- No new backend routes required for nav scaffold (S-FE5–11) — those land first
- Monaco lazy-loaded (React.lazy + Suspense) to keep initial bundle small
- `reactflow` requires `ReactFlowProvider` wrapper; add at page level, not app root
- All React Query keys follow pattern `["job", id, "sources"]`, `["job", id, "lineage"]`, etc.
- `package-lock.json` must be committed alongside `package.json` after adding new packages
- After frontend package changes, `make docker-build` must pass before commit
