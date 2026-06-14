"""Shared post-processing utilities for translation agents.

All three translation agents (DataStepAgent, ProcAgent, GenericProcAgent) produce
a python_code string and an output_var string from their LLM call.  The LLM
sometimes uses the libname-qualified form (e.g. ``rawdir_customers`` or
``rawdir.customers``) instead of the required stem-only form (``customers``).
These helpers normalise both fields in one place so each agent delegates the fix
rather than duplicating it.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from src.worker.engine.format_catalog import normalize_format_name
from src.worker.engine.models import FormatDef

logger = logging.getLogger(__name__)

# A SAS ``put(<var>, <fmt>)`` call. The second argument is the format reference:
# an optional ``$`` (char-format marker), the format name with an optional numeric
# width, and a format dot. Two valid shapes are accepted: a trailing-dot form
# ``name[w].`` (e.g. ``agegr1f.``, ``agegr1f8.``, ``$sexdec.``) and the ``w.d``
# decimal-width form ``name w.d`` (e.g. ``agegr1f8.2``). Whitespace around the
# comma and arguments is tolerated (e.g. ``put( x , agegr1f. )``). Only the raw
# format token is captured; normalization is delegated to ``normalize_format_name``.
_PUT_FORMAT_RE = re.compile(
    r"\bput\s*\(\s*[^,()]+?\s*,\s*(?P<fmt>\$?\w+(?:\.\d+|\.))\s*\)",
    re.IGNORECASE,
)

# ── Shared LLM prompt rules (injected into all three translation agents) ─────

SHARED_TRANSLATION_RULES = """\

## 1. Output Format Rules

### ALWAYS generate PySpark DataFrame code — never pandas

You MUST use PySpark for ALL transformations, aggregations, joins, and I/O.
Never use pandas (pd.DataFrame, pd.read_csv, etc.) except as a last resort for
operations with no PySpark equivalent. The final variable MUST be a Spark DataFrame.

- Use these APIs:
    df.select(), df.withColumn(), df.filter(), df.groupBy(), df.join(), df.orderBy()
- Always import:
    from pyspark.sql import functions as F
    from pyspark.sql import Window
- Assume a Spark session exists as `spark`. Use the active session:
    spark = SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()
  Do NOT use SparkSession.builder.getOrCreate() alone — it can fail if no
  active SparkContext exists in the executor.
- Input DataFrames from prior blocks are already Spark DataFrames — do NOT
  convert them to pandas and back.
- NEVER introspect a prior-block DataFrame's schema before using it.
  Do NOT write: `_type = df.schema["col"].dataType` or `df.schema[col]`
  to inspect types from an upstream block. Assume the DataFrame exists
  and use it directly. Schema introspection on inter-block inputs causes
  NameError when the block runs in isolation during validation.

### Never rely on SQL as the primary output

- Do not emit spark.sql("...") as the main implementation.

### Column creation / transformation

- Use withColumn() for new derived columns and for replacing existing columns.
- Avoid SELECT *-style logic that can cause duplicate/ambiguous columns.
- NEVER cast a column to a different type just to match a reference schema.
  Preserve the natural PySpark type. If reconciliation flags a type mismatch,
  it means the reference CSV stored the column differently — the PySpark type
  is authoritative for the actual data.


## 2. Column Naming Convention — CRITICAL

Use lowercase snake_case for ALL column aliases in PySpark output.
SAS is case-insensitive and stores column names as UPPERCASE. Python/PySpark
is case-sensitive and uses lowercase. You MUST normalize on every load.

Rule: immediately after reading ANY file (read_csv, read_sas7bdat, spark.read,
etc.), lowercase all column names before any other operation:

  df = spark.read.csv(path, header=True, inferSchema=True)
  df = df.toDF(*[c.lower() for c in df.columns])   # ← ALWAYS do this

  ✅ .alias("total_eur")
  ✅ .alias("segment_clean")
  ❌ .alias("TOTAL_EUR")
  ❌ .alias("SEGMENT_CLEAN")

Never reference a column by its original SAS uppercase name after loading.


## 3. Carry Forward All Columns — CRITICAL

SAS procedures like PROC IML, PROC STDIZE, and DATA steps that
compute new variables preserve ALL original columns in the output
dataset by default. PySpark does not do this automatically.

Rules:
1. When translating a SAS step that computes a new column, use
   .withColumn() to APPEND it to the existing DataFrame.
   Do NOT create a new DataFrame containing only the computed column.
