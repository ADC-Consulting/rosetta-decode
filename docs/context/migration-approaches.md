# SAS Migration Approaches

Four approaches exist for migrating SAS to a modern cloud platform. This document explains each and justifies the choice made for this tool.

---

## Approach 1 — Migrate Datasets Only

Export SAS datasets (`.sas7bdat`) to cloud storage and load them with pandas or Spark. The SAS programs remain untouched.

**Pros:** Fast to execute. Gets data into the cloud quickly.  
**Cons:** Not a real migration. SAS license and operational dependency remain. Legacy logic stays opaque.  
**When useful:** As a first step to familiarise users with the new environment using familiar data.

---

## Approach 2 — Automated Code Conversion Tool

Use a dedicated SAS-to-Python conversion tool (commercial or open source). Typically achieves ~90% coverage; the remaining 10% requires manual intervention.

**Pros:** Reasonably fast. Some tooling exists.  
**Cons:** Converted code is procedural Python, not idiomatic Spark/SQL. Significant technical debt. Hard-coded values and undocumented logic survive the conversion unchanged. The team still needs to understand what the code does.

---

## Approach 3 — LLM-Assisted Conversion (this tool)

Use an LLM to convert SAS code to Python, but with structured prompting, pattern catalogs, provenance tracking, and automated reconciliation. The LLM does not just transliterate — it can also explain, infer intent, and flag uncertainty.

**Pros:** Faster than manual, cheaper than commercial tools. Can explain legacy logic, not just convert it. Produces audit-ready output with provenance. Reconciliation proves correctness.  
**Cons:** Skills (prompts, patterns) must be built and maintained. Some manual review still required for edge cases. LLMs can hallucinate — reconciliation is the safety net.

**This is the approach implemented by this tool.** The key differentiators vs a naive LLM conversion:
- Pattern catalog guides the LLM (see `sas-patterns.md`)
- Provenance comments on every line
- Automated reconciliation as proof of correctness
- Untranslatable constructs are surfaced, not silently dropped

---

## Approach 4 — Full Refactor

Rebuild from scratch: remodel the business logic in modern SQL/PySpark, validated against business requirements rather than legacy SAS outputs.

**Pros:** No technical debt. Clean architecture. Data is modelled for the AI era.  
**Cons:** Expensive and time-consuming, especially with thousands of SAS scripts. Requires deep business domain knowledge. Hard to justify to stakeholders.

**When useful:** After approach 3 has delivered value and trust — use the LLM-generated explanations as a starting point for refactoring with full business understanding.
