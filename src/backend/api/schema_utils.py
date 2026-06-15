"""Utilities for mapping SAS data types and formats to semantic target types."""

# SAS: src/backend/api/schema_utils.py:1

import re

# Date/Datetime format patterns
_DATE_FORMATS = re.compile(
    r"^(DATE|DDMMYY|MMDDYY|YYMMDD|JULIAN|WEEKDATE|WORDDATE|DTDATE|YEAR|QTR|MONNAME|DAYNAME|"
    r"EURDFDD|EURDFDE|EURDFDN|EURDFDT|EURDFWK|NLDATE|ISO8601DA)",
    re.IGNORECASE,
)
_DATETIME_FORMATS = re.compile(
    r"^(DATETIME|DTTIME|TOD|HHMM|HOUR|MMSS|TIME|TIMEAMPM|E8601DT|NLTIMAP|NLTIME)",
    re.IGNORECASE,
)
_DECIMAL_FORMATS = re.compile(
    r"^(COMMA|DOLLAR|EURO|POUND|FRANC|DM|YEN|F|E|BEST|NUMX)",
    re.IGNORECASE,
)


def map_sas_to_semantic_type(sas_type: str, sas_format: str | None) -> str:
    """Map a SAS storage type and display format to a semantic target type.

    Args:
        sas_type: "character" or "double" (from readstat_variable_types)
        sas_format: SAS format name e.g. "DATE9.", "$40.", "DATETIME20." (may be empty/None)

    Returns:
        One of: "String", "Date", "Timestamp", "Decimal", "Number", "Integer", "Unknown"
    """
    if not sas_type:
        return "Unknown"
    fmt = (sas_format or "").strip().lstrip("$").rstrip(".")
    if sas_type == "character":
        return "String"
    # numeric — check format for semantic hint
    # Datetime must be tested before date: DATETIME... starts with DATE...
    if _DATETIME_FORMATS.match(fmt):
        return "Timestamp"
    if _DATE_FORMATS.match(fmt):
        return "Date"
    if _DECIMAL_FORMATS.match(fmt) and "." in (sas_format or ""):
        return "Decimal"
    return "Number"
