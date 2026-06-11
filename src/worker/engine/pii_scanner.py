"""Detect PII/sensitive data signals in SAS column names and variable references."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import DataFileInfo, SASBlock, SensitiveDataFinding

_PII_SIGNALS: frozenset[str] = frozenset(
    {
        "ssn",
        "social",
        "security",
        "nin",
        "national",
        "id",
        "cpr",
        "personnummer",
        "cvr",
        "bsn",
        "nino",
        "pps",
        "passport",
        "dob",
        "birth",
        "age",
        "email",
        "phone",
        "mobile",
        "address",
        "street",
        "postcode",
        "zip",
        "ip",
        "credit",
        "card",
        "iban",
        "account",
        "bank",
        "tax",
    }
)

_SPLIT_RE = re.compile(r"[_\s]+|(?<=[a-z])(?=[A-Z])")

# Hint fields on SASBlock that may contain column names
_HINT_FIELDS: tuple[str, ...] = (
    "var_cols",
    "class_vars",
    "by_vars",
    "table_vars",
    "id_cols",
    "rank_cols",
    "keep_cols",
    "drop_cols",
)


def _tokenise(name: str) -> list[str]:
    """Split a column name on underscores, spaces, and CamelCase boundaries.

    Args:
        name: Raw column name to tokenise.

    Returns:
        List of lowercase tokens derived from the name.
    """
    return [t.lower() for t in _SPLIT_RE.split(name) if t]


def _matches_pii(name: str) -> str | None:
    """Return the first matching PII signal token found in name, or None.

    Args:
        name: Column name to check against the PII signal set.

    Returns:
        The matched signal string if any token matches, otherwise None.
    """
    for token in _tokenise(name):
        if token in _PII_SIGNALS:
            return token
    return None


def scan_for_pii(
    blocks: list[SASBlock],
    data_files: dict[str, DataFileInfo],
) -> list[SensitiveDataFinding]:
    """Detect column names matching PII signals from data files and SAS block hints.

    Args:
        blocks: Parsed SAS blocks — hint fields checked for column name leakage.
        data_files: Uploaded data files with column metadata.

    Returns:
        Deduplicated list of SensitiveDataFinding entries.
    """
    from .models import SensitiveDataFinding

    seen: set[tuple[str, str, str]] = set()
    results: list[SensitiveDataFinding] = []

    def _add(column: str, source_type: str, source: str) -> None:
        signal = _matches_pii(column)
        if signal is None:
            return
        key = (column.lower(), signal, source)
        if key in seen:
            return
        seen.add(key)
        results.append(
            SensitiveDataFinding(
                column=column,
                matched_signal=signal,
                source_type=source_type,
                source=source,
            )
        )

    # Scan data file columns
    for path, info in data_files.items():
        for col in info.columns:
            _add(col, "file", path)

    # Scan SAS block hint fields
    for block in blocks:
        block_id = f"{block.source_file}:{block.start_line}"
        for field in _HINT_FIELDS:
            for col in getattr(block, field, []) or []:
                _add(col, "block", block_id)

    return results