2. The output must include every column from the input plus any
   new columns.

  ❌ Wrong — drops all original columns:
  z_scores = df.select(
      ((F.col("value") - mean_val) / std_val).alias("z_score")
  )

  ✅ Correct — preserves all original columns:
  z_scores = df.withColumn(
      "z_score",
      (F.col("value") - mean_val) / std_val
  )

This applies to PROC IML, PROC STDIZE, PROC SCORE, and any DATA
step that adds new variables. If in doubt, keep every column from
the input and only add new ones.


## 4. Column Lifecycle & Ordering — CRITICAL

A column must EXIST in the DataFrame at the moment any transformation
references it. Two failure modes crash generated PySpark with
`[UNRESOLVED_COLUMN]`:

1. **Dropping a column before a later transform needs it.** A narrowing
   `.select(...)` or `.drop(...)` to the final output schema removes columns;
   any derivation that reads those columns must run BEFORE the narrowing,
   never after.
2. **Recomputing a column that already exists.** If a derived column was
   already built earlier in the chain, REUSE it — do not rebuild it from its
   source columns again (those sources may have been projected away, and the
   rebuild is redundant even when they survive).

Rules:
1. Derive EVERY column that depends on join keys or source columns BEFORE any
   `.select(...)`/projection that narrows the column set. Never reference a
   column in a later transform after it has been projected away.
2. Keep join keys (e.g. studyid, siteid, subjid) available until ALL downstream
   derivations that need them are complete. Only drop them at the final
   projection.
3. Place the narrowing `.select(...)`/`.drop(...)` to the final output schema as
   the LAST step, after all derivations are done.
4. Do NOT recompute a column that already exists in the DataFrame — reuse it.

  ❌ Wrong — selects the final schema first, dropping the join keys, then tries
  to derive usubjid from keys that no longer exist (and re-derives a column that
  was already built):
  df = df.select("usubjid", "age", "sex")          # drops studyid/siteid/subjid
  df = df.withColumn(                                # UNRESOLVED_COLUMN: studyid
      "usubjid",
      F.concat_ws("-", F.col("studyid"), F.col("siteid"), F.col("subjid")),
  )

  ✅ Correct — derive usubjid from the keys FIRST, then narrow to the final
  schema as the last step:
  df = df.withColumn(
      "usubjid",
      F.concat_ws("-", F.col("studyid"), F.col("siteid"), F.col("subjid")),
  )
  df = df.select("usubjid", "age", "sex")          # final projection LAST

This complements rule #3 (carry columns forward) and the join-key rules below:
keep columns AND order derivations before any narrowing, and never re-derive a
column that already exists.


## 5. Join Key Normalisation — CRITICAL

Identifier columns used as join keys (e.g. customer_id, policy_no, account_id) must be
normalised to the same type before joining. Source CSVs often store integer IDs as floats
(1000.0), while another table infers them as longs (1000). Spark type-strict equality
produces 0 rows when types differ.

For EVERY join key column: save the original type, normalise both sides, join, then restore:
    _cid_type = df1.schema["customer_id"].dataType
    df1 = df1.withColumn("customer_id",
        F.regexp_replace(F.col("customer_id").cast("string"), r"\\.0$", ""))
    df2 = df2.withColumn("customer_id",
        F.regexp_replace(F.col("customer_id").cast("string"), r"\\.0$", ""))
    result = df1.join(df2, on="customer_id", how="left")
    result = result.withColumn("customer_id", F.col("customer_id").cast(_cid_type))

Apply ONLY to identifier/key columns (IDs, codes, reference numbers).
Do NOT apply to value columns (amounts, prices, quantities, dates, metrics).

After a join, always qualify ambiguous column references with DataFrame aliases to avoid
AMBIGUOUS_REFERENCE errors:
    result = df1.alias("a").join(df2.alias("b"), on="customer_id", how="left").select(
        F.col("a.*"), F.col("b.extra_col"))


## 6. Null Handling — CRITICAL

SAS "missing" ≈ Spark NULL. Always be explicit with NULL in joins, aggregations,
and derived columns.

  # Default nulls to 0 before arithmetic
  df = df.withColumn(
      "total",
      F.coalesce(F.col("value1"), F.lit(0.0))
      + F.coalesce(F.col("value2"), F.lit(0.0))
  )

  # LEFT JOIN with default
  result_df = left_df.join(right_df, on="key", how="left").withColumn(
      "cnt", F.coalesce(F.col("cnt"), F.lit(0))
  )

  # Filter nulls explicitly
  df = df.filter(F.col("col").isNotNull() & (F.col("col") != ""))


