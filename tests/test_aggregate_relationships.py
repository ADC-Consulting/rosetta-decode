"""Unit tests for _aggregate_relationships and _strip_libname in src/worker/main.py.

Covers:
- merge aggregation (DATA step MERGE BY)
- join aggregation (PROC SQL JOIN ON)
- deduplication across blocks
- libname prefix stripping
- empty-input edge cases
"""

from src.worker.engine.models import BlockRisk, BlockType, MigrationPlan, SASBlock
from src.worker.main import _aggregate_relationships, _strip_libname

# ── helpers ────────────────────────────────────────────────────────────────────


def _make_migration_plan() -> MigrationPlan:
    """Return a minimal MigrationPlan with no relationships."""
    return MigrationPlan(
        summary="test",
        block_plans=[],
        overall_risk=BlockRisk.LOW,
        recommended_review_blocks=[],
        cross_file_dependencies=[],
    )


def _make_block(**overrides: object) -> SASBlock:
    """Return a SASBlock with sensible defaults."""
    defaults: dict[str, object] = {
        "block_type": BlockType.DATA_STEP,
        "source_file": "test.sas",
        "start_line": 1,
        "end_line": 10,
        "raw_sas": "data out; merge a b; by id; run;",
        "input_datasets": [],
        "output_datasets": [],
        "merge_by_vars": [],
        "join_on_keys": [],
    }
    defaults.update(overrides)
    return SASBlock(**defaults)


# ── _strip_libname ──────────────────────────────────────────────────────────────


class TestStripLibname:
    """Tests for the _strip_libname helper."""

    def test_strips_prefix(self) -> None:
        assert _strip_libname("outdir.sdtm_dm") == "sdtm_dm"

    def test_no_prefix_unchanged(self) -> None:
        assert _strip_libname("dm") == "dm"

    def test_lowercase_applied(self) -> None:
        assert _strip_libname("OUTDIR.DM") == "dm"

    def test_multiple_dots_takes_last_segment(self) -> None:
        # Only the last dot-separated segment is kept
        assert _strip_libname("a.b.c") == "c"

    def test_empty_string(self) -> None:
        assert _strip_libname("") == ""


# ── _aggregate_relationships: merge ────────────────────────────────────────────


class TestAggregateRelationshipsMerge:
    """Tests for DATA step MERGE relationship aggregation."""

    def test_merge_produces_relationship(self) -> None:
        """A DATA step block with merge_by_vars produces one relationship per BY var."""
        block = _make_block(
            input_datasets=["dm"],
            output_datasets=["sdtm_dm"],
            merge_by_vars=["usubjid"],
        )
        plan = _make_migration_plan()
        _aggregate_relationships([block], plan)

        assert len(plan.relationships) == 1
        rel = plan.relationships[0]
        assert rel["left_table"] == "sdtm_dm"
        assert rel["right_table"] == "dm"
        assert rel["key_column"] == "usubjid"
        assert rel["relationship_type"] == "merge"
        assert rel["via_block_id"] == "test.sas:1"

    def test_merge_multiple_by_vars(self) -> None:
        """Each BY variable generates a separate relationship entry."""
        block = _make_block(
            input_datasets=["ex"],
            output_datasets=["out"],
            merge_by_vars=["usubjid", "studyid"],
        )
        plan = _make_migration_plan()
        _aggregate_relationships([block], plan)

        assert len(plan.relationships) == 2
        key_columns = {r["key_column"] for r in plan.relationships}
        assert key_columns == {"usubjid", "studyid"}

    def test_merge_strips_libname_prefix(self) -> None:
        """Libname prefixes are stripped from table names in merge relationships."""
        block = _make_block(
            input_datasets=["rawdir.dm"],
            output_datasets=["outdir.sdtm_dm"],
            merge_by_vars=["usubjid"],
        )
        plan = _make_migration_plan()
        _aggregate_relationships([block], plan)

        assert len(plan.relationships) == 1
        rel = plan.relationships[0]
        assert rel["left_table"] == "sdtm_dm"
        assert rel["right_table"] == "dm"

    def test_no_merge_by_vars_produces_no_relationships(self) -> None:
        """A DATA step block with no merge_by_vars contributes nothing."""
        block = _make_block(
            input_datasets=["dm"],
            output_datasets=["out"],
            merge_by_vars=[],
        )
        plan = _make_migration_plan()
        _aggregate_relationships([block], plan)

        assert plan.relationships == []

    def test_same_left_right_skipped(self) -> None:
        """A block where the same table appears in both input and output is skipped."""
        block = _make_block(
            input_datasets=["dm"],
            output_datasets=["dm"],
            merge_by_vars=["id"],
        )
        plan = _make_migration_plan()
        _aggregate_relationships([block], plan)

        assert plan.relationships == []


# ── _aggregate_relationships: join ─────────────────────────────────────────────


