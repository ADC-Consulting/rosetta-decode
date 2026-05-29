# F24 — SAS Editor Fidelity

**Phase:** 3
**Area:** Frontend
**Status:** complete

## Goal

The Monaco SAS editor in the Editor tab currently has syntax highlighting but does not feel like SAS Studio or Enterprise Guide to an experienced SAS programmer. Keywords are nearly indistinguishable from identifiers (colour too dark), the most common SAS comment style (`* text;`) is not highlighted, SAS built-in functions have no distinct visual treatment, key statements like `DELETE` are missing from the keyword list, and there is no code folding for DATA/PROC/DO blocks. This feature fixes all five gaps in a single file with no backend changes.

Done looks like: an experienced SAS programmer opens the Editor tab and recognises the colour scheme, sees fold arrows on DATA and PROC blocks, and can distinguish keywords, functions, macros, strings, and comments at a glance.

## Acceptance Criteria

- [ ] SAS keywords render in a clearly visible blue (`#0070C0` light / `#569CD6` dark) — distinct from identifiers at normal editor font size
- [ ] SAS built-in functions (`missing`, `substr`, `trim`, `input`, `put`, `catx`, `compress`, `scan`, `upcase`, `lowcase`, `strip`, `length`, `index`, `tranwrd`, `coalescec`, `coalesce`, `int`, `round`, `sum`, `mean`, `min`, `max`, `abs`, `mod`, `floor`, `ceil`, `lag`, `dif`, `today`, `date`, `time`, `datetime`, `datepart`, `timepart`, `mdy`, `ymd`, `year`, `month`, `day`, `hour`, `minute`, `second`) render in a distinct teal/cyan colour separate from keywords
- [ ] `* text;` line comment style is highlighted as a comment
- [ ] `DELETE`, `ERROR`, `RETURN`, `LINK`, `GOTO`, `STOP`, `ABORT`, `LEAVE`, `CONTINUE` and text comparison operators `GT`, `LT`, `EQ`, `NE`, `GE`, `LE` are highlighted as keywords
- [ ] Fold arrows appear on `DATA...RUN`, `PROC...RUN`, `PROC...QUIT`, and `DO...END` blocks
- [ ] `make test` exits 0

## Subtasks

### S-A: Tokenizer improvements — functions, missing keywords, `* text;` comment fix
**File:** `src/frontend/src/components/JobDetail/registerSasLanguage.ts`
**Depends on:** none
**Done when:** A `sasFunctions` array is defined and matched as `keyword.function`; `DELETE`, `ERROR`, `LEAVE`, `CONTINUE`, `STOP`, `ABORT`, `LINK`, `GOTO`, `RETURN` and text operators `GT`, `LT`, `EQ`, `NE`, `GE`, `LE` are added to `keywords`; the `* text;` comment rule is reordered before the operator rule and validated to match at line start.
- [x] done

---

### S-B: Theme brightness — update sas-light + sas-dark colour values
**File:** `src/frontend/src/components/JobDetail/registerSasLanguage.ts`
**Depends on:** S-A
**Done when:** `sas-light` keyword foreground changes from `0000C0` to `0070C0`; a `keyword.function` rule with foreground `007070` is added to both `sas-light` and `sas-dark`; dark theme `keyword.function` foreground is `4EC9B0`.
- [x] done

---

### S-C: Code folding for DATA / PROC / DO blocks
**File:** `src/frontend/src/components/JobDetail/registerSasLanguage.ts`
**Depends on:** none
**Done when:** `monaco.languages.registerFoldingRangeProvider("sas", ...)` is called inside `registerSasLanguage`; the provider scans line content case-insensitively and returns fold ranges for `DATA...RUN`, `PROC...RUN`, `PROC...QUIT`, and `DO...END` pairs.
- [x] done

---

### S-D: `make test` exits 0
**File:** n/a
**Depends on:** S-A, S-B, S-C
**Done when:** `make test` exits 0 — tsc, eslint, and frontend-build all pass.
- [x] done

## Dependencies on other features

- None — pure change to `registerSasLanguage.ts`; `EditorTab.tsx` `beforeMount` wiring requires no modification

## Out of scope for this feature

- SAS-specific autocomplete / IntelliSense (PROC options, function signatures)
- Hover documentation for SAS functions
- SAS formatter / auto-indent on semicolons
- `PROC`-specific option keyword highlighting (e.g. `DATAFILE=`, `GUESSINGROWS=`)
- Dark mode theme parity beyond adding `keyword.function`
