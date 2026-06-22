"""Rule-based, LLM-free scoping engine for the F77 assessment report.

Turns a :class:`ParseResult` (plus the uploaded file contents) into a
deterministic :class:`ScopingReport`. Pure Python: no LLM calls and no I/O
beyond the data passed in. Same SAS input + same rate table → byte-identical
report (the run timestamp is injected at render time, never here).

Classification is grounded entirely in confirmed parser signals:
- per-file complexity tier (``simple`` / ``moderate`` / ``complex``),
- a static per-:class:`BlockType` translation-category map,
- rule-based risk flags reusing :func:`detect_missing_dependencies`.

Honors DECISIONS.md: assessment works without an LLM, risk assessment is
rule-based, and undetectable signals are explicitly labelled in
:attr:`ScopingReport.notes` rather than silently dropped.
"""

# SAS: src/worker/engine/scoping.py:1
import os
import re
from collections import Counter

from .dependency_checker import _extract_macro_invocations, detect_missing_dependencies
from .estimation_model import estimate_effort
from .models import (
    BlockBreakdown,
    BlockType,
    ComplexityTier,
    DataAssetInventory,
    FileInventoryItem,
    MacroDef,
    ParseResult,
    RiskFlag,
    SASBlock,
    ScopingReport,
    TranslationCategory,
)

# Heavy-macro-nesting threshold: a macro is "heavily nested" when a nested
# %macro appears in its body, or when %do/%if nesting depth exceeds this value.
# Named constant so the rule is tunable in one place.
MACRO_NESTING_DEPTH_THRESHOLD = 2

# Static, exhaustive translation-category map keyed by BlockType. Kept in one
# place so adding a new BlockType without categorising it fails a test rather
# than silently defaulting. Rationale per entry:
#   - DATA_STEP + most catalog PROCs: deterministic structural translation → auto.
#   - PROC_SQL: joins / inline macros frequently need a human pass → needs_review.
#   - PROC_FORMAT / PROC_PRINT / PROC_CONTENTS / PROC_DATASETS: reporting / catalog
#     ops that translate mechanically but benefit from a glance → needs_review.
#   - PROC_IML / PROC_OPTMODEL / PROC_FCMP / PROC_UNKNOWN: no faithful library
#     mapping (matrix lang, solver, custom funcs, unknown PROC) → manual.
#   - UNTRANSLATABLE: genuinely unparsable SAS → untranslatable.
_CATEGORY_BY_TYPE: dict[BlockType, TranslationCategory] = {
    BlockType.DATA_STEP: "auto_translatable",
    BlockType.PROC_SORT: "auto_translatable",
    BlockType.PROC_MEANS: "auto_translatable",
    BlockType.PROC_FREQ: "auto_translatable",
    BlockType.PROC_TRANSPOSE: "auto_translatable",
    BlockType.PROC_IMPORT: "auto_translatable",
    BlockType.PROC_EXPORT: "auto_translatable",
    BlockType.PROC_APPEND: "auto_translatable",
    BlockType.PROC_RANK: "auto_translatable",
    BlockType.PROC_SQL: "needs_review",  # joins/subqueries/inline macros often need review
    BlockType.PROC_FORMAT: "needs_review",  # format catalog needs verifying
    BlockType.PROC_PRINT: "needs_review",  # reporting output, no exact equivalent
    BlockType.PROC_CONTENTS: "needs_review",  # metadata listing
    BlockType.PROC_DATASETS: "needs_review",  # library admin ops
    BlockType.PROC_IML: "manual",  # matrix language — no library mapping
    BlockType.PROC_OPTMODEL: "manual",  # optimisation solver — manual port
    BlockType.PROC_FCMP: "manual",  # user-defined functions — manual port
    BlockType.PROC_UNKNOWN: "manual",  # PROC not in catalog — manual triage
    BlockType.UNTRANSLATABLE: "untranslatable",  # genuinely unparsable SAS
}

# Block types that on their own keep a file in the `simple` tier.
_SIMPLE_BLOCK_TYPES: frozenset[BlockType] = frozenset({BlockType.DATA_STEP, BlockType.PROC_SORT})

