"""SAS macro call expander — deterministic textual expansion of control-flow-free macros.

Expansion happens before block extraction so datasets produced inside macro bodies
(e.g. work.dose from %m_first_dose) are visible to the topo-sort and downstream translators.
"""

from __future__ import annotations

import logging
import re

from src.worker.engine.macro_expander import _substitute_let_vars
from src.worker.engine.models import MacroDef

logger = logging.getLogger(__name__)

# Matches %macroname(...) or %macroname; — captures name and optional arg list
_MACRO_CALL_RE = re.compile(
    r"(?i)%(?!if\b|do\b|while\b|let\b|global\b|return\b|end\b|mend\b|macro\b)(\w+)"
    r"\s*(?:\(([^)]*)\))?\s*;",
)

__all__ = [
    "_is_expandable",
    "bind_args",
    "expand_macro_calls",
    "parse_call_args",
    "parse_macro_params",
]

# Matches %if, %do, %while, %let, %global, %return, %end as whole tokens.
_CONTROL_FLOW_RE = re.compile(r"%\s*(if|do|while|let|global|return|end)\b", re.IGNORECASE)


def parse_macro_params(param_str: str) -> list[tuple[str, str | None]]:
    """Parse the parameter declaration string from a %MACRO definition header.

    Args:
        param_str: Raw text between the outer parentheses of the %MACRO header,
            e.g. ``"in=, out=, by=USUBJID"`` or ``"a, b, c"`` or ``""``.

    Returns:
        Ordered list of ``(name, default)`` tuples where:
        - ``default`` is ``None`` for bare positional parameters (no ``=``).
        - ``default`` is ``""`` for keyword parameters declared without a value
          (e.g. ``in=``).
        - ``default`` is the literal string for parameters with an explicit
          default (e.g. ``"USUBJID"`` for ``by=USUBJID``).
    """
    # SAS: macro_call_expander.py:38
    if not param_str.strip():
        return []

    result: list[tuple[str, str | None]] = []
    for token in param_str.split(","):
        token = token.strip()
        if not token:
            continue
        if "=" in token:
            name, _, default = token.partition("=")
            result.append((name.strip(), default.strip()))
        else:
            result.append((token, None))
    return result


def parse_call_args(arg_str: str) -> tuple[list[str], dict[str, str]]:
    """Parse the argument string from a macro call site.

    Args:
        arg_str: Raw text between the outer parentheses of the macro call,
            e.g. ``"in=sdtm.ex, out=work.dose"`` or ``"val1, val2"`` or ``""``.

    Returns:
        A two-element tuple ``(positional, keyword)`` where *positional* is a
        list of values for arguments without ``=`` and *keyword* is a dict
        mapping ``{name: value}`` for arguments that include ``=``.
    """
    # SAS: macro_call_expander.py:60
    if not arg_str.strip():
        return ([], {})

    positional: list[str] = []
    keyword: dict[str, str] = {}

    for token in arg_str.split(","):
        token = token.strip()
        if not token:
            continue
        if "=" in token:
            name, _, value = token.partition("=")
            keyword[name.strip()] = value.strip()
        else:
            positional.append(token)

    return (positional, keyword)


def bind_args(
    params: list[tuple[str, str | None]],
    positional: list[str],
    keyword: dict[str, str],
) -> dict[str, str]:
    """Resolve the final variable map for a macro call.

    Keyword arguments take precedence over positional arguments; positional
    arguments fill parameters left-to-right, skipping any that were already
    supplied as keyword arguments.  Parameters with a non-empty default string
    are used as a last-resort fallback.

    Args:
        params: Ordered parameter declarations from :func:`parse_macro_params`.
        positional: Positional argument values from :func:`parse_call_args`.
        keyword: Keyword argument mapping from :func:`parse_call_args`.

    Returns:
        Dict mapping each parameter name (as declared) to its resolved string
        value.

    Raises:
        ValueError: When a required parameter has no supplied value and no
            non-empty default.
    """
    # SAS: macro_call_expander.py:85
    keyword_upper: dict[str, str] = {k.upper(): v for k, v in keyword.items()}
    result: dict[str, str] = {}
    pos_index = 0

    for name, default in params:
        upper_name = name.upper()
        if upper_name in keyword_upper:
            result[name] = keyword_upper[upper_name]
            continue

        # Not supplied as keyword — try positional fill for params not already bound.
        if pos_index < len(positional):
            result[name] = positional[pos_index]
            pos_index += 1
            continue

        # Fall back to default value if non-empty.
        if default is not None and default != "":
            result[name] = default
            continue

        raise ValueError(f"Missing required macro parameter: {name}")

    return result


def _is_expandable(body: str) -> bool:
    """Return True when *body* contains no SAS macro control-flow keywords.

    The check is intentionally conservative: any occurrence of ``%if``,
    ``%do``, ``%while``, ``%let``, ``%global``, ``%return``, or ``%end``
    (matched as whole tokens, case-insensitive) causes the macro to be treated
    as non-expandable.

    Args:
        body: Raw SAS text of the macro body (between %MACRO header and %MEND).

    Returns:
        ``True`` if the body is safe for deterministic textual expansion,
        ``False`` otherwise.
    """
    # SAS: macro_call_expander.py:127
    return _CONTROL_FLOW_RE.search(body) is None


def expand_macro_calls(source: str, macro_defs: dict[str, MacroDef]) -> str:
    """Expand all expandable macro calls in *source* to a fixed point.

    Iterates up to 10 rounds of substitution.  On each round every call whose
    macro is present in *macro_defs* and passes :func:`_is_expandable` is
    replaced with the macro body after parameter substitution.  Calls to
    unknown macros or non-expandable macros are left verbatim.

    Args:
        source: Full SAS source text (may contain multiple macro calls).
        macro_defs: Dict keyed by UPPERCASE macro name mapping to
            :class:`~src.worker.engine.models.MacroDef` instances.

    Returns:
        Source text with all eligible macro calls expanded, wrapped in
        provenance markers.  Identical to *source* when no expansion applies.
    """
    # SAS: macro_call_expander.py:160

    _max_rounds = 10

    for _ in range(_max_rounds):

        def _replacer(m: re.Match[str]) -> str:
            name = m.group(1).upper()
            arg_str = m.group(2) or ""

            if name not in macro_defs:
                return m.group(0)

            macro = macro_defs[name]
            if not _is_expandable(macro.body):
                return m.group(0)

            params = parse_macro_params(macro.param_str)
            positional, keyword = parse_call_args(arg_str)
            try:
                var_map = bind_args(params, positional, keyword)
            except ValueError as exc:
                logger.warning("Skipping expansion of %%%s: %s", name, exc)
                return m.group(0)

            # _substitute_let_vars expects uppercase keys
            upper_var_map = {k.upper(): v for k, v in var_map.items()}
            substituted = _substitute_let_vars(macro.body, upper_var_map)

            return (
                f"/* SAS-MACRO-EXPANDED: {name} from"
                f" {macro.source_file}:{macro.line} */\n"
                f"{substituted}\n"
                f"/* SAS-MACRO-END: {name} */"
            )

        expanded = _MACRO_CALL_RE.sub(_replacer, source)
        if expanded == source:
            break
        source = expanded

    return source