## 7. Python vs Column Expressions — CRITICAL

Inside DataFrame operations (withColumn, filter, agg, etc.) use ONLY Column
expressions, not Python booleans or numbers.

  ❌ Wrong — Python boolean inside F.when():
  completed_count = some_df.count()   # Python int
  df = df.withColumn(
      "rate",
      F.when(completed_count > 0,
             F.col("total") / F.lit(completed_count))
  )

  ✅ Correct — Column logic only:
  df = df.withColumn(
      "rate",
      F.when(F.col("completed_count") > 0,
             F.col("total") / F.col("completed_count"))
       .otherwise(F.lit(None))
  )

  ✅ Also correct — Python outside DF ops:
  completed_count = some_df.count()
  if completed_count > 0:
      df = df.withColumn("rate", F.col("total") / F.lit(completed_count))
  else:
      df = df.withColumn("rate", F.lit(None))


## 8. Explicit Type Casting

SAS auto-coerces types; PySpark does not.

  # Cast join keys to same type
  result = members_df.alias("m").join(
      claims_df.alias("c"),
      F.col("m.member_id").cast("string") == F.col("c.member_id").cast("string"),
      "left"
  )

  # Arithmetic
  df = df.withColumn(
      "total_cost",
      F.col("quantity").cast("int") * F.col("unit_price").cast("double")
  )

  # Aggregation with explicit casts
  agg_df = df.groupBy("key").agg(
      F.count("*").cast("long").alias("row_count"),
      F.sum("amount").cast("double").alias("total_amount")
  )


## 9. No Implicit Ordering

DataFrames are unordered unless you call .orderBy().

- Add .orderBy(...) when output order matters (reports, top-N, window logic).
- Skip .orderBy() for intermediate steps to save compute.

  result_df = df.select("member_id", "score") \\
      .orderBy(F.col("score").desc(), F.col("member_id").asc())

Window functions require an orderBy in the window spec; that is separate
from global output ordering.


## 10. UDFs: Use Sparingly

Prefer native functions: F.when, F.coalesce, F.datediff, F.concat, etc.
Use Python UDFs only when logic cannot be expressed with built-ins.
Always declare the return type.

  from pyspark.sql.types import StringType
  from pyspark.sql.functions import udf

  @udf(StringType())
  def categorize_score(score):
      if score is None:
          return None
      if score >= 3.0:
          return "Very High"
      elif score >= 2.0:
          return "High"
      elif score >= 1.0:
          return "Medium"
      return "Low"


## 11. Date Conventions

- SAS dates: '01JAN2024'd → PySpark: '2024-01-01' (ISO format)
- Use Spark date type and ISO strings.
- Treat identifiers (member, customer, claim, etc.) as string.

| SAS                          | PySpark                                       |
|------------------------------|-----------------------------------------------|
| TODAY()                      | F.current_date()                              |
| YEAR(date)                   | F.year(F.col("date"))                         |
| MONTH(date)                  | F.month(F.col("date"))                        |
| DAY(date)                    | F.dayofmonth(F.col("date"))                   |
| INTNX('month',date,n)       | F.add_months(F.col("date"), n)                |
| INTNX('day',date,n)         | F.date_add(F.col("date"), n)                  |
| INTCK('day',start,end)       | F.datediff(F.col("end"), F.col("start"))      |
| INTCK('month',start,end)     | F.months_between(F.col("end"), F.col("start"))|


## 12. String Function Mappings

| SAS                          | PySpark                                       |
|------------------------------|-----------------------------------------------|
| UPCASE(str)                  | F.upper(F.col("str"))                         |
| LOWCASE(str)                 | F.lower(F.col("str"))                         |
| SUBSTR(str,pos,len)          | F.substring(F.col("str"), pos, len)           |
| TRIM(str)                    | F.trim(F.col("str"))                          |
| LENGTH(str)                  | F.length(F.col("str"))                        |
| INDEX(str,substr)            | F.instr(F.col("str"), "substr")               |
| CATX(delim,s1,s2)           | F.concat_ws(delim, *cols)                     |


## 13. Numeric / Aggregation Function Mappings