# Block types that immediately escalate a file to `complex`.
_COMPLEX_BLOCK_TYPES: frozenset[BlockType] = frozenset(
    {BlockType.PROC_IML, BlockType.PROC_OPTMODEL, BlockType.PROC_UNKNOWN}
)

# Nested %macro definition signals heavy nesting on its own.
_NESTED_MACRO_RE = re.compile(r"%macro\b", re.IGNORECASE)


def _category_by_type() -> dict[BlockType, TranslationCategory]:
    """Return the static translation-category map (validated exhaustive).

    Returns:
        Mapping of every :class:`BlockType` member to its translation category.

    Raises:
        ValueError: If any ``BlockType`` member is missing from the map.
    """
    missing = [bt for bt in BlockType if bt not in _CATEGORY_BY_TYPE]
    if missing:
        raise ValueError(f"Translation category map missing BlockType(s): {missing}")
    return _CATEGORY_BY_TYPE


def _macro_nesting_depth(body: str) -> int:
    """Return the maximum %do/%if nesting depth in a macro body.

    Args:
        body: Raw SAS text of the macro body.

    Returns:
        Maximum nesting depth of %do/%if blocks (0 when none).
    """
    depth = 0
    max_depth = 0
    # Walk tokens in order so opens and closes interleave correctly.
    tokens = re.findall(r"%(?:do|if|end)\b", body, re.IGNORECASE)
    for tok in tokens:
        if tok.lower() == "%end":
            depth = max(0, depth - 1)
        else:
            depth += 1
            max_depth = max(max_depth, depth)
    return max_depth


def _is_heavily_nested(macro_def: MacroDef) -> bool:
    """Return True when a macro body is heavily nested.

    Heavy nesting = a nested ``%macro`` inside the body, or a %do/%if depth
    greater than :data:`MACRO_NESTING_DEPTH_THRESHOLD`.

    Args:
        macro_def: The macro definition to inspect.

    Returns:
        True when the body exceeds the nesting heuristics.
    """
    body = macro_def.body
    if _NESTED_MACRO_RE.search(body):
        return True
    return _macro_nesting_depth(body) > MACRO_NESTING_DEPTH_THRESHOLD


def _is_real_source(path: str) -> bool:
    """Return True for real `.sas` source files (skips `__ref_*` sentinels).

    Args:
        path: A key from the uploaded ``files`` mapping.

    Returns:
        True when the key is a genuine `.sas` source file.
    """
    return path.lower().endswith(".sas") and not path.startswith("__")


def _line_count(source: str) -> int:
    """Count lines in a source string (final line without newline included)."""
    if not source:
        return 0
    return source.count("\n") + (0 if source.endswith("\n") else 1)


def _classify_tier(
    file_blocks: list[SASBlock],
    *,
    has_heavy_nesting: bool,
    non_base_engine: bool,
    has_ods: bool,
) -> ComplexityTier:
    """Classify a single file's complexity tier deterministically.

    Args:
        file_blocks: Blocks originating from this file.
        has_heavy_nesting: True when a macro defined in this file is heavily nested.
        non_base_engine: True when the file declares a non-BASE LIBNAME engine.
        has_ods: True when the file's source contains an ODS target statement.

    Returns:
        ``"simple"``, ``"moderate"``, or ``"complex"``.
    """
    types = {b.block_type for b in file_blocks}
    has_external_io = any(b.infile_paths for b in file_blocks)

    if (
        types & _COMPLEX_BLOCK_TYPES
        or has_external_io
        or non_base_engine
        or has_heavy_nesting
        or has_ods
    ):
        return "complex"

    # simple = file's block types are a non-empty subset of {DATA_STEP, PROC_SORT}
    if types and types <= _SIMPLE_BLOCK_TYPES:
        return "simple"

    return "moderate"


# ── Assembly helpers ──────────────────────────────────────────────────────────

_ODS_TOKEN_RE = re.compile(r"\bODS\s+(?:PDF|RTF|HTML|EXCEL)\b", re.IGNORECASE)
_LIBNAME_TOKEN_RE = re.compile(r"\bLIBNAME\s+(\w+)\b", re.IGNORECASE)


