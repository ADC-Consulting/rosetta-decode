"""Extended coverage tests for src/worker/main.py — targeting uncovered branches."""

from src.worker.engine.models import BlockType, DataFileInfo, JobContext, SASBlock
from src.worker.main import (
    _dataset_matches_file,
    _inject_data_file_nodes,
)


def _make_job_context(**overrides: object) -> JobContext:
    """Helper to create a JobContext with default values."""
    defaults = {
        "source_files": {},
        "resolved_macros": [],
        "dependency_order": [],
        "risk_flags": [],
        "blocks": [],
        "generated": [],
        "data_files": {},
        "libname_map": {},
    }
    defaults.update(overrides)
    return JobContext(**defaults)


def _make_sas_block(**overrides: object) -> SASBlock:
    """Helper to create a SASBlock with default values."""
    defaults = {
        "block_type": BlockType.DATA_STEP,
        "source_file": "test.sas",
        "start_line": 1,
        "end_line": 5,
        "raw_sas": "data out; set in; run;",
        "input_datasets": [],
        "output_datasets": [],
    }
    defaults.update(overrides)
    return SASBlock(**defaults)


# ── Tests for _dataset_matches_file ────────────────────────────────────────


class TestDatasetMatchesFile:
    """Test the _dataset_matches_file matching logic."""

    def test_direct_stem_match(self) -> None:
        """Test direct filename stem matching."""
        context = _make_job_context()
        result = _dataset_matches_file(["customers"], "data/raw/customers.csv", context)
        assert result is True

    def test_direct_stem_match_case_insensitive(self) -> None:
        """Test that stem matching is case-insensitive."""
        context = _make_job_context()
        result = _dataset_matches_file(["CUSTOMERS"], "data/raw/customers.csv", context)
        assert result is True

    def test_direct_stem_matches_regardless_of_path(self) -> None:
        """Test that direct stem match works regardless of folder."""
        context = _make_job_context()
        result = _dataset_matches_file(["customers"], "data/different/customers.csv", context)
        assert result is True

    def test_libname_resolution_with_matching_folder(self) -> None:
        """Test libname resolution: 'rawdir.customers' with matching folder."""
        context = _make_job_context(libname_map={"rawdir": "data/raw"})
        result = _dataset_matches_file(["rawdir.customers"], "data/raw/customers.csv", context)
        assert result is True

    def test_libname_alias_match(self) -> None:
        """Test filename alias match from libname_map."""
        context = _make_job_context(libname_map={"myfile": "data/raw/customers.csv"})
        result = _dataset_matches_file(["myfile"], "data/raw/customers.csv", context)
        assert result is True

    def test_no_match_empty_datasets(self) -> None:
        """Test that empty datasets list returns False."""
        context = _make_job_context()
        result = _dataset_matches_file([], "data/raw/customers.csv", context)
        assert result is False

    def test_no_match_unrelated_dataset(self) -> None:
        """Test that unrelated dataset names return False."""
        context = _make_job_context()
        result = _dataset_matches_file(["orders"], "data/raw/customers.csv", context)
        assert result is False

    def test_libname_without_table_part(self) -> None:
        """Test libname.table format where table doesn't match."""
        context = _make_job_context(libname_map={"rawdir": "data/raw"})
        result = _dataset_matches_file(["rawdir.orders"], "data/raw/customers.csv", context)
        assert result is False

    def test_libname_not_in_map_still_matches_by_stem(self) -> None:
        """Test libname.table format when libname not in map still matches by stem."""
        context = _make_job_context()
        # This actually matches because "customers" stem matches
        result = _dataset_matches_file(["unknownlib.customers"], "data/raw/customers.csv", context)
        assert result is True

    def test_no_alias_match_wrong_file(self) -> None:
        """Test that alias does not match wrong file."""
        context = _make_job_context(libname_map={"myfile": "data/raw/customers.csv"})
        result = _dataset_matches_file(["myfile"], "data/raw/orders.csv", context)
        assert result is False


# ── Tests for _inject_data_file_nodes ────────────────────────────────────────


