"""Unit tests for build_block_output_stems and normalise_input_vars_in_code."""

from src.worker.engine.agents.shared import (
    SHARED_TRANSLATION_RULES,
    build_block_output_stems,
    normalise_input_vars_in_code,
)
from src.worker.engine.models import BlockType, SASBlock

# ── Helpers ───────────────────────────────────────────────────────────────────


def _block(output_datasets: list[str]) -> SASBlock:
    return SASBlock(
        block_type=BlockType.DATA_STEP,
        source_file="test.sas",
        start_line=1,
        end_line=5,
        raw_sas="",
        input_datasets=[],
        output_datasets=output_datasets,
    )


# ── build_block_output_stems ──────────────────────────────────────────────────


def test_stem_map_dot_form() -> None:
    stems = build_block_output_stems([_block(["work.ex_dedup"])])
    assert stems["work.ex_dedup"] == "ex_dedup"


def test_stem_map_underscore_form() -> None:
    stems = build_block_output_stems([_block(["work.ex_dedup"])])
    assert stems["work_ex_dedup"] == "ex_dedup"


def test_stem_map_no_libname() -> None:
    stems = build_block_output_stems([_block(["ex_dedup"])])
    assert stems["ex_dedup"] == "ex_dedup"


def test_stem_map_multiple_blocks() -> None:
    blocks = [_block(["work.ex_dedup"]), _block(["sdtm.ae", "work.ae_raw"])]
    stems = build_block_output_stems(blocks)
    assert stems["work.ex_dedup"] == "ex_dedup"
    assert stems["sdtm.ae"] == "ae"
    assert stems["work.ae_raw"] == "ae_raw"


def test_stem_map_empty() -> None:
    assert build_block_output_stems([]) == {}


# ── normalise_input_vars_in_code ──────────────────────────────────────────────


def test_prior_block_output_underscore_form_replaced() -> None:
    stems = {"work.ex_dedup": "ex_dedup", "work_ex_dedup": "ex_dedup"}
    code = "sdtm_ex = work_ex_dedup.copy()"
    result = normalise_input_vars_in_code(code, ["work.ex_dedup"], stems, "TestAgent")
    assert result == "sdtm_ex = ex_dedup.copy()"
    assert "work_ex_dedup" not in result


def test_prior_block_output_dot_form_replaced() -> None:
    stems = {"work.ex_dedup": "ex_dedup", "work_ex_dedup": "ex_dedup"}
    code = "sdtm_ex = work.ex_dedup.copy()"
    result = normalise_input_vars_in_code(code, ["work.ex_dedup"], stems, "TestAgent")
    assert "work.ex_dedup" not in result


def test_external_dataset_left_unchanged() -> None:
    # rawdir.customers is NOT in block_output_stems → correct form is rawdir_customers
    stems: dict[str, str] = {}
    code = "df = rawdir_customers.filter(F.col('id') > 0)"
    result = normalise_input_vars_in_code(code, ["rawdir.customers"], stems, "TestAgent")
    assert result == code  # no change: already the correct underscore form


def test_word_boundary_respected() -> None:
    # 'work_ex_dedup_extra' must NOT be touched
    stems = {"work.ex_dedup": "ex_dedup", "work_ex_dedup": "ex_dedup"}
    code = "a = work_ex_dedup_extra.copy()\nb = work_ex_dedup.copy()"
    result = normalise_input_vars_in_code(code, ["work.ex_dedup"], stems, "TestAgent")
    assert "work_ex_dedup_extra" in result  # untouched (not a word boundary match)
    assert "b = ex_dedup.copy()" in result


def test_no_false_positive_when_already_correct() -> None:
    stems = {"work.ex_dedup": "ex_dedup", "work_ex_dedup": "ex_dedup"}
    code = "sdtm_ex = ex_dedup.copy()"
    result = normalise_input_vars_in_code(code, ["work.ex_dedup"], stems, "TestAgent")
    assert result == code  # already correct — no change


def test_multiple_input_datasets() -> None:
    stems = {
        "work.ex_dedup": "ex_dedup",
        "work_ex_dedup": "ex_dedup",
        "work.dm_raw": "dm_raw",
        "work_dm_raw": "dm_raw",
    }
    code = "a = work_ex_dedup.copy()\nb = work_dm_raw.copy()"
    result = normalise_input_vars_in_code(
        code, ["work.ex_dedup", "work.dm_raw"], stems, "TestAgent"
    )
    assert "a = ex_dedup.copy()" in result
    assert "b = dm_raw.copy()" in result


def test_empty_input_datasets_no_change() -> None:
    stems = {"work.ex_dedup": "ex_dedup", "work_ex_dedup": "ex_dedup"}
    code = "sdtm_ex = work_ex_dedup.copy()"
    result = normalise_input_vars_in_code(code, [], stems, "TestAgent")
    assert result == code


# ── SHARED_TRANSLATION_RULES content ──────────────────────────────────────────


def test_column_lifecycle_rule_present() -> None:
    assert "## 4. Column Lifecycle & Ordering" in SHARED_TRANSLATION_RULES


def test_column_lifecycle_rule_orders_derivation_before_narrowing() -> None:
    rules = SHARED_TRANSLATION_RULES
    assert "BEFORE any" in rules and ".select(...)" in rules
    assert "Do NOT recompute a column that already exists" in rules


def test_section_numbering_contiguous() -> None:
    import re

    numbers = [int(m) for m in re.findall(r"^## (\d+)\.", SHARED_TRANSLATION_RULES, re.M)]
    assert numbers == list(range(1, numbers[-1] + 1))