def _build_file_inventory(
    parse_result: ParseResult, files: dict[str, str]
) -> list[FileInventoryItem]:
    """Build the per-file inventory with line counts and complexity tiers.

    Args:
        parse_result: Parser output.
        files: Uploaded file contents (sentinel keys are skipped).

    Returns:
        File inventory sorted by source file name for determinism.
    """
    blocks_by_file: dict[str, list[SASBlock]] = {}
    for block in parse_result.blocks:
        blocks_by_file.setdefault(block.source_file, []).append(block)

    inventory: list[FileInventoryItem] = []
    for path in sorted(files):
        if not _is_real_source(path):
            continue
        source = files[path]
        file_blocks = blocks_by_file.get(path, [])
        non_base_engine = _file_uses_non_base_engine(source, parse_result)
        has_heavy_nesting = any(
            _is_heavily_nested(md) for md in parse_result.macro_defs if md.source_file == path
        )
        has_ods = bool(_ODS_TOKEN_RE.search(source))
        type_counts = Counter(str(b.block_type) for b in file_blocks)
        inventory.append(
            FileInventoryItem(
                source_file=path,
                line_count=_line_count(source),
                block_count=len(file_blocks),
                complexity_tier=_classify_tier(
                    file_blocks,
                    has_heavy_nesting=has_heavy_nesting,
                    non_base_engine=non_base_engine,
                    has_ods=has_ods,
                ),
                block_type_counts=dict(type_counts),
            )
        )
    return inventory


def _file_uses_non_base_engine(source: str, parse_result: ParseResult) -> bool:
    """Return True when a LIBNAME declared in this file uses a non-BASE engine.

    Args:
        source: Raw text of the `.sas` file.
        parse_result: Parser output (for the project-wide engine map).

    Returns:
        True when any libref declared in the file maps to a non-BASE engine.
    """
    for match in _LIBNAME_TOKEN_RE.finditer(source):
        libref = match.group(1)
        engine = parse_result.libname_engines.get(libref)
        if engine is not None and engine.upper() != "BASE":
            return True
    return False


def _build_block_breakdown(parse_result: ParseResult, files: dict[str, str]) -> BlockBreakdown:
    """Build the project-wide block breakdown including macro pseudo-types.

    Args:
        parse_result: Parser output.
        files: Uploaded file contents (sentinel keys skipped for macro-call scan).

    Returns:
        A :class:`BlockBreakdown` with counts and per-type categories.
    """
    counts: Counter[str] = Counter(str(b.block_type) for b in parse_result.blocks)
    total_blocks = len(parse_result.blocks)

    # Macro pseudo-types (not counted in total_blocks).
    counts["macro_def"] = len(parse_result.macro_defs)
    macro_calls: Counter[str] = Counter()
    for path, source in files.items():
        if _is_real_source(path):
            macro_calls.update(_extract_macro_invocations(source))
    counts["macro_call"] = sum(macro_calls.values())

    category_map = _category_by_type()
    category_by_type: dict[str, TranslationCategory] = {
        str(b.block_type): category_map[b.block_type] for b in parse_result.blocks
    }
    return BlockBreakdown(
        counts_by_type=dict(counts),
        category_by_type=category_by_type,
        total_blocks=total_blocks,
    )


# Implicit librefs that never need a LIBNAME declaration.
_IMPLICIT_LIBREFS: frozenset[str] = frozenset({"work", "sashelp", "sasuser"})


def _dataset_libref(dataset: str) -> str | None:
    """Return the lowercased libref of a ``libref.member`` dataset, else None."""
    if "." in dataset:
        return dataset.split(".", 1)[0].lower()
    return None


def _known_librefs(parse_result: ParseResult) -> frozenset[str]:
    """Return all librefs considered known (mapped, engine-declared, or implicit).

    A libref is known if it appears in EITHER ``libname_map`` OR
    ``libname_engines`` (engine-form LIBNAME populates only the latter), or is a
    built-in implicit library. Lowercased for comparison.

    Args:
        parse_result: Parser output.

    Returns:
        Frozen set of lowercased known librefs.
    """
    known = {k.lower() for k in parse_result.libname_map}
    known |= {k.lower() for k in parse_result.libname_engines}
    known |= _IMPLICIT_LIBREFS
    return frozenset(known)


