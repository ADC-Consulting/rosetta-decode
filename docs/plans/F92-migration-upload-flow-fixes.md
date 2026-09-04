# F92 — Fix the migration upload flow (Migrate button, dead code, theming)

**Phase:** 3
**Area:** Frontend
**Status:** in-progress

## Goal

Fix the concrete bugs found this session while testing the "New migration" upload dialog with a
real sample project (tracked in issue #148, alongside two larger, design-led ideas — a welcome
page and a sidebar redesign — that are deliberately **not** part of this plan; see Out of scope).

Root-caused via code reading and a live browser reproduction:

1. `src/frontend/src/pages/JobsPage.tsx`'s "New migration" dialog is the **only live upload path**
   — `src/frontend/src/pages/UploadPage.tsx` has no route in `App.tsx` and is referenced nowhere
   else in the app. It is dead code left over from a 2026-04-23 decision ("Upload page promoted to
   Dialog on JobsPage... revisit never" — `journal/DECISIONS.md`) that was never deleted afterward.
2. The dialog's `submitDisabled` unconditionally requires `refTargetPath` to be set — the Migrate
   button cannot be enabled without marking a reconciliation target — even though the backend
   (`POST /migrate`, `ref_target_path: str | None = Form(default=None)`) treats it as fully
   optional. This is what actually blocked migration submission this session.
3. Nothing in the UI explains that a reconciliation target must be a file **already inside** the
   submitted zip (`ref_target_path` only ever matches a zip-extracted entry — see
   `_unpack_zip`/`migrate()` in `src/backend/api/routes/migrate.py`). A standalone reference file
   added alongside a zip is silently never uploaded at all: `submitMigration()`
   (`src/frontend/src/api/migrate.ts`) only appends `zip_file` when one is present, dropping
   `sas_files`/`ref_dataset` entirely.
4. The dialog still uses stock shadcn/Tailwind styling (default button, `bg-emerald-100
   text-emerald-700` badges) instead of the muted "Manifest" design system rolled out to the Plan
   tab in F87–F90, and its `DialogContent` has no `container` prop, so — like 4 other dialogs
   fixed in F91 — it portals to `document.body`, escaping `.brand-manifest` entirely.

## Acceptance Criteria

- [ ] Migrate button enables based on real requirements only (valid files selected, name filled) —
      no reconciliation target required
- [ ] `UploadPage.tsx` deleted; confirmed no remaining references anywhere in the frontend
- [ ] Dialog copy clearly explains reconciliation is optional, and that a zip upload's reference
      file must be bundled inside the zip itself
- [ ] Dialog renders themed (Manifest fonts/accent/muted tone colors) instead of stock shadcn, in
      both light and dark mode
- [ ] `make test` exits 0

## Subtasks

### S-A: Delete dead `UploadPage.tsx`
**File:** `src/frontend/src/pages/UploadPage.tsx` (delete)
**Depends on:** none
**Done when:** file removed; grep confirms no remaining reference to `UploadPage` or a `/upload`
route anywhere in `src/frontend/src`.
- [x] done — deleted. Re-grepped before removing per the plan's caution: the only extra hit beyond
  what was already known was a stale `/upload` mention in a code comment inside
  `UploadStateContext.tsx` (a live, shared context still used by the dialog) — not a reference to
  the `UploadPage` component itself, so it was safe to proceed.

### S-B: Stop requiring a reconciliation target to submit
**File:** `src/frontend/src/pages/JobsPage.tsx`
**Depends on:** none
**Done when:** `submitDisabled` no longer includes `!refTargetPath`; Migrate enables with just a
valid file selection + name, matching `POST /migrate`'s actual optionality.
- [x] done — `!refTargetPath` removed from `submitDisabled`. Verified live (twice — once by the
  implementing agent, once independently): a single `.sas` file + a name, no target set anywhere,
  enables Migrate immediately.

### S-C: Clarify reconciliation-target UX copy
**File:** `src/frontend/src/pages/JobsPage.tsx`
**Depends on:** S-B
**Done when:** the "Select a target dataset for reconciliation" banner/help text states plainly
that (1) this step is optional, and (2) for a zip upload the reference file must be included
*inside* the zip — a file added alongside it is never sent to the backend.
- [x] done — banner reworded to "Reconciliation target (optional)"; added a
  `refTargetIsOutsideZip` derived check that catches the exact silent-failure case (a target set on
  a file sitting alongside the zip rather than inside it) and flips the banner to a red "⚠ Won't
  upload — outside the zip" warning with an explanatory line, instead of a false "✓ Target set".
  Contextual hint text also added for the zip-present/no-target and no-zip/eligible-file states.
  Verified live for both the reworded default copy and the outside-zip warning state.

### S-D: Apply Manifest design system styling to the dialog
**File:** `src/frontend/src/pages/JobsPage.tsx`
**Depends on:** S-B, S-C
**Depends on (external):** F91 merged — reuses `useBrandManifestContainer()`
(`src/frontend/src/lib/`, added in F91). Branch this plan off `fix/F91-design-followups` if #145
hasn't merged yet by the time this subtask starts, to avoid re-deriving the hook.
**Done when:** (1) `DialogContent` passes `container={useBrandManifestContainer()}` so the dialog
renders inside `.brand-manifest` instead of portaling to `document.body` — the same bug class
fixed for 4 other dialogs in F91, just out of that pass's scope; (2) the "TARGET" badge and other
hardcoded Tailwind color utilities are swapped for the muted Manifest tone tokens established in
F88/F89; (3) the Migrate button matches Manifest's button styling.
- [ ] done

### S-E: Full manual smoke test
**Depends on:** S-A, S-B, S-C, S-D
**Done when:** verified live in the browser — submitting with no reconciliation target at all
(previously impossible) succeeds; submitting with a zip-bundled target still works; dialog renders
themed correctly in both light and dark mode.
- [ ] done

### S-F: Gate
**Depends on:** S-E
**Done when:** `make tsc-check && make frontend-lint && make frontend-build && make test` all exit
0.
- [ ] done

## Dependencies on other features

- S-D depends on F91's `useBrandManifestContainer()` hook (PR #145) — merge first, or branch off
  `fix/F91-design-followups` instead of `main`

## Out of scope for this feature

- The welcome/landing page and sidebar nav redesign from issue #148 — design-led work needing its
  own mockup/decision pass (the same process F87–F90's "Manifest" direction went through), not
  bundled into this bug-fix-scoped plan. Track as a separate future plan once scoped.
- Any backend change — `POST /migrate`'s existing `ref_target_path` optionality is already
  correct; this plan only fixes the frontend to match it.