class TestAggregateRelationshipsJoin:
    """Tests for PROC SQL JOIN relationship aggregation."""

    def test_join_produces_relationship(self) -> None:
        """A block with join_on_keys produces one relationship per join predicate."""
        block = _make_block(
            block_type=BlockType.PROC_SQL,
            join_on_keys=[
                {
                    "left_table": "dm",
                    "right_table": "ex",
                    "left_col": "usubjid",
                    "right_col": "usubjid",
                }
            ],
        )
        plan = _make_migration_plan()
        _aggregate_relationships([block], plan)

        assert len(plan.relationships) == 1
        rel = plan.relationships[0]
        assert rel["left_table"] == "dm"
        assert rel["right_table"] == "ex"
        assert rel["key_column"] == "usubjid"
        assert rel["relationship_type"] == "join"
        assert rel["via_block_id"] == "test.sas:1"

    def test_join_strips_libname_prefix(self) -> None:
        """Libname prefixes are stripped from join table names."""
        block = _make_block(
            block_type=BlockType.PROC_SQL,
            join_on_keys=[
                {
                    "left_table": "rawdir.dm",
                    "right_table": "rawdir.ex",
                    "left_col": "id",
                    "right_col": "id",
                }
            ],
        )
        plan = _make_migration_plan()
        _aggregate_relationships([block], plan)

        assert len(plan.relationships) == 1
        rel = plan.relationships[0]
        assert rel["left_table"] == "dm"
        assert rel["right_table"] == "ex"

    def test_join_entry_missing_left_col_skipped(self) -> None:
        """A join_on_keys entry with no left_col is silently skipped."""
        block = _make_block(
            block_type=BlockType.PROC_SQL,
            join_on_keys=[{"left_table": "dm", "right_table": "ex", "left_col": ""}],
        )
        plan = _make_migration_plan()
        _aggregate_relationships([block], plan)

        assert plan.relationships == []

    def test_no_join_keys_produces_no_relationships(self) -> None:
        """A PROC SQL block with no join_on_keys contributes nothing."""
        block = _make_block(block_type=BlockType.PROC_SQL, join_on_keys=[])
        plan = _make_migration_plan()
        _aggregate_relationships([block], plan)

        assert plan.relationships == []


# ── _aggregate_relationships: deduplication ────────────────────────────────────


class TestAggregateRelationshipsDedup:
    """Tests for deduplication across multiple blocks."""

    def test_duplicate_merge_from_two_blocks_kept_once(self) -> None:
        """Two blocks that produce the same (left, right, key, type) tuple are deduplicated."""
        block1 = _make_block(
            source_file="step1.sas",
            start_line=1,
            input_datasets=["dm"],
            output_datasets=["out"],
            merge_by_vars=["usubjid"],
        )
        block2 = _make_block(
            source_file="step2.sas",
            start_line=10,
            input_datasets=["dm"],
            output_datasets=["out"],
            merge_by_vars=["usubjid"],
        )
        plan = _make_migration_plan()
        _aggregate_relationships([block1, block2], plan)

        assert len(plan.relationships) == 1
        # First block wins
        assert plan.relationships[0]["via_block_id"] == "step1.sas:1"

    def test_duplicate_join_from_two_blocks_kept_once(self) -> None:
        """Two PROC SQL blocks with the same join predicate are deduplicated."""
        join_entry = {
            "left_table": "dm",
            "right_table": "ex",
            "left_col": "usubjid",
            "right_col": "usubjid",
        }
        block1 = _make_block(
            block_type=BlockType.PROC_SQL,
            source_file="sql1.sas",
            start_line=5,
            join_on_keys=[join_entry],
        )
        block2 = _make_block(
            block_type=BlockType.PROC_SQL,
            source_file="sql2.sas",
            start_line=20,
            join_on_keys=[join_entry],
        )
        plan = _make_migration_plan()
        _aggregate_relationships([block1, block2], plan)

        assert len(plan.relationships) == 1
        assert plan.relationships[0]["via_block_id"] == "sql1.sas:5"

    def test_different_key_columns_not_deduplicated(self) -> None:
        """Two join entries with different key columns both appear in results."""
        block = _make_block(
            block_type=BlockType.PROC_SQL,
            join_on_keys=[
                {
                    "left_table": "dm",
                    "right_table": "ex",
                    "left_col": "usubjid",
                    "right_col": "usubjid",
                },
                {
                    "left_table": "dm",
                    "right_table": "ex",
                    "left_col": "studyid",
                    "right_col": "studyid",
                },
            ],
        )
        plan = _make_migration_plan()
        _aggregate_relationships([block], plan)

        assert len(plan.relationships) == 2

    def test_merge_and_join_same_key_not_deduplicated(self) -> None:
        """A merge and a join on the same tables/key produce two entries (different types)."""
        block = _make_block(
            input_datasets=["ex"],
            output_datasets=["dm"],
            merge_by_vars=["usubjid"],
            join_on_keys=[
                {
                    "left_table": "dm",
                    "right_table": "ex",
                    "left_col": "usubjid",
                    "right_col": "usubjid",
                },
            ],
        )
        plan = _make_migration_plan()
        _aggregate_relationships([block], plan)

        types = {r["relationship_type"] for r in plan.relationships}
        assert "merge" in types
        assert "join" in types

    def test_empty_blocks_list(self) -> None:
        """No blocks → empty relationships list."""
        plan = _make_migration_plan()
        _aggregate_relationships([], plan)

        assert plan.relationships == []