class TestInjectDataFileNodes:
    """Test the _inject_data_file_nodes function."""

    def test_empty_data_files(self) -> None:
        """Test that empty data_files dict returns unchanged lineage."""
        lineage_data = {"nodes": [{"id": "block1"}], "edges": []}
        context = _make_job_context()
        result = _inject_data_file_nodes(lineage_data, [], context)
        assert result["nodes"] == [{"id": "block1"}]
        assert result["edges"] == []

    def test_data_files_with_no_blocks(self) -> None:
        """Test that data files are added even when there are no blocks."""
        lineage_data = {"nodes": [], "edges": []}
        data_files = {
            "data/raw/customers.csv": DataFileInfo(
                path="data/raw/customers.csv",
                disk_path="/tmp/customers.csv",
                extension=".csv",
                columns=["id", "name"],
                row_count=100,
            )
        }
        context = _make_job_context(data_files=data_files)
        result = _inject_data_file_nodes(lineage_data, [], context)
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["node_type"] == "DATA_FILE"
        assert result["nodes"][0]["path"] == "data/raw/customers.csv"
        assert result["nodes"][0]["columns"] == ["id", "name"]
        assert result["nodes"][0]["row_count"] == 100

    def test_data_files_with_matching_blocks(self) -> None:
        """Test that edges are created when blocks reference data files."""
        lineage_data = {"nodes": [], "edges": []}
        data_files = {
            "data/raw/customers.csv": DataFileInfo(
                path="data/raw/customers.csv",
                disk_path="/tmp/customers.csv",
                extension=".csv",
                columns=["id", "name"],
                row_count=100,
            )
        }
        block = _make_sas_block(
            source_file="test.sas",
            start_line=1,
            input_datasets=["customers"],
            output_datasets=[],
        )
        context = _make_job_context(blocks=[block], data_files=data_files)
        result = _inject_data_file_nodes(lineage_data, [block], context)

        # Should have file node and one input edge
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["node_type"] == "DATA_FILE"

        # Should have one edge from file to block
        assert len(result["edges"]) == 1
        assert result["edges"][0]["source"] == "__data_file__data/raw/customers.csv"
        assert result["edges"][0]["target"] == "test.sas::1"

    def test_data_files_with_output_edges(self) -> None:
        """Test that output edges are created correctly."""
        lineage_data = {"nodes": [], "edges": []}
        data_files = {
            "output.csv": DataFileInfo(
                path="output.csv",
                disk_path="/tmp/output.csv",
                extension=".csv",
                columns=["result"],
                row_count=50,
            )
        }
        block = _make_sas_block(
            source_file="transform.sas",
            start_line=10,
            input_datasets=[],
            output_datasets=["output"],
        )
        context = _make_job_context(blocks=[block], data_files=data_files)
        result = _inject_data_file_nodes(lineage_data, [block], context)

        # Should have one edge from block to file
        assert len(result["edges"]) == 1
        assert result["edges"][0]["source"] == "transform.sas::10"
        assert result["edges"][0]["target"] == "__data_file__output.csv"

    def test_multiple_data_files_and_blocks(self) -> None:
        """Test with multiple data files and blocks."""
        lineage_data = {"nodes": [], "edges": []}
        data_files = {
            "data/raw/in.csv": DataFileInfo(
                path="data/raw/in.csv",
                disk_path="/tmp/in.csv",
                extension=".csv",
                columns=["id"],
                row_count=100,
            ),
            "data/out.csv": DataFileInfo(
                path="data/out.csv",
                disk_path="/tmp/out.csv",
                extension=".csv",
                columns=["id", "result"],
                row_count=50,
            ),
        }
        block1 = _make_sas_block(
            source_file="test.sas",
            start_line=1,
            input_datasets=["in"],
            output_datasets=["temp"],
        )
        block2 = _make_sas_block(
            source_file="test.sas",
            start_line=6,
            input_datasets=["temp"],
            output_datasets=["out"],
        )
        context = _make_job_context(blocks=[block1, block2], data_files=data_files)
        result = _inject_data_file_nodes(lineage_data, [block1, block2], context)

        # Should have 2 file nodes
        assert len(result["nodes"]) == 2
        # Should have 2 edges (in→block1, block2→out)
        assert len(result["edges"]) == 2

    def test_preserves_existing_nodes_and_edges(self) -> None:
        """Test that existing nodes and edges are preserved."""
        existing_node = {"id": "existing_block", "node_type": "PROC"}
        existing_edge = {"source": "other_file", "target": "existing_block"}
        lineage_data = {"nodes": [existing_node], "edges": [existing_edge]}

        data_files = {
            "new.csv": DataFileInfo(
                path="new.csv",
                disk_path="/tmp/new.csv",
                extension=".csv",
                columns=[],
                row_count=10,
            )
        }
        context = _make_job_context(data_files=data_files)
        result = _inject_data_file_nodes(lineage_data, [], context)

        # Should have both existing and new nodes
        assert len(result["nodes"]) == 2
        assert result["nodes"][0] == existing_node
        assert result["nodes"][1]["node_type"] == "DATA_FILE"

        # Should have both existing and new edges
        assert len(result["edges"]) == 1
        assert result["edges"][0] == existing_edge
