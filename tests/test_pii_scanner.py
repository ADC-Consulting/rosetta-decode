"""Unit tests for the PII/sensitive-data scanner."""

from src.worker.engine.pii_scanner import _matches_pii, _tokenise, scan_for_pii


def test_tokenise_underscore() -> None:
    assert _tokenise("date_of_birth") == ["date", "of", "birth"]


def test_tokenise_camelcase() -> None:
    assert _tokenise("DateOfBirth") == ["date", "of", "birth"]


def test_tokenise_mixed() -> None:
    assert _tokenise("customerEmail") == ["customer", "email"]


def test_matches_pii_email() -> None:
    assert _matches_pii("customer_email") == "email"


def test_matches_pii_dob() -> None:
    assert _matches_pii("DateOfBirth") == "birth"


def test_no_false_positive_topzip() -> None:
    # "TOPZIP" tokens to ["topzip"] — no exact match in _PII_SIGNALS
    assert _matches_pii("TOPZIP") is None


def test_no_false_positive_doberman() -> None:
    # "doberman" tokens to ["doberman"] — not in _PII_SIGNALS
    assert _matches_pii("doberman") is None


def test_address_flag_is_valid_match() -> None:
    # "address_flag" contains "address" as a token — this IS a valid match
    assert _matches_pii("address_flag") == "address"


def test_phone_confirmed_is_valid_match() -> None:
    # "phone_confirmed" contains "phone" — legitimate PII signal
    assert _matches_pii("phone_confirmed") == "phone"


def test_scan_data_file_columns() -> None:
    from src.worker.engine.models import DataFileInfo

    info = DataFileInfo(
        path="data.csv",
        disk_path="/tmp/data.csv",
        extension=".csv",
        columns=["customer_email", "revenue"],
        row_count=100,
    )
    results = scan_for_pii([], {"data.csv": info})
    assert any(r.column == "customer_email" and r.source_type == "file" for r in results)
    assert not any(r.column == "revenue" for r in results)


def test_scan_deduplication() -> None:
    from src.worker.engine.models import DataFileInfo

    # Duplicate column name in the columns list should only produce one finding
    info = DataFileInfo(
        path="a.csv",
        disk_path="/tmp/a.csv",
        extension=".csv",
        columns=["ssn", "ssn"],
        row_count=1,
    )
    results = scan_for_pii([], {"a.csv": info})
    assert sum(1 for r in results if r.column == "ssn") == 1


def test_scan_empty_inputs() -> None:
    assert scan_for_pii([], {}) == []


def test_scan_block_hint_fields() -> None:
    from src.worker.engine.models import BlockType, SASBlock

    block = SASBlock(
        block_type=BlockType.PROC_MEANS,
        source_file="analysis.sas",
        start_line=10,
        end_line=20,
        raw_sas="proc means; var ssn_col; run;",
        class_vars=["ssn_col"],
    )
    results = scan_for_pii([block], {})
    assert any(r.column == "ssn_col" and r.source_type == "block" for r in results)
    match = next(r for r in results if r.column == "ssn_col")
    assert match.source == "analysis.sas:10"


def test_scan_block_source_type_is_file_for_data_files() -> None:
    from src.worker.engine.models import DataFileInfo

    info = DataFileInfo(
        path="customers.csv",
        disk_path="/uploads/customers.csv",
        extension=".csv",
        columns=["phone_number"],
        row_count=50,
    )
    results = scan_for_pii([], {"customers.csv": info})
    assert len(results) == 1
    assert results[0].source_type == "file"
    assert results[0].source == "customers.csv"
    assert results[0].matched_signal == "phone"