def _collect_datasets(parse_result: ParseResult) -> tuple[list[str], list[str]]:
    """Return sorted unique (input_datasets, output_datasets) across all blocks."""
    inputs: set[str] = set()
    outputs: set[str] = set()
    for block in parse_result.blocks:
        inputs.update(block.input_datasets)
        outputs.update(block.output_datasets)
    return sorted(inputs), sorted(outputs)


def _build_risk_flags(parse_result: ParseResult, files: dict[str, str]) -> list[RiskFlag]:
    """Assemble all rule-based risk flags for the report.

    Args:
        parse_result: Parser output.
        files: Uploaded file contents.

    Returns:
        Risk flags ordered: missing macros/includes, unknown procs,
        external dependencies, missing reference data.
    """
    flags: list[RiskFlag] = []
    flags.extend(_missing_dependency_flags(parse_result, files))
    unknown = _unknown_proc_flag(parse_result)
    if unknown is not None:
        flags.append(unknown)
    external = _external_dependency_flag(parse_result, files)
    if external is not None:
        flags.append(external)
    missing_ref = _missing_reference_data_flag(parse_result)
    if missing_ref is not None:
        flags.append(missing_ref)
    return flags


def _missing_dependency_flags(parse_result: ParseResult, files: dict[str, str]) -> list[RiskFlag]:
    """Map ``detect_missing_dependencies`` output into missing_macro/include flags."""
    deps = detect_missing_dependencies(parse_result, files)
    flags: list[RiskFlag] = []
    macros = [d for d in deps if d.type == "macro"]
    includes = [d for d in deps if d.type == "include"]
    if macros:
        flags.append(
            RiskFlag(
                kind="missing_macro",
                severity="high",
                message=f"{len(macros)} macro(s) invoked but not defined in the upload.",
                detail=[{"name": d.name, "reference_count": d.reference_count} for d in macros],
                count=len(macros),
            )
        )
    if includes:
        flags.append(
            RiskFlag(
                kind="missing_include",
                severity="medium",
                message=f"{len(includes)} %INCLUDE file(s) referenced but not uploaded.",
                detail=[d.name for d in includes],
                count=len(includes),
            )
        )
    return flags


def _unknown_proc_flag(parse_result: ParseResult) -> RiskFlag | None:
    """Flag blocks whose PROC is not in the translation catalog."""
    locations = [
        {
            "source_file": b.source_file,
            "start_line": str(b.start_line),
            "end_line": str(b.end_line),
        }
        for b in parse_result.blocks
        if b.block_type == BlockType.PROC_UNKNOWN
    ]
    if not locations:
        return None
    return RiskFlag(
        kind="unknown_proc",
        severity="high",
        message=f"{len(locations)} PROC step(s) not in the translation catalog.",
        detail=locations,
        count=len(locations),
    )


def _external_dependency_flag(parse_result: ParseResult, files: dict[str, str]) -> RiskFlag | None:
    """Flag external file paths and non-BASE engine libnames not in the upload."""
    uploaded_basenames = {os.path.basename(k) for k in files if not k.startswith("__")}
    external: list[str] = list(parse_result.external_file_paths)
    non_base_libnames = sorted(
        f"{ref} ({engine})"
        for ref, engine in parse_result.libname_engines.items()
        if engine.upper() != "BASE"
    )

    # Keep external paths whose basename is not among uploaded files.
    unresolved_paths = sorted(p for p in external if os.path.basename(p) not in uploaded_basenames)

    if not unresolved_paths and not non_base_libnames:
        return None
    detail: dict[str, list[str]] = {
        "external_file_paths": unresolved_paths,
        "non_base_engine_libnames": non_base_libnames,
    }
    return RiskFlag(
        kind="external_dependency",
        severity="medium",
        message=(
            f"{len(unresolved_paths)} external file path(s) and "
            f"{len(non_base_libnames)} non-BASE engine LIBNAME(s) reference data "
            "outside the upload."
        ),
        detail=detail,
        count=len(unresolved_paths) + len(non_base_libnames),
    )


