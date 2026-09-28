# Competitive Positioning vs. SAS Migration Alternatives

Status: draft for issue #120
Owner: ADC / Rosetta Decode
Last updated: 2026-08-10

---

## Purpose

Define clear, evidence-based positioning for Rosetta Decode against common SAS migration alternatives, so consultants can:

- qualify opportunities faster
- explain why clients should not choose a pure manual rewrite
- show where Rosetta is stronger than simple code conversion tools
- be explicit about when Rosetta is not the best fit

This document is based on the current product capabilities in this repo (backend, worker, frontend, validation, lineage, documentation, and audit artefacts).

---

## Positioning Statement

Rosetta Decode is a proof-first SAS migration platform for regulated data teams that need to move from SAS to Python/PySpark without losing trust.

Unlike dataset-only moves, generic code converters, or one-off LLM prompts, Rosetta combines automated translation with deterministic output, reconciliation checks, provenance tagging, and audit-ready artefacts so teams can defend migration decisions in front of engineering, QA, and compliance.

---

## Category Strategy

Primary category:
- AI-assisted SAS-to-Python migration with built-in validation and audit traceability.

Not positioned as:
- a generic ETL builder
- a BI dashboard tool
- a full replacement for long-term data platform redesign programs

Practical wedge:
- migrate high-value SAS pipelines quickly
- prove parity with reconciliation
- create the evidence package needed for sign-off
- then optionally continue to deeper refactor and modernization

---

## Alternatives and Competitive Comparison

## 1) Stay on SAS (status quo)

Typical buyer logic:
- "It is expensive, but at least it works."

Strengths:
- low immediate change risk
- existing production familiarity

Weaknesses:
- ongoing license and specialist-talent dependency
- low transparency for newer teams
- weak portability to modern data/AI stacks

Rosetta position:
- preserve business logic while reducing platform lock-in
- keep migration evidence explicit (provenance + reconciliation + audit record)
- reduce organizational risk of "tribal knowledge" concentration

## 2) Data-only migration (move datasets, keep SAS jobs)

Typical buyer logic:
- "Move data first, leave code for later."

Strengths:
- fastest visible cloud movement
- low short-term disruption

Weaknesses:
- does not remove SAS runtime dependency
- no code modernization
- no migration completeness story

Rosetta position:
- delivers executable Python pipeline artefacts, not only relocated data
- makes untranslatable logic visible instead of hiding deferred work
- creates a path to full decommissioning of SAS workloads

## 3) Rule-based or traditional conversion tooling

Typical buyer logic:
- "Automate conversion with a deterministic converter and clean up manually."

Strengths:
- predictable transliteration behavior in supported patterns
- can be faster than manual rewrite for narrow procedure sets

Weaknesses:
- often procedural output with significant manual rework
- limited explanation and business readability
- limited trust layer beyond code output itself

Rosetta position:
- combines translation with confidence scoring, strategy labels, and rationale
- includes reconciliation checks as a first-class acceptance gate
- produces plain-language and technical documentation in addition to code
- stores job-level evidence (input hashes, outputs, checks, timestamps) for auditability

## 4) Generic LLM prompts or internal scripts

Typical buyer logic:
- "We can prompt an LLM ourselves and save tool cost."

Strengths:
- low setup barrier for a prototype
- flexible experimentation

Weaknesses:
- unstable output quality across runs
- weak governance and reproducibility
- no standard acceptance workflow

Rosetta position:
- deterministic migration behavior for identical input
- structured pipeline: parse -> plan -> translate -> execute -> reconcile -> report
- explicit handling of unsupported constructs (`SAS-UNTRANSLATABLE`)
- UI and API workflow for repeatable delivery, not ad-hoc scripts

## 5) Full manual rewrite / full refactor programs

Typical buyer logic:
- "Rebuild correctly from scratch and avoid legacy baggage."

Strengths:
- best long-term architecture potential
- maximum design freedom

Weaknesses:
- highest cost and timeline risk
- heavy dependency on domain experts
- slower time-to-value and delayed de-risking

Rosetta position:
- faster path to validated migration output
- reduces uncertainty early with measurable parity checks
- can be used as a transitional step before selective deep refactor

---

## Why Rosetta Wins (Where It Is Strongest)