| SAS          | PySpark                          |
|--------------|----------------------------------|
| SUM(x)       | F.sum("x")                       |
| MEAN(x)      | F.mean("x")                      |
| MIN(x)       | F.min("x")                       |
| MAX(x)       | F.max("x")                       |
| STD(x)       | F.stddev("x")                    |
| COUNT(x)     | F.count("x")                     |
| ROUND(x,dec) | F.round(F.col("x"), dec)         |
| FLOOR(x)     | F.floor(F.col("x"))              |
| CEIL(x)      | F.ceil(F.col("x"))               |


## 14. PROC → PySpark Patterns

### PROC FREQ → groupBy + count
  freq_df = df.filter(F.col("year") == 2024) \\
      .groupBy("gender", "plan_type") \\
      .agg(F.count("*").alias("frequency")) \\
      .orderBy("gender", "plan_type")

### PROC MEANS → groupBy + agg
  summary_df = df.groupBy("member_id").agg(
      F.sum("paid_amount").alias("total_paid"),
      F.mean("copay_amount").alias("avg_copay"),
      F.count("*").alias("claim_count")
  )

### PROC SQL → filter/select/join
  claim_counts_df = claims_df.groupBy("member_id").agg(
      F.count("*").alias("claim_count")
  )
  result_df = members_df.alias("m").join(
      claim_counts_df.alias("c"),
      on=F.col("m.member_id") == F.col("c.member_id"),
      how="left"
  ).select(
      F.col("m.member_id"),
      F.coalesce(F.col("c.claim_count"), F.lit(0)).alias("claim_count")
  )

### PROC IML → PySpark / NumPy
PROC IML is SAS's matrix language. Common operations:
- Matrix math (means, stddev, z-scores) → use F.mean(), F.stddev() with Window or agg
- Row-level transformations → use .withColumn()
- READ/CREATE from datasets → the input DataFrame is already provided
- APPEND to datasets → the output DataFrame is returned

## 15. DATA Step → PySpark Patterns

### IF-THEN-ELSE → F.when
  df = df.withColumn(
      "age_group",
      F.when(F.col("age") < 18, "Pediatric")
       .when((F.col("age") >= 18) & (F.col("age") < 65), "Adult")
       .otherwise("Senior")
  )

### BY + RETAIN → Window + LAG
  from pyspark.sql.window import Window
  w = Window.partitionBy("member_id").orderBy("effective_date")
  df = df.withColumn("prior_plan_type", F.lag("plan_type", 1).over(w))
  df = df.withColumn(
      "plan_changed",
      F.when(
          (F.col("plan_type") != F.col("prior_plan_type")) &
          F.col("prior_plan_type").isNotNull(),
          F.lit(True)
      ).otherwise(F.lit(False))
  )


## 16. Macro Handling

### %LET → Python variables
  measurement_year = 2024
  min_age = 18
  result_df = df.filter(
      (F.col("year") == measurement_year) & (F.col("age") >= min_age)
  )

### Macro loops → Python for loops
  for plan in ["HMO", "PPO", "EPO"]:
      plan_df = df.filter(F.col("plan_type") == plan)


## 17. PUT() / User-Defined Format Handling — SCOPED RULE

**When** a format definition is supplied in the "## Available SAS formats"
section of this prompt, translate a `put(var, fmt.)` call into an explicit
`F.when(...).otherwise(...)` chain (or a broadcast lookup table for large maps)
built directly from that definition, and PRESERVE the resulting column on the
output DataFrame. Map each definition entry faithfully: single values become
equality tests, ranges become bound comparisons (respect exclusive upper bounds
shown as ``< high``), and the ``other`` catch-all becomes the trailing
``.otherwise(...)``.

  # Given format `sexdec`:  1 -> "Male", 2 -> "Female", other -> "Unknown"
  df = df.withColumn(
      "sex_label",
      F.when(F.col("sex") == 1, F.lit("Male"))
       .when(F.col("sex") == 2, F.lit("Female"))
       .otherwise(F.lit("Unknown"))
  )

**Otherwise** (no matching definition in "## Available SAS formats"), treat
`fmt` as a built-in SAS format (e.g. `dollar8.`, `date9.`, `comma12.`) and apply
the existing date/string/numeric conventions in sections #11-13. Do NOT invent a
value mapping for a format whose definition was not supplied.


