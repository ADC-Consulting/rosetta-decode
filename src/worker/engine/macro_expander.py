"""SAS macro expansion: %LET variable substitution and zero-arg %MACRO/%MEND inlining."""

import re

from src.worker.engine.models import MacroVar, SASBlock


class CannotExpandError(Exception):
    """Raised when a macro cannot be safely expanded by the MVP expander."""

    def __init__(self, macro_name: str, reason: str) -> None:
        """Initialise with macro name and reason string."""
        self.macro_name = macro_name
        self.reason = reason
        super().__init__(f"Cannot expand macro %{macro_name}: {reason}")


# Alias for backward compatibility
CannotExpand = CannotExpandError


# Matches &NAME or &NAME. (dot-terminated)
_LET_REF_RE = re.compile(r"&(\w+)(\.)?", re.IGNORECASE)

# Matches full %MACRO ... %MEND blocks
_MACRO_DEF_RE = re.compile(
    r"(?i)%MACRO\s+(\w+)\s*(?:\(([^)]*)\))?\s*;(.*?)%MEND\s+\1\s*;",
    re.DOTALL | re.IGNORECASE,
)

# Matches a macro call: %NAME or %NAME() or %NAME(args)
_MACRO_CALL_RE = re.compile(r"(?i)%(\w+)\s*(\([^)]*\))?(?=\s|;|$)", re.IGNORECASE)

_CONDITIONAL_RE = re.compile(r"%IF|%ELSE", re.IGNORECASE)


def _substitute_let_vars(text: str, var_map: dict[str, str]) -> str:
    """Replace all &NAME and &NAME. references using *var_map* (keys uppercase)."""

    def _replace(m: re.Match[str]) -> str:
        key = m.group(1).upper()
        if key not in var_map:
            return m.group(0)  # leave unresolved references intact
        value = var_map[key]
        # dot is consumed (separator), no trailing dot in output
        return value

    return _LET_REF_RE.sub(_replace, text)


def _collect_macro_definitions(blocks: list[SASBlock]) -> dict[str, str]:
    """Return a map of uppercase macro name -> body text for all zero-arg definitions found."""
    definitions: dict[str, str] = {}
    for block in blocks:
        for m in _MACRO_DEF_RE.finditer(block.raw_sas):
            name = m.group(1).upper()
            params = (m.group(2) or "").strip()
            body = m.group(3)
            if params:
                # Parameterised — record as sentinel so call-site raises CannotExpand
                definitions[name] = "__PARAMETERISED__"
            else:
                definitions[name] = body
    return definitions


def _inline_macros(text: str, macro_defs: dict[str, str]) -> str:
    """Inline zero-arg macro calls in *text* using *macro_defs*."""

    def _replace_call(m: re.Match[str]) -> str:
        name = m.group(1).upper()
        arg_part = m.group(2)  # None or "(…)"

        # Skip built-in SAS macro keywords that are not user-defined
        if name not in macro_defs:
            if arg_part is None:
                return m.group(0)  # not a known macro; leave intact
            raise CannotExpandError(name, "macro not found in any block")

        body = macro_defs[name]
        if body == "__PARAMETERISED__":
            raise CannotExpandError(name, "parameterised macros are not supported in MVP")
        if _CONDITIONAL_RE.search(body):
            raise CannotExpandError(name, "macro body contains conditional logic (%IF/%ELSE)")

        return body.strip()

    return _MACRO_CALL_RE.sub(_replace_call, text)


def _has_macro_calls(text: str, macro_defs: dict[str, str]) -> bool:
    """Return True if *text* contains at least one call to a known user macro."""
    return any(m.group(1).upper() in macro_defs for m in _MACRO_CALL_RE.finditer(text))


def _has_unknown_macro_calls(text: str, macro_defs: dict[str, str]) -> bool:
    """Return True if *text* contains a macro call with args that is not defined."""
    for m in _MACRO_CALL_RE.finditer(text):
        name = m.group(1).upper()
        arg_part = m.group(2)
        if name not in macro_defs and arg_part is not None:
            return True
    return False


class MacroExpander:
    """Expand SAS macro variables and inline zero-arg macro definitions."""

    def expand(self, blocks: list[SASBlock], macro_vars: list[MacroVar]) -> list[SASBlock]:
        """Return new SASBlock list with %LET substitutions and zero-arg macro inlining applied.

        Args:
            blocks: Parsed SAS blocks from the engine parser.
            macro_vars: Resolved %LET declarations extracted from the same source.

        Returns:
            New list of SASBlock instances with expanded raw_sas; input is not mutated.

        Raises:
            CannotExpand: When a macro call cannot be safely inlined.
        """
        var_map: dict[str, str] = {v.name.upper(): v.raw_value for v in macro_vars}
        macro_defs = _collect_macro_definitions(blocks)

        result: list[SASBlock] = []
        for block in blocks:
            raw = block.raw_sas

            if var_map:
                raw = _substitute_let_vars(raw, var_map)

            if _has_macro_calls(raw, macro_defs) or _has_unknown_macro_calls(raw, macro_defs):
                raw = _inline_macros(raw, macro_defs)

            if raw == block.raw_sas:
                result.append(block)
            else:
                result.append(block.model_copy(update={"raw_sas": raw}))

        return result
