# SAS Pattern Catalog

Reference for the LLM product layer and for the `sas-translator` skill. Each entry maps a SAS construct to its Python/PySpark equivalent and notes edge cases.

---

## DATA Step

### Basic SET + transformation

```sas
/* SAS */
DATA output;
    SET input;
    new_col = col_a * 1.2;
    IF col_b > 0 THEN flag = 1; ELSE flag = 0;
RUN;
```

```python
# pandas (CLOUD=false)
output = input.copy()                     # SAS: script.sas:2
output["new_col"] = output["col_a"] * 1.2 # SAS: script.sas:3
output["flag"] = (output["col_b"] > 0).astype(int)  # SAS: script.sas:4

# PySpark (CLOUD=true)
from pyspark.sql import functions as F
output = input \
    .withColumn("new_col", F.col("col_a") * 1.2) \
    .withColumn("flag", F.when(F.col("col_b") > 0, 1).otherwise(0))
```

**Edge cases:**
- SAS missing values (`.`) map to `None`/`NaN` in Python — handle with `pd.isna()` or `F.isnan()`
- SAS character vs numeric types must be preserved; LLM must infer from context

---

### KEEP / DROP

```sas
DATA output;
    SET input;
    KEEP col_a col_b col_c;
RUN;
```

```python
# pandas
output = input[["col_a", "col_b", "col_c"]].copy()  # SAS: script.sas:3

# PySpark
output = input.select("col_a", "col_b", "col_c")
```

---

### WHERE filter

```sas
DATA output;
    SET input;
    WHERE col_a > 100;
RUN;
```

```python
# pandas
output = input[input["col_a"] > 100].copy()  # SAS: script.sas:3

# PySpark
output = input.filter(F.col("col_a") > 100)
```

---

## PROC SQL

### Basic SELECT

```sas
PROC SQL;
    CREATE TABLE output AS
    SELECT col_a, SUM(col_b) AS total_b
    FROM input
    GROUP BY col_a;
QUIT;
```

```python
# pandas
output = input.groupby("col_a", as_index=False).agg(total_b=("col_b", "sum"))  # SAS: script.sas:2

# PySpark (via SQL string or DataFrame API)
output = input.groupBy("col_a").agg(F.sum("col_b").alias("total_b"))
```

---

### JOIN

```sas
PROC SQL;
    CREATE TABLE output AS
    SELECT a.*, b.col_x
    FROM table_a AS a
    LEFT JOIN table_b AS b ON a.key = b.key;
QUIT;
```

```python
# pandas
output = table_a.merge(table_b[["key", "col_x"]], on="key", how="left")  # SAS: script.sas:2

# PySpark
output = table_a.join(table_b.select("key", "col_x"), on="key", how="left")
```

---

## PROC SORT

```sas
PROC SORT DATA=input OUT=output;
    BY col_a DESCENDING col_b;
RUN;
```

```python
# pandas
output = input.sort_values(["col_a", "col_b"], ascending=[True, False])  # SAS: script.sas:1

# PySpark
output = input.orderBy(F.col("col_a").asc(), F.col("col_b").desc())
```

---

## Macro Variables

```sas
%LET threshold = 100;
DATA output;
    SET input;
    IF value > &threshold THEN flag = 1;
RUN;
```

```python
# Resolved at parse time — macro variables become Python constants
THRESHOLD = 100  # SAS: script.sas:1 (macro variable)
output = input.copy()
output["flag"] = (output["value"] > THRESHOLD).astype(int)  # SAS: script.sas:4
```

---

## Untranslatable Constructs

The following SAS constructs have no direct Python equivalent and must be flagged:

| Construct | Reason | Flag |
|---|---|---|
| PROC MIXED | Statistical procedure, no pandas/Spark equivalent | `# SAS-UNTRANSLATABLE: PROC MIXED — use statsmodels manually` |
| ODS statements | Output delivery system, not data transformation | `# SAS-UNTRANSLATABLE: ODS — reporting only, no data output` |
| PROC REPORT | Report formatting | `# SAS-UNTRANSLATABLE: PROC REPORT — reporting only` |
| `%INCLUDE` | File inclusion — must be resolved before parsing | `# SAS-UNTRANSLATABLE: %INCLUDE — resolve source file manually` |
| Platform I/O (`LIBNAME` with engine) | Platform-specific storage | `# SAS-UNTRANSLATABLE: LIBNAME engine — map to storage path manually` |

---

## Provenance Comment Format

Every generated line must end with a provenance comment:

```python
output["col"] = input["col"] * 2  # SAS: path/to/file.sas:42
```

For blocks derived from multiple SAS lines, use the starting line:

```python
# SAS: path/to/file.sas:10-18
output = input.groupby("a").agg(...)
```