## 18. Performance Patterns

  # Broadcast small tables in joins
  from pyspark.sql.functions import broadcast
  result_df = large_df.join(broadcast(small_lookup_df), "key", "left")

  # Filter early
  filtered_df = df.filter(F.col("year") == 2024).filter(F.col("status") == "PAID")

  # Cache only when reused multiple times
  base_df = spark.table("gold.members").cache()
  # ... multiple uses ...
  base_df.unpersist()


## 19. Response Expectations

When converting SAS to PySpark:
1. Return complete, runnable PySpark code (no pseudocode).
2. Include necessary imports at the top.
3. Use PySpark DataFrame API as the primary implementation.
4. Map SAS logic faithfully using idiomatic PySpark patterns.
5. Immediately lowercase all column names after every file read (rule 2).
   Use lowercase snake_case for all column aliases.
6. Preserve all input columns through transformations — use
   .withColumn() to add new columns, never drop originals
   unless the SAS code explicitly does so.
7. Handle nulls, types, and column casing explicitly.
8. Add .orderBy() when output order matters.
"""


def detect_referenced_formats(raw_sas: str) -> list[str]:
    """Find every ``put(var, fmt.)`` format reference in *raw_sas*.

    Scans for SAS ``put(<var>, <fmt>)`` calls (case-insensitive) and returns the
    normalized names of the formats referenced as the second argument. The format
    token may be ``$``-prefixed (character format) and width-suffixed; both are
    handled by :func:`normalize_format_name`. Whitespace variants such as
    ``put( x , agegr1f. )`` and ``put(sex,$sexdec.)`` are tolerated.

    Args:
        raw_sas: Raw SAS source text for a single block.

    Returns:
        De-duplicated, order-stable list of normalized format names.
    """
    seen: dict[str, None] = {}
    for match in _PUT_FORMAT_RE.finditer(raw_sas):
        normalized = normalize_format_name(match.group("fmt"))
        if normalized not in seen:
            seen[normalized] = None
    return list(seen)


def _render_format_entry(entry: Any) -> str:
    """Render one :class:`FormatEntry` as a single human-readable bullet line.

    Args:
        entry: A ``FormatEntry`` from a ``FormatDef``.

    Returns:
        A bullet line describing the entry's source operand → label mapping.
    """
    if entry.is_other:
        operand = "other"
    elif entry.value is not None:
        operand = entry.value
    else:
        bound = "< high (exclusive)" if entry.exclusive_upper else "high (inclusive)"
        operand = f"{entry.low} .. {entry.high} [{bound}]"
    return f"- {operand} -> {entry.label!r}"


def render_format_section(referenced: list[str], catalog: dict[str, FormatDef]) -> str:
    """Render a prompt section describing referenced user-defined formats.

    Only names present in *catalog* are rendered; built-in formats (e.g.
    ``dollar8.``, ``date9.``) are absent from the catalog and therefore omitted.
    Each rendered format gets a ``### <name>`` header followed by one bullet per
    entry. Rendering is deterministic and compact.

    Args:
        referenced: Normalized format names from :func:`detect_referenced_formats`.
        catalog: ``{normalized_name: FormatDef}`` (e.g. ``JobContext.format_catalog``).

    Returns:
        The rendered section under a ``## Available SAS formats`` header, or an
        empty string when none of *referenced* are in *catalog* (so callers may
        skip the section entirely).
    """
    matched = [name for name in referenced if name in catalog]
    if not matched:
        return ""
    lines: list[str] = ["## Available SAS formats"]
    for name in matched:
        fmt = catalog[name]
        kind = "character" if fmt.is_char else "numeric"
        lines.append(f"### {name} ({kind})")
        for entry in fmt.entries:
            lines.append(_render_format_entry(entry))
    return "\n".join(lines)


def build_block_output_stems(all_blocks: list[Any]) -> dict[str, str]:
    """Map every prior-block output dataset (dot AND underscore form) → stem name.

    Both ``work.ex_dedup`` and ``work_ex_dedup`` map to ``ex_dedup``.  Used by
    the prompt builder and the input-variable normalizer so they stay in sync.

    Args:
        all_blocks: All SASBlock objects in the job.

    Returns:
        Mapping from lower-cased dot-form and underscore-form dataset names to
        their stem-only variable names.
    """
    stems: dict[str, str] = {}
    for b in all_blocks:
        for ds in b.output_datasets:
            stem = ds.lower().split(".")[-1]
            stems[ds.lower()] = stem
            stems[ds.lower().replace(".", "_")] = stem
    return stems


def normalise_input_vars_in_code(
    python_code: str,
    input_datasets: list[str],
    block_output_stems: dict[str, str],
    agent_name: str,
) -> str:
    """Replace wrong input variable names in *python_code* with the correct form.

    The prompt tells the LLM which variable name to use for each input dataset
    (stem-only for prior-block outputs, underscore form for external datasets).
    When the LLM ignores that hint and writes the wrong form, this function
    corrects it deterministically — mirroring what ``normalise_output_var_in_code``
    does for output variables.

    Args:
        python_code: Generated Python source from the LLM.
        input_datasets: Dataset names from the SAS parser (may be ``libname.table``).
        block_output_stems: Map produced by ``build_block_output_stems``.
        agent_name: Agent class name used in log messages.

    Returns:
        Python source with all wrong input variable references corrected.
    """
    logger.debug(
        "%s normalise_input_vars: input_datasets=%s stems_keys=%s",
        agent_name,
        input_datasets,
        sorted(block_output_stems.keys()),
    )
    for ds in input_datasets:
        ds_lower = ds.lower()
        if ds_lower in block_output_stems:
            correct = block_output_stems[ds_lower]  # prior-block output → stem
            logger.debug("%s: '%s' found in stems → correct='%s'", agent_name, ds_lower, correct)
        else:
            correct = ds_lower.replace(".", "_")  # external → underscore form
            logger.debug(
                "%s: '%s' NOT in stems → external form '%s'", agent_name, ds_lower, correct
            )

        underscore_form = ds_lower.replace(".", "_")
        dot_form = ds_lower

        for wrong, pattern in (
            (underscore_form, rf"\b{re.escape(underscore_form)}\b"),
            (dot_form, re.escape(dot_form)),
        ):
            if wrong == correct:
                continue  # already the right form — no substitution needed
            if not re.search(pattern, python_code):
                continue
            logger.warning(
                "%s: renaming input '%s' → '%s' in generated code (LLM used wrong form)",
                agent_name,
                wrong,
                correct,
            )
            python_code = re.sub(pattern, correct, python_code)
    return python_code


def normalise_output_var(
    output_datasets: list[str],
    output_var: str | None,
) -> str | None:
    """Return *output_var* normalised to the dataset stem, or unchanged if already correct.

    Matches the LLM-returned value against every known output dataset in both the
    dot form (``libname.table``) and the underscore form (``libname_table``).  When
    a match is found the stem (``table``) is returned instead.

    Args:
        output_datasets: Dataset names from the SAS parser (may be ``libname.table``).
        output_var: Raw ``output_var`` string returned by the LLM.

    Returns:
        Stem-only variable name, or the original *output_var* if no correction needed.
    """
    if not output_var:
        return output_var
    fov = output_var.lower()
    for ds in output_datasets:
        stem = ds.lower().split(".")[-1]
        if ds.lower() == stem:
            continue  # no libname prefix — nothing to correct
        if fov in (ds.lower(), ds.lower().replace(".", "_")):
            return stem
    return output_var


def normalise_output_var_in_code(
    python_code: str,
    output_datasets: list[str],
    agent_name: str,
) -> str:
    """Replace libname-qualified output variable names in *python_code* with stems.

    For each output dataset that has a libname prefix, replaces every word-boundary
    occurrence of the underscore form (``libname_table``) in *python_code* with the
    stem (``table``).  Logs a WARNING when a substitution is made so it is visible
    in the worker logs.

    Args:
        python_code: Generated Python source from the LLM.
        output_datasets: Dataset names from the SAS parser (may be ``libname.table``).
        agent_name: Agent class name used in log messages (e.g. ``"DataStepAgent"``).

    Returns:
        Python source with all libname-qualified output variables replaced.
    """
    for ds in output_datasets:
        stem = ds.lower().split(".")[-1]  # customers
        if ds.lower() == stem:
            continue  # no libname prefix — nothing to correct
        underscore_form = ds.lower().replace(".", "_")  # outdir_customers
        dot_form = ds.lower()  # outdir.customers
        for wrong, pattern in (
            (underscore_form, rf"\b{re.escape(underscore_form)}\b"),
            (dot_form, re.escape(dot_form)),
        ):
            if not re.search(pattern, python_code):
                continue
            logger.warning(
                "%s: renaming '%s' → '%s' in generated code (LLM used libname form)",
                agent_name,
                wrong,
                stem,
            )
            python_code = re.sub(pattern, stem, python_code)
    return python_code