Rosetta is strongest when clients need all of the following:

- trustable migration evidence, not just translated code
- faster delivery than manual rewrite
- compliance-friendly traceability
- optional local or Databricks target model
- cross-persona visibility (engineers, product owners, QA/compliance)

Capability proof points from the current product:

- deterministic output for identical SAS input
- per-line provenance comments in generated code
- explicit unsupported-construct marking
- reconciliation checks (schema, row count, aggregate parity)
- downloadable artefact package (pipeline, reconciliation report, audit record)
- migration plan with confidence/strategy signaling
- lineage and documentation surfaces in UI

---

## Where Rosetta Is Not the Best Fit

Be explicit early to preserve credibility.

Not ideal when:

- client only wants file-format relocation and will keep SAS permanently
- no tolerance for any manual review on edge SAS constructs
- migration scope is tiny and one-time, with no need for repeatable governance
- client expects instant full statistical-procedure parity without review workflow

In these cases, position Rosetta as:
- optional accelerator for selected high-risk/high-value flows, or
- a later-stage tool after initial scope expansion

---

## Ideal Customer Profile Alignment (Issue #117 dependency)

Best-fit account profile:

- regulated or audit-sensitive sectors (finance, pharma, insurance, public sector)
- meaningful SAS estate with business-critical ETL logic
- pressure to modernize to Python/PySpark and cloud data platforms
- delivery teams that need both technical and non-technical sign-off

Buyer group map:

- Technical Lead / Data Engineer: code quality, runtime confidence, remediation workflow
- Product Owner / Analyst: plain-language understanding, risk and confidence visibility
- QA / Compliance: immutable artefacts and reproducible migration evidence

---

## Battlecard Messaging

Core message:
- "Do not buy conversion output. Buy migration proof."

Three value pillars:

- Speed with control: automated translation plus guided remediation
- Trust by design: reconciliation and provenance are part of the core flow
- Audit readiness: every migration emits an inspectable evidence package

Common objections and responses:

- "We can do this with prompts ourselves."
  - Response: prompts can generate code; they do not provide a repeatable acceptance system with deterministic behavior, reconciliation workflow, and durable audit artefacts.

- "We should refactor everything from scratch."
  - Response: full refactor is often right eventually, but Rosetta reduces risk first by proving parity and surfacing uncertain blocks before large-scale redesign spend.

- "Traditional converters are more deterministic."
  - Response: determinism matters, and Rosetta includes deterministic output plus validation and explainability layers typically missing in pure transliteration tools.

---

## Competitive Decision Matrix (Consulting Use)

Use this in discovery and proposal conversations.

| Option | Time to first usable output | Confidence evidence | Audit traceability | Long-term portability | Typical cost/risk profile |
|---|---|---|---|---|---|
| Stay on SAS | Immediate | Existing only | Limited modernization evidence | Low | High ongoing license + talent risk |
| Data-only move | Fast | Low for logic parity | Low | Medium | Defers core migration risk |
| Traditional converter | Medium | Medium | Medium | Medium | Medium rework burden |
| Generic LLM scripts | Fast prototype | Low to medium | Low | Medium | Quality/governance variability |
| Full manual refactor | Slow | High (if fully tested) | High | High | Highest near-term cost and schedule risk |
| Rosetta Decode | Fast to medium | High (reconciliation + confidence + provenance) | High | High | Balanced speed/risk for regulated migration |

---

## Packaging for Client Conversations

Recommended sequencing across related go-to-market issues:

- #117 ICP: define who to target first
- #119 ROI benchmark: quantify value against manual and converter alternatives
- #120 positioning (this doc): define why Rosetta wins
- #122 pilot design: convert positioning into a concrete 6-12 week engagement
- #123 sales playbook: operationalize messaging and qualification

---

## Next Content to Produce

To make this positioning executable in the field, produce:

- a 1-page external version (client-safe language, no internal implementation detail)
- a 10-question qualification checklist linked to the matrix above
- two reference architectures (local-first and Databricks-first) for proposal appendices
- one "when not to choose Rosetta" slide to strengthen trust in advisory conversations

---

## Decision

Use this positioning as the default narrative for competitive conversations until ROI and ICP docs are finalized. Update the matrix once issue #119 (ROI benchmark) produces measured conversion baselines.