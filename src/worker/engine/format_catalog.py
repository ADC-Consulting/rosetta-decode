"""Deterministic extractor for SAS ``PROC FORMAT`` user-defined formats.

This module parses ``PROC FORMAT ... RUN;`` blocks into a catalog of
:class:`~src.worker.engine.models.FormatDef` objects, keyed by a normalized
format name. It is a pure, deterministic module: no I/O, no LLM calls.

The parser is intentionally conservative — any mapping line it cannot confidently
interpret (e.g. picture formats, unparseable ranges) is skipped, leaving a
partial catalog rather than raising.
"""

import re

from src.worker.engine.models import FormatDef, FormatEntry

# PROC FORMAT block: PROC FORMAT … RUN; (mirrors parser._PROC_FORMAT_RE)
_PROC_FORMAT_RE = re.compile(
    r"PROC\s+FORMAT\b.*?RUN\s*;",
    re.IGNORECASE | re.DOTALL,
)

# A single ``value`` statement up to its terminating semicolon. The name may be
# ``$``-prefixed for character formats. The body is everything up to the ``;``.
_VALUE_STMT_RE = re.compile(
    r"\bvalue\s+(\$?\w+)\b(.*?);",
    re.IGNORECASE | re.DOTALL,
)

# One mapping line: <left-hand operand(s)> = <quoted label>.
# Operands run up to the ``=`` but may NOT cross a newline: each ``operand =
# label`` mapping lives on its own physical line in a ``value`` statement, even
# when the statement itself spans several lines. Bounding the operand at the
# newline ensures a malformed line drops only itself, never swallowing the next
# valid mapping. The label is a single- or double-quoted string on the same line.
_MAPPING_RE = re.compile(
    r"""(?P<operands>[^=\n]+?)\s*=\s*(?P<quote>['"])(?P<label>[^\n]*?)(?P=quote)""",
)

# A range: <low> <sep> <high>, where sep is ``-`` (inclusive) or ``-<``
# (exclusive upper), with arbitrary surrounding whitespace.
_RANGE_RE = re.compile(
    r"^(?P<low>\S+)\s+(?P<sep>-<|-)\s+(?P<high>\S+)$",
)

# Trailing format width: a run of digits (optionally ``.d``) at the very end,
# preceded by at least one non-digit name character, with an optional terminal
# ``.``. The leading ``$`` (if any) is handled separately.
_WIDTH_SUFFIX_RE = re.compile(r"(?<=\D)\d+(?:\.\d+)?\.?$|(?<=\D)\.$")


def normalize_format_name(name: str) -> str:
    """Normalize a SAS format name to its canonical catalog key.

    The same key is produced for a ``PROC FORMAT`` definition name and for a
    ``put()``-style reference that carries a width and/or trailing dot. For
    example ``agegr1f``, ``agegr1f8.`` and ``agegr1f8.2`` all normalize to
    ``agegr1f``, and ``$SEXDEC`` / ``$sexdec.`` both normalize to ``$sexdec``.

    Normalization steps:

    1. Trim surrounding whitespace and lowercase the name.
    2. Preserve a single leading ``$`` (character-format marker).
    3. Strip a trailing numeric width and the optional terminal ``.``.

    Width-stripping heuristic (deliberately conservative): a width is a run of
    digits — optionally in ``w.d`` form such as ``8.2`` — at the very end of the
    name, immediately preceded by at least one non-digit name character, with an
    optional terminating ``.``. A lone trailing ``.`` (no width digits) is also
    stripped. Because the digit run must follow a non-digit, digits that are part
    of the format name itself (e.g. the ``1`` in ``agegr1f``) are never removed.

    Args:
        name: Raw format name or reference (e.g. ``"agegr1f8."``, ``"$SEXDEC."``).

    Returns:
        The normalized catalog key (lowercased, ``$`` preserved, width removed).
    """
    cleaned = name.strip().lower()
    has_dollar = cleaned.startswith("$")
    body = cleaned[1:] if has_dollar else cleaned
    body = _WIDTH_SUFFIX_RE.sub("", body)
    return f"${body}" if has_dollar else body


def _parse_mapping(operands: str, label: str) -> FormatEntry | None:
    """Build a :class:`FormatEntry` from one mapping line, or ``None`` if unparseable.

    Args:
        operands: Raw left-hand side of the mapping (before the ``=``).
        label: The unquoted label text (right-hand side).

    Returns:
        A populated ``FormatEntry``, or ``None`` when the operands cannot be
        interpreted as a single value, a range, or the ``other`` catch-all.
    """
    operands = operands.strip()
    if not operands:
        return None
    if operands.lower() == "other":
        return FormatEntry(is_other=True, label=label)
    range_match = _RANGE_RE.match(operands)
    if range_match:
        return FormatEntry(
            low=range_match.group("low"),
            high=range_match.group("high"),
            exclusive_upper=range_match.group("sep") == "-<",
            label=label,
        )
    # Single value: must be one token (a bare number or a quoted literal).
    if len(operands.split()) == 1:
        return FormatEntry(value=operands, label=label)
    return None


def _parse_value_statement(raw_name: str, body: str) -> FormatDef:
    """Parse one ``value`` statement body into a :class:`FormatDef`.

    Args:
        raw_name: The format name as written (may carry a leading ``$``).
        body: The statement text between the name and the terminating ``;``.

    Returns:
        A ``FormatDef`` with all confidently-parsed entries; unparseable mapping
        lines are skipped.
    """
    is_char = raw_name.startswith("$")
    entries: list[FormatEntry] = []
    for match in _MAPPING_RE.finditer(body):
        entry = _parse_mapping(match.group("operands"), match.group("label"))
        if entry is not None:
            entries.append(entry)
    return FormatDef(name=normalize_format_name(raw_name), is_char=is_char, entries=entries)


def extract_format_catalog(source: str) -> dict[str, FormatDef]:
    """Extract all user-defined formats from ``PROC FORMAT`` blocks in ``source``.

    Scans every ``PROC FORMAT ... RUN;`` block and every ``value`` statement
    within each block, building a catalog keyed by normalized format name. The
    function never raises: malformed or unsupported entries are skipped.

    Args:
        source: SAS source text (may contain zero or more PROC FORMAT blocks).

    Returns:
        A mapping of ``{normalized_name: FormatDef}``. Later definitions with the
        same normalized name overwrite earlier ones.
    """
    catalog: dict[str, FormatDef] = {}
    for block_match in _PROC_FORMAT_RE.finditer(source):
        block = block_match.group(0)
        for value_match in _VALUE_STMT_RE.finditer(block):
            fmt_def = _parse_value_statement(value_match.group(1), value_match.group(2))
            catalog[fmt_def.name] = fmt_def
    return catalog
