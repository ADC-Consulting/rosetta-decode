"""Unit tests for the F76 portable-codegen post-processors.

Covers ``parameterize_data_root`` (rewrite local data-root reads to a portable
``DATA_ROOT`` constant) and ``ensure_result_assignment`` (guarantee the executor's
``result`` contract). Both must be deterministic and idempotent, and every rewritten
block must remain valid Python (verified via ``ast.parse``).
"""

import ast

from src.worker.engine.agents.shared import (
    ensure_result_assignment,
    parameterize_data_root,
)

# ── parameterize_data_root ────────────────────────────────────────────────────


def test_parameterize_rewrites_double_quoted_path() -> None:
    """A double-quoted /workspace/data/ literal becomes an f-string on DATA_ROOT."""
    code = 'df = spark.read.csv("/workspace/data/dm.csv", header=True)'
    out = parameterize_data_root(code)
    assert 'f"{DATA_ROOT}/dm.csv"' in out
    assert "/workspace/data/dm.csv" not in out
    assert ast.parse(out) is not None


def test_parameterize_rewrites_single_quoted_path() -> None:
    """A single-quoted /workspace/data/ literal is rewritten just like double quotes."""
    code = "df = spark.read.csv('/workspace/data/raw/ex.csv')"
    out = parameterize_data_root(code)
    assert 'f"{DATA_ROOT}/raw/ex.csv"' in out
    assert "/workspace/data/" not in out
    assert ast.parse(out) is not None


def test_parameterize_injects_constant_and_import_once() -> None:
    """The DATA_ROOT constant and `import os` are injected exactly once."""
    code = (
        'a = spark.read.csv("/workspace/data/a.csv")\nb = spark.read.csv("/workspace/data/b.csv")'
    )
    out = parameterize_data_root(code)
    const = 'DATA_ROOT = os.environ.get("ROSETTA_DATA_ROOT", "/workspace/data")'
    assert out.count(const) == 1
    assert out.count("import os") == 1
    # Both paths rewritten.
    assert 'f"{DATA_ROOT}/a.csv"' in out
    assert 'f"{DATA_ROOT}/b.csv"' in out
    assert ast.parse(out) is not None


def test_parameterize_is_idempotent() -> None:
    """Running twice produces no further change."""
    code = 'df = spark.read.csv("/workspace/data/dm.csv")'
    once = parameterize_data_root(code)
    twice = parameterize_data_root(once)
    assert once == twice
    assert ast.parse(twice) is not None


def test_parameterize_does_not_double_wrap_fstring() -> None:
    """An already-f-string DATA_ROOT path is left intact (no double wrapping)."""
    code = (
        "import os\n"
        'DATA_ROOT = os.environ.get("ROSETTA_DATA_ROOT", "/workspace/data")\n'
        'df = spark.read.csv(f"{DATA_ROOT}/dm.csv")\n'
    )
    out = parameterize_data_root(code)
    assert out == code
    assert ast.parse(out) is not None


def test_parameterize_noop_when_prefix_absent() -> None:
    """Code without /workspace/data/ is returned unchanged (no constant injected)."""
    code = "df = prior_block.withColumn('x', F.lit(1))\nresult = df"
    out = parameterize_data_root(code)
    assert out == code
    assert "DATA_ROOT" not in out
    assert "import os" not in out


def test_parameterize_preserves_existing_os_import() -> None:
    """An existing `import os` is not duplicated when the constant is injected."""
    code = 'import os\ndf = spark.read.csv("/workspace/data/dm.csv")'
    out = parameterize_data_root(code)
    assert out.count("import os") == 1
    assert ast.parse(out) is not None


def test_parameterize_constant_lands_below_imports() -> None:
    """The constant is inserted after the import block, above the first statement."""
    code = (
        "import os\n"
        "from pyspark.sql import functions as F\n"
        'df = spark.read.csv("/workspace/data/dm.csv")\n'
    )
    out = parameterize_data_root(code)
    lines = out.split("\n")
    const_idx = next(i for i, line in enumerate(lines) if line.startswith("DATA_ROOT ="))
    df_idx = next(i for i, line in enumerate(lines) if line.startswith("df ="))
    assert const_idx < df_idx
    assert ast.parse(out) is not None


# ── ensure_result_assignment ──────────────────────────────────────────────────


def test_ensure_result_adds_when_missing() -> None:
    """When the code does not bind result, append `result = <output_var>`."""
    code = "work_out = work_in.withColumn('x', F.lit(1))"
    out = ensure_result_assignment(code, "work_out")
    assert out.rstrip().endswith("result = work_out")
    assert ast.parse(out) is not None


def test_ensure_result_inert_when_present() -> None:
    """When result is already bound, the code is returned unchanged."""
    code = "work_out = work_in.copy()\nresult = work_out"
    out = ensure_result_assignment(code, "work_out")
    assert out == code


def test_ensure_result_inert_when_present_with_leading_whitespace() -> None:
    """A `result =` binding with leading whitespace still counts as present."""
    code = "if True:\n    result = work_out"
    out = ensure_result_assignment(code, "work_out")
    assert out == code


def test_ensure_result_noop_when_output_var_none() -> None:
    """No output_var → no guess, code unchanged."""
    code = "work_out = work_in.copy()"
    assert ensure_result_assignment(code, None) == code


def test_ensure_result_noop_when_output_var_not_identifier() -> None:
    """A non-identifier output_var (e.g. dotted form) is not appended."""
    code = "work_out = work_in.copy()"
    assert ensure_result_assignment(code, "work.out") == code


def test_ensure_result_is_idempotent() -> None:
    """Running twice does not append a second binding."""
    code = "work_out = work_in.copy()"
    once = ensure_result_assignment(code, "work_out")
    twice = ensure_result_assignment(once, "work_out")
    assert once == twice
    assert twice.count("result = work_out") == 1
