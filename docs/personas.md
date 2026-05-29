# Personas

Two primary personas use rosetta-decode. They have different goals, different literacy levels, and consume different parts of the UI.

---

## P1 — Technical Lead / Data Engineer

**Goal:** Migrate SAS code to runnable Python/PySpark as quickly and safely as possible. Needs to verify that generated code is correct, fix what isn't, and have evidence it works before handing to production.

**Background:** Comfortable reading both SAS and Python. Understands DataFrames, reconciliation, and CI/CD. May have limited SAS depth but knows what correct output looks like.

### Primary views

| View | What they use it for |
|---|---|
| **Job Detail — Plan tab** | Review block-by-block strategy decisions; check confidence + reconciliation status; expand blocks flagged for review; edit code inline via View Code dialog |
| **Job Detail — Editor tab** | Read generated Python against the SAS source; run the code; check stdout/stderr; iterate on blocks that fail execution |
| **Job Detail — Lineage tab** | Understand data flow; verify inputs and outputs are correctly mapped; check for missing or unexpected dependencies |
| **Migrations list** | Monitor job queue; navigate to completed jobs; upload new SAS files |
| **Explain page** | Ask questions about specific SAS constructs they're unfamiliar with |

### Key metrics they care about

- Reconciliation pass/fail per block
- Blocks requiring manual review (`strategy: manual`, `strategy: manual_ingestion`)
- Untranslatable blocks (`# SAS-UNRECOGNIZED`)
- Overall confidence score

### Actions they take

- Edit generated Python code inline (Editor tab → View Code)
- Trigger a refine run on a failing block
- Upload reference CSVs for reconciliation
- Download the migration zip for handoff to QA

---

## P2 — Product Owner / Business Analyst

**Goal:** Understand what the migrated pipeline does and trust that it preserves the original business logic. Does not read code. Needs to sign off before a migration goes to production.

**Background:** Knows the business domain well (finance, pharma, analytics). Understands inputs and outputs conceptually. Cannot evaluate Python or SAS syntax.

### Primary views

| View | What they use it for |
|---|---|
| **Job Detail — Report tab** | Read the plain-English summary of what the pipeline does; verify the description matches expectations |
| **Job Detail — Plan tab (summary card)** | Check the top-level confidence score, block count, risk tier, and whether any blocks need attention |
| **Migrations list** | Track overall migration progress; see which jobs are done vs under review |

### Key metrics they care about

- Overall migration confidence (e.g. "87% confident")
- Risk tier (Low / Medium / High)
- Number of blocks needing attention
- Migration status (proposed → accepted)

### Actions they take

- Read the plain-English report and flag concerns to the technical lead
- Accept a completed migration (moves status from `proposed` to `accepted`)
- Add notes or questions via the Explain chat

---

## Persona × Feature mapping

| Feature | P1 (Technical Lead) | P2 (PO / Analyst) |
|---|---|---|
| Plan tab — block table | Primary | Summary card only |
| Editor tab | Primary | Not used |
| Report tab | Secondary (skim) | Primary |
| Lineage tab | Primary | Occasionally (high-level) |
| Explain chat | For SAS questions | For business logic questions |
| Migrations list | Operational | Progress tracking |
| Download zip | Handoff to QA | Not used |

---

## Out of scope (Phase 3+)

A third persona — **compliance officer / auditor** — will need read-only access to audit records, immutable reconciliation reports, and full data lineage. This is not differentiated in the current UI (they would use the same views as P2). Persona-differentiated UX for auditors is planned for Phase 3+ (see GitHub issue #30).
