# Personas

**Updated 2026-09-25:** P1 and P2 below describe who uses rosetta-decode once a client engagement
is underway and their own team owns the tool day to day. That is not who's using it right now.
Current usage is demo- and engagement-kickoff-led — see **P0** below, which should be the primary
lens for near-term UX decisions (e.g. sidebar navigation, #52) until the tool is actually embedded
in a client's ongoing workflow. P1/P2 remain the design target for depth (Plan/Editor/ETL detail,
reconciliation, etc.) and should stay documented for that reason, not discarded.

---

## P0 — ADC Consultant (current primary user)

**Goal:** Use the tool live in front of a prospective or newly-engaged client to show concretely
what modernizing their SAS estate would look like, and to do real early-stage work — scoping and a
first migration pass — at the start of an actual engagement. Needs to build credibility fast: a
non-technical stakeholder in the room has to trust the output without reading code, while the
consultant needs enough depth on screen to field a skeptical technical question.

**Background:** An ADC team member, not the client. Deeply familiar with the tool already (unlike
P1/P2, who are seeing it for the first time). Comfortable narrating both the SAS source and the
generated Python to an audience that mostly can't read either.

### Primary views

| View | What they use it for |
|---|---|
| **Migrations list** | Entry point — picks a seeded demo job (industry/vertical-matched) or the client's own small pilot upload; needs to read as a credible portfolio at a glance, not a raw job queue |
| **Plan tab** | The core narrative surface — confidence, risk, what needs review — walked through live |
| **Docs page / Report tab** | The trust-closing moment: the plain-English proof it's not a black box, shown to whoever in the room can't read code |
| **ETL / Data Storage tabs** | Depth-on-demand when a technical stakeholder wants to see under the hood |
| **Explain chat** | A differentiator moment — showing the AI can answer questions live |

### Key metrics they care about

- How fast they can get to a compelling result from a cold start
- Whether the story reads clearly to someone who has never seen the tool before
- Whether confidence/risk numbers hold up under a skeptical technical question

### Actions they take

- Upload or select a demo/pilot SAS project
- Narrate the Plan tab and Report/Docs content live, in front of the client
- Field "what about this SAS construct" questions via Explain
- (Future) scope an engagement before committing to a full migration — see GitHub issue #113

### Secondary audience — Prospect / Client Stakeholder

Mostly watching, not driving the UI. Cares about the same trust signals P2 cares about (confidence,
risk, plain-English explanation) but consumes them passively, narrated by the consultant, rather
than navigating tabs themselves. Their bar is "does this look credible for data like ours," not
"let me click through every view."

---

## P1 — Technical Lead / Data Engineer

*(End-state persona — a client's own technical lead, once they're embedded in the tool day to day.)*

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

*(End-state persona — a client's own PO/analyst, once they're embedded in the tool day to day.)*

**Goal:** Understand what the migrated pipeline does and trust that it preserves the original business logic. Does not read code. Needs to sign off before a migration goes to production.

**Background:** Knows the business domain well (finance, pharma, analytics). Understands inputs and outputs conceptually. Cannot evaluate Python or SAS syntax.

### Primary views

| View | What they use it for |
|---|---|
| **Job Detail — Report tab** | Read the plain-English summary of what the pipeline does; verify the description matches expectations |
| **Job Detail — Plan tab (summary card)** | Check the top-level confidence score, block count, risk tier, and whether any blocks need attention |
| **Docs page** | Browse documentation cards across all migrations; read plain-English and technical doc tabs side by side; check confidence/risk badges without navigating into individual jobs |
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

| Feature | P0 (Consultant, current) | P1 (Technical Lead, end-state) | P2 (PO / Analyst, end-state) |
|---|---|---|---|
| Migrations list | Primary — demo entry point | Operational | Progress tracking |
| Plan tab — block table | Primary — narrated live | Primary | Summary card only |
| Editor tab | Occasionally — depth-on-demand | Primary | Not used |
| ETL / Data Storage tabs | Occasionally — depth-on-demand | Primary | Occasionally (high-level) |
| Report tab | Primary — trust-closing moment | Secondary (skim) | Primary |
| Docs page | Primary — trust-closing moment | Occasionally | Primary (cross-migration overview) |
| Explain chat | Primary — differentiator moment | For SAS questions | For business logic questions |
| Global Lineage page | Not used | Unclear — see #52 | Not used |
| Download zip | Not used | Handoff to QA | Not used |

---

## Out of scope (Phase 3+)

A third persona — **compliance officer / auditor** — will need read-only access to audit records, immutable reconciliation reports, and full data lineage. This is not differentiated in the current UI (they would use the same views as P2). Persona-differentiated UX for auditors is planned for Phase 3+ (see GitHub issue #30).