def _missing_reference_data_flag(parse_result: ParseResult) -> RiskFlag | None:
    """Flag input datasets whose libref is neither mapped nor engine-declared.

    Honors the S-A gotcha: engine-form ``LIBNAME x oracle "..."`` populates
    ``libname_engines`` (not ``libname_map``), so such librefs are KNOWN and
    must not be flagged.
    """
    known = _known_librefs(parse_result)
    unmapped: set[str] = set()
    for block in parse_result.blocks:
        for dataset in block.input_datasets:
            libref = _dataset_libref(dataset)
            if libref is not None and libref not in known:
                unmapped.add(libref)
    if not unmapped:
        return None
    detail = sorted(unmapped)
    return RiskFlag(
        kind="missing_reference_data",
        severity="high",
        message=(
            f"{len(detail)} input dataset libref(s) are unmapped "
            "(no LIBNAME and not an implicit library)."
        ),
        detail=detail,
        count=len(detail),
    )


def _build_data_assets(parse_result: ParseResult) -> DataAssetInventory:
    """Assemble the data-asset inventory (libnames, datasets, external paths)."""
    librefs = sorted(set(parse_result.libname_map) | set(parse_result.libname_engines))
    libnames: list[dict[str, str]] = []
    for ref in librefs:
        entry: dict[str, str] = {
            "libref": ref,
            "engine": parse_result.libname_engines.get(ref, "BASE"),
        }
        path = parse_result.libname_map.get(ref)
        if path is not None:
            entry["path"] = path
        libnames.append(entry)

    inputs, outputs = _collect_datasets(parse_result)
    return DataAssetInventory(
        libnames=libnames,
        input_datasets=inputs,
        output_datasets=outputs,
        external_file_paths=list(parse_result.external_file_paths),
    )


def _detectability_notes() -> list[str]:
    """Return explicit labels for signals not statically detectable (no silent caps)."""
    return [
        "Effort estimate uses a PROVISIONAL placeholder rate table; not yet "
        "calibrated against real engagements.",
        "Macro-generated logic is included as expanded by the parser; runtime-only "
        "macro branches (e.g. driven by &SYSPARM) cannot be detected statically.",
        "Dataset row counts and column-level data quality are not assessed without "
        "the actual data files.",
        "%INCLUDE paths containing macro-variable references are skipped (unresolvable "
        "at static analysis time).",
        "External resources behind non-BASE LIBNAME engines (e.g. Oracle, Teradata) "
        "are flagged but their contents cannot be inspected.",
    ]


def build_scoping_report(parse_result: ParseResult, files: dict[str, str]) -> ScopingReport:
    """Assemble a deterministic, LLM-free scoping report.

    Args:
        parse_result: Output of ``SASParser.parse()``.
        files: Uploaded file contents keyed by path. Non-`.sas` keys and
            ``__ref_*`` sentinels are ignored for inventory/line counts.

    Returns:
        A fully populated :class:`ScopingReport`. Same input + same rate table
        yields a byte-identical report (no timestamp baked in here).
    """
    file_inventory = _build_file_inventory(parse_result, files)
    block_breakdown = _build_block_breakdown(parse_result, files)
    risk_flags = _build_risk_flags(parse_result, files)
    data_assets = _build_data_assets(parse_result)
    effort_estimate = estimate_effort(file_inventory)

    total_files = len(file_inventory)
    total_lines = sum(item.line_count for item in file_inventory)
    total_blocks = block_breakdown.total_blocks

    return ScopingReport(
        total_files=total_files,
        total_lines=total_lines,
        total_blocks=total_blocks,
        file_inventory=file_inventory,
        block_breakdown=block_breakdown,
        risk_flags=risk_flags,
        data_assets=data_assets,
        effort_estimate=effort_estimate,
        notes=_detectability_notes(),
    )
