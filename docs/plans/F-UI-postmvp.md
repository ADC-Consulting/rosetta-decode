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
- [ ] S-FE5 — `src/frontend/src/components/AppSidebar.tsx`
  - Persistent left sidebar: Upload, Migrations, Lineage, Docs, Explain nav items
  - Icon + label; collapses to icon-only on narrow viewports; active route highlighted
- [ ] S-FE10 — `src/frontend/src/App.tsx`
  - Replace `<header>` nav with `AppSidebar` layout wrapper
  - Routes: `/upload`, `/jobs`, `/jobs/:id`, `/lineage`, `/docs`, `/explain`; `/` → redirect `/jobs`
- [ ] S-FE11 — `src/frontend/src/pages/JobsPage.tsx`
  - Rows navigate to `/jobs/:id` via `useNavigate`; remove inline expansion + `selectedJobId` state
  - "New migration" button → `/upload`

### Editor components
- [ ] S-FE1 — `src/frontend/src/components/MonacoDiffViewer.tsx`
  - Wraps `DiffEditor` from `@monaco-editor/react`
  - Props: `original: string`, `modified: string`, `onChange?: (value: string) => void`
  - Left pane (SAS) read-only; right pane (Python) editable
- [ ] S-FE2 — `src/frontend/src/components/MonacoEditor.tsx`
  - Wraps `Editor` from `@monaco-editor/react`
  - Props: `value: string`, `onChange?: (value: string) => void`, `readOnly?: boolean`
- [ ] S-FE3 — `src/frontend/src/components/TiptapEditor.tsx`
  - StarterKit + CodeBlockLowlight; toolbar: bold, italic, code block + language selector
  - Props: `content?: string`, `onChange?: (html: string) => void`, `readOnly?: boolean`
  - `readOnly=true`: non-editable mode with "Edit" toggle button top-right
- [ ] S-FE4 — `src/frontend/src/components/LineageGraph.tsx`
  - React Flow canvas with three zoom levels
  - Level 1 (default): SAS files as nodes, inter-file edges
  - Level 2 (double-click file node): SAS blocks within file
  - Level 3 (click "show columns"): column-level operations within step
  - Node colours: `migrated` → green border, `manual_review` → amber, `untranslatable` → red
  - Edge styles: `inferred: true` → dashed, `inferred: false` → solid
  - Breadcrumb pill: `File graph > script.sas > DATA myds`; clicking parent zooms out
  - Props: `lineage: JobLineageResponse`

### New pages
- [ ] S-FE6 — `src/frontend/src/pages/JobDetailPage.tsx` at `/jobs/:id`
  - Header: job ID (truncated), status badge, Download button, `← Migrations` back link
  - Tab 1 **Comparison**: `MonacoDiffViewer` (SAS from `GET /sources` + Python from job status)
  - Tab 2 **Edit**: `MonacoEditor` + "Save & Re-reconcile" (`PUT /python_code`) + "Refine migration" (`POST /refine` → navigate to new job)
  - Tab 3 **Report**: `TiptapEditor readOnly` for reconciliation report; `TiptapEditor readOnly` for LLM doc; each has Edit toggle
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
- [ ] S-FE12 — `src/frontend/src/pages/UploadPage.tsx`
  - Radio toggle: "Individual files" (existing multi-.sas input) | "Zip archive" (new `.zip` input)
  - After submission: file manifest — accepted (green tick) + rejected (red ✕ + reason)
  - Manifest from extended `MigrateResponse.accepted` / `.rejected`

### API client
- [ ] S-FE13 — `src/frontend/src/api/types.ts`
  - Add: `JobSourcesResponse`, `LineageNode`, `LineageEdge`, `JobLineageResponse`, `JobDocResponse`
  - Extend `MigrateResponse` with `accepted: string[]`, `rejected: Array<{filename: string, reason: string}>`
- [ ] S-FE13 — `src/frontend/src/api/jobs.ts`
  - Add: `getJobSources(id)`, `getJobLineage(id)`, `getJobDoc(id)`, `updateJobPythonCode(id, code)`, `refineJob(id, hint?)`
- [ ] S-FE13 — `src/frontend/src/api/migrate.ts`
  - Extend `submitMigration` to accept `zipFile?: File` (mutually exclusive with `sasFiles`)

## Key constraints

- Stack: React 19, TypeScript strict, Tailwind v4, `@base-ui/react` primitives
- No new backend routes required for nav scaffold (S-FE5–11) — those land first
- Monaco lazy-loaded (React.lazy + Suspense) to keep initial bundle small
- `reactflow` requires `ReactFlowProvider` wrapper; add at page level, not app root
- All React Query keys follow pattern `["job", id, "sources"]`, `["job", id, "lineage"]`, etc.
- `package-lock.json` must be committed alongside `package.json` after adding new packages
- After frontend package changes, `make docker-build` must pass before commit
