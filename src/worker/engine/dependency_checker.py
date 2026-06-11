"""Detect missing macro definitions and %INCLUDE paths in a parsed SAS project."""

# SAS: src/worker/engine/dependency_checker.py:1
import os
import re
from collections import Counter

from .models import MissingDependency, ParseResult

# SAS built-in macro keywords and functions — any %word that is NOT a user macro.
# This allowlist covers all standard SAS macro statement keywords and macro functions.
# Any %word token NOT present here is treated as a potential user macro invocation.
_SAS_BUILTINS: frozenset[str] = frozenset(
    {
        # Statement keywords
        "let",
        "if",
        "do",
        "end",
        "then",
        "else",
        "put",
        "global",
        "local",
        "macro",
        "mend",
        "include",
        "return",
        "abort",
        "goto",
        "to",
        "by",
        "while",
        "until",
        # Macro functions
        "str",
        "nrstr",
        "eval",
        "nreval",
        "sysevalf",
        "sysfunc",
        "nrsysfunc",
        "qsysfunc",
        "scan",
        "qscan",
        "substr",
        "qsubstr",
        "index",
        "length",
        "trim",
        "left",
        "right",
        "compress",
        "tranwrd",
        "datatyp",
        "verify",
        "upcase",
        "lowcase",
        "quote",
        "nrquote",
        "bquote",
        "nrbquote",
        "superq",
        "unquote",
    }
)

_MACRO_INVOKE_RE = re.compile(r"%([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)


def _extract_macro_invocations(source: str) -> Counter[str]:
    """Return a Counter of uppercased user macro names found in SAS source.

    Tokens that appear in ``_SAS_BUILTINS`` are excluded so only user-defined
    macro call candidates remain.

    Args:
        source: Raw SAS source text to scan.

    Returns:
        Counter mapping uppercased macro name to occurrence count.
    """
    counts: Counter[str] = Counter()
    for match in _MACRO_INVOKE_RE.finditer(source):
        name = match.group(1).lower()
        if name not in _SAS_BUILTINS:
            counts[name.upper()] += 1
    return counts


def detect_missing_dependencies(
    parse_result: ParseResult,
    files: dict[str, str],
) -> list[MissingDependency]:
    """Detect macro calls and %INCLUDE paths referenced but absent from uploaded files.

    Uses an allowlist approach: all ``%word`` tokens in the SAS source are extracted;
    tokens that match SAS built-in keywords or functions are dropped; the remainder
    are considered user macro invocations. Any invocation whose name does not appear
    in ``parse_result.macro_defs`` is flagged as missing.

    For includes, basename comparison is used so that ``/sas/macros/utils.sas`` matches
    an uploaded file keyed as ``utils.sas``. Include paths containing ``&`` (macro
    variable references) are skipped — they are unresolvable at static analysis time.

    Args:
        parse_result: Result from ``SASParser.parse()`` — contains ``macro_defs``
            and ``includes``.
        files: Uploaded file contents keyed by path (as stored in ``job.files``).

    Returns:
        List of ``MissingDependency`` entries, macros ordered first then includes.
    """
    results: list[MissingDependency] = []

    # --- Macro check ---
    defined_names: frozenset[str] = frozenset(md.name.upper() for md in parse_result.macro_defs)
    all_invocations: Counter[str] = Counter()
    for source in files.values():
        all_invocations.update(_extract_macro_invocations(source))

    for name, count in sorted(all_invocations.items()):
        if name not in defined_names:
            results.append(MissingDependency(name=name, type="macro", reference_count=count))

    # --- Include check ---
    uploaded_basenames: frozenset[str] = frozenset(os.path.basename(k) for k in files)
    for include_path in parse_result.includes:
        # Skip paths containing macro variable references — unresolvable statically
        if "&" in include_path:
            continue
        basename = os.path.basename(include_path)
        if basename and basename not in uploaded_basenames:
            results.append(MissingDependency(name=basename, type="include", reference_count=1))

    return results
