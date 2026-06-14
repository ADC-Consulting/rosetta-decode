"""Deterministic SAS macro control-flow evaluator.

Resolves ``%if/%then/%else``, ``%do;...%end;`` blocks, iterative ``%do i=a %to b``
loops, and ``%let/%global/%put/%return`` against an already-bound environment.

This module is pure (no I/O, no LLM, no randomness): the same SAS body and the same
environment always produce the same output. Any construct that cannot be evaluated
deterministically raises :class:`CannotResolveMacroLogic`, leaving the caller to keep
the macro unexpanded rather than guessing a branch or emitting partial output.

It reuses :func:`~src.worker.engine.macro_expander._substitute_let_vars` for ``&var``
substitution and is intentionally call-agnostic: it receives an already-bound *env*
and never resolves macro-call arguments itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.worker.engine.macro_expander import _substitute_let_vars

__all__ = [
    "CannotResolveMacroLogic",
    "MacroLogicResult",
    "evaluate_condition",
    "resolve_macro_body",
]

# Module-level cap on TOTAL iterations emitted across one resolve_macro_body call.
MAX_UNROLL = 1000


class CannotResolveMacroLogic(Exception):  # noqa: N818  # public API name pinned by F59 spec
    """Raised for any unsupported construct or condition that is not deterministically evaluable."""


@dataclass(frozen=True)
class MacroLogicResult:
    """Result of resolving a macro body.

    Attributes:
        sas_text: The resolved SAS text of the taken control-flow path, with
            ``%let``/``%global`` env vars substituted and ``&param`` refs left intact.
        assigned_globals: Mapping of UPPERCASE ``%global NAME=VALUE`` assignments made
            during resolution (bare ``%global NAME;`` declarations are excluded).
    """

    sas_text: str
    assigned_globals: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Token:
    """A single lexical token produced by the tokenizer.

    Attributes:
        kind: The token kind (e.g. ``MIF``, ``MDO_ITER``, ``SAS_TEXT``).
        text: The associated raw text (condition text, loop header, value, or SAS run).
    """

    kind: str
    text: str


# --- S-A0: tokenizer ---------------------------------------------------------

# /* ... */ comments and %* ... ; macro comments.
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_MACRO_COMMENT_RE = re.compile(r"%\*.*?;", re.DOTALL)

# Integer literal (used by both the condition evaluator and the loop unroller).
_INT_RE = re.compile(r"^-?\d+$")

# %length(arg) — the only function the condition evaluator supports.
_LENGTH_RE = re.compile(r"(?i)%length\s*\(\s*([^()]*?)\s*\)")

# Comparison operator aliases mapped to a canonical symbol.
_COMPARISON_OPS: dict[str, str] = {
    "=": "=",
    "eq": "=",
    "ne": "ne",
    "^=": "ne",
    "~=": "ne",
    "<>": "ne",
    "<=": "<=",
    "le": "<=",
    ">=": ">=",
    "ge": ">=",
    "<": "<",
    "lt": "<",
    ">": ">",
    "gt": ">",
}

# Ordered longest-first so multi-char symbols win over single-char ones.
_OP_SYMBOLS = ["<=", ">=", "^=", "~=", "<>", "=", "<", ">"]


def _strip_comments(body: str) -> str:
    """Remove ``/* ... */`` and ``%* ... ;`` comments, leaving all other text intact."""
    # SAS: macro_logic.py:_strip_comments
    body = _BLOCK_COMMENT_RE.sub("", body)
    return _MACRO_COMMENT_RE.sub("", body)


def _match_keyword(text: str, pos: int, keyword: str) -> bool:
    """Return True if *keyword* begins at *pos*, case-insensitively, with a word boundary."""
    segment = text[pos : pos + len(keyword)]
    if segment.lower() != keyword.lower():
        return False
    after = pos + len(keyword)
    return not (after < len(text) and text[after].isalnum())


def _read_until_semicolon(text: str, start: int) -> tuple[str, int]:
    """Return the substring from *start* through the next ``;`` and the index after it."""
    end = text.find(";", start)
    if end == -1:
        end = len(text)
        return text[start:end], end
    return text[start : end + 1], end + 1


def _read_do_header(text: str, pos: int) -> tuple[Token | None, int]:
    """Tokenize a ``%do`` construct starting at *pos*; return the token and next index."""
    # SAS: macro_logic.py:_read_do_header
    header, after = _read_until_semicolon(text, pos)
    lowered = header.lower()
    if re.search(r"%\s*while\b", lowered):
        return Token("MDO_WHILE", header.strip()), after
    if re.search(r"%\s*until\b", lowered):
        return Token("MDO_UNTIL", header.strip()), after
    # Iterative form contains '%to'; bare block form is just '%do;'.
    if re.search(r"%\s*to\b", lowered):
        return Token("MDO_ITER", header.strip()), after
    body = header.strip().rstrip(";").strip()
    if body.lower() == "%do":
        return Token("MDO_BLOCK", "%do;"), after
    # Anything else after %do that we do not recognise -> let caller decide via header.
    return Token("MDO_ITER", header.strip()), after


def _read_macro_keyword_token(text: str, pos: int) -> tuple[Token | None, int]:
    """Tokenize a macro control keyword at *pos*; return ``(token_or_None, next_pos)``.

    Returns ``(None, pos)`` when no macro control keyword begins at *pos* so the caller
    can accumulate the character into a ``SAS_TEXT`` run.
    """
    # SAS: macro_logic.py:_read_macro_keyword_token
    if _match_keyword(text, pos, "%if"):
        cond_start = pos + len("%if")
        then_idx = re.search(r"(?i)%\s*then\b", text[cond_start:])
        if then_idx is None:
            raise CannotResolveMacroLogic("%if without %then")
        cond_text = text[cond_start : cond_start + then_idx.start()].strip()
        return Token("MIF", cond_text), cond_start + then_idx.start()
    if _match_keyword(text, pos, "%then"):
        return Token("MTHEN", "%then"), pos + len("%then")
    if _match_keyword(text, pos, "%else"):
        return Token("MELSE", "%else"), pos + len("%else")
    if _match_keyword(text, pos, "%do"):
        return _read_do_header(text, pos)
    if _match_keyword(text, pos, "%end"):
        _, after = _read_until_semicolon(text, pos)
        return Token("MEND", "%end;"), after
    if _match_keyword(text, pos, "%let"):
        body, after = _read_until_semicolon(text, pos)
        return Token("MLET", body.strip()), after
    if _match_keyword(text, pos, "%global"):
        body, after = _read_until_semicolon(text, pos)
        return Token("MGLOBAL", body.strip()), after
    if _match_keyword(text, pos, "%return"):
        _, after = _read_until_semicolon(text, pos)
        return Token("MRETURN", "%return;"), after
    if _match_keyword(text, pos, "%put"):
        body, after = _read_until_semicolon(text, pos)
        return Token("MPUT", body.strip()), after
    return None, pos


def _tokenize(body: str) -> list[Token]:
    """Tokenize a macro body into ordered control-flow and SAS-text tokens.

    This is the only layer that touches raw text. Comments are stripped first; macro
    keywords are matched case-insensitively; everything else accumulates into
    ``SAS_TEXT`` runs.

    Args:
        body: Raw SAS macro body text.

    Returns:
        Ordered list of :class:`Token`.

    Raises:
        CannotResolveMacroLogic: If an ``%if`` lacks a matching ``%then``.
    """
    # SAS: macro_logic.py:_tokenize
    text = _strip_comments(body)
    tokens: list[Token] = []
    buffer: list[str] = []
    pos = 0
    length = len(text)

    def _flush() -> None:
        if buffer:
            run = "".join(buffer)
            if run.strip():
                tokens.append(Token("SAS_TEXT", run))
            buffer.clear()

    while pos < length:
        if text[pos] == "%":
            token, after = _read_macro_keyword_token(text, pos)
            if token is not None:
                _flush()
                tokens.append(token)
                pos = after
                continue
        buffer.append(text[pos])
        pos += 1

    _flush()
    return tokens


# --- S-A: condition evaluator ------------------------------------------------


def _resolve_length_calls(expr: str) -> str | None:
    """Replace every ``%length(arg)`` with the integer length of its argument.

    Returns ``None`` if a residual ``%length`` (e.g. nested/unparsable) remains.
    """
    # SAS: macro_logic.py:_resolve_length_calls
    resolved = _LENGTH_RE.sub(lambda m: str(len(m.group(1))), expr)
    if re.search(r"(?i)%length", resolved):
        return None
    return resolved


def _compare(left: str, op: str, right: str) -> bool:
    """Apply a canonical comparison operator to two operand strings (pinned type rule)."""
    # SAS: macro_logic.py:_compare
    if _INT_RE.match(left) and _INT_RE.match(right):
        lval: int | str = int(left)
        rval: int | str = int(right)
    else:
        lval, rval = left, right
    if op == "=":
        return lval == rval
    if op == "ne":
        return lval != rval
    if op == "<":
        return lval < rval  # type: ignore[operator]
    if op == ">":
        return lval > rval  # type: ignore[operator]
    if op == "<=":
        return lval <= rval  # type: ignore[operator]
    if op == ">=":
        return lval >= rval  # type: ignore[operator]
    raise CannotResolveMacroLogic(f"unknown operator: {op}")


def _split_top_level(expr: str, keyword: str) -> list[str] | None:
    """Split *expr* on a whole-word boundary *keyword* (case-insensitive) outside parentheses.

    Returns the list of segments, or ``None`` if any split point sits inside unbalanced
    parentheses (malformed).
    """
    # SAS: macro_logic.py:_split_top_level
    pattern = re.compile(rf"(?i)\b{keyword}\b")
    segments: list[str] = []
    depth = 0
    last = 0
    idx = 0
    while idx < len(expr):
        char = expr[idx]
        if char == "(":
            depth += 1
            idx += 1
            continue
        if char == ")":
            depth -= 1
            if depth < 0:
                return None
            idx += 1
            continue
        if depth == 0:
            match = pattern.match(expr, idx)
            if match:
                segments.append(expr[last : match.start()])
                last = match.end()
                idx = match.end()
                continue
        idx += 1
    if depth != 0:
        return None
    segments.append(expr[last:])
    return segments


def _eval_expr(expr: str) -> bool | None:
    """Recursively evaluate a fully-substituted boolean expression (OR > AND > comparison)."""
    # SAS: macro_logic.py:_eval_expr
    expr = expr.strip()
    if not expr:
        return None

    or_parts = _split_top_level(expr, "or")
    if or_parts is None:
        return None
    if len(or_parts) > 1:
        results = [_eval_expr(part) for part in or_parts]
        if any(r is None for r in results):
            return None
        return any(results)

    and_parts = _split_top_level(expr, "and")
    if and_parts is None:
        return None
    if len(and_parts) > 1:
        results = [_eval_expr(part) for part in and_parts]
        if any(r is None for r in results):
            return None
        return all(results)

    return _eval_comparison(expr)


def _eval_comparison(expr: str) -> bool | None:
    """Evaluate a parenthesised group or a single ``lhs op rhs`` comparison."""
    # SAS: macro_logic.py:_eval_comparison
    expr = expr.strip()
    if expr.startswith("(") and expr.endswith(")") and _is_balanced_wrapper(expr):
        return _eval_expr(expr[1:-1])

    for symbol in _OP_SYMBOLS:
        idx = _find_top_level_symbol(expr, symbol)
        if idx != -1:
            left = expr[:idx].strip()
            right = expr[idx + len(symbol) :].strip()
            if not left or not right:
                return None
            if "(" in left or "(" in right or ")" in left or ")" in right:
                return None
            return _compare(left, _COMPARISON_OPS[symbol], right)

    # Alias word operators (eq/ne/lt/gt/le/ge) as whole words.
    for alias in ("eq", "ne", "lt", "gt", "le", "ge"):
        match = re.search(rf"(?i)\b{alias}\b", expr)
        if match:
            left = expr[: match.start()].strip()
            right = expr[match.end() :].strip()
            if not left or not right:
                return None
            return _compare(left, _COMPARISON_OPS[alias], right)

    return None


def _is_balanced_wrapper(expr: str) -> bool:
    """Return True if the outer parentheses of *expr* wrap the whole expression."""
    depth = 0
    for idx, char in enumerate(expr):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0 and idx != len(expr) - 1:
                return False
    return depth == 0


def _find_top_level_symbol(expr: str, symbol: str) -> int:
    """Return the index of the first *symbol* outside parentheses, or -1 if none."""
    depth = 0
    idx = 0
    while idx < len(expr):
        char = expr[idx]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif depth == 0 and expr.startswith(symbol, idx):
            # Avoid matching '<' inside '<=' / '<>' or '>' inside '>='.
            if symbol in ("<", ">", "=") and idx + 1 < len(expr) and expr[idx + 1] in "=<>":
                idx += 1
                continue
            return idx
        idx += 1
    return -1


def evaluate_condition(expr: str, env: dict[str, str]) -> bool | None:
    """Deterministically evaluate a ``%if`` condition. Never raises.

    Substitutes ``&var`` references from *env*, resolves ``%length(...)``, then parses
    with precedence comparisons > ``AND`` > ``OR`` and recursive parentheses.

    Args:
        expr: The raw condition text (between ``%if`` and ``%then``).
        env: UPPERCASE-keyed environment of resolved macro variables.

    Returns:
        ``True``/``False`` when the condition is deterministically evaluable, or ``None``
        when any ``&ref`` is unresolved, an unsupported function appears, or it is malformed.
    """
    # SAS: macro_logic.py:evaluate_condition
    substituted = _substitute_let_vars(expr, env)
    if re.search(r"&\w+", substituted):
        return None  # unresolved reference
    # Reject unsupported functions (only %length is allowed).
    for match in re.finditer(r"(?i)%(\w+)", substituted):
        if match.group(1).lower() != "length":
            return None
    resolved = _resolve_length_calls(substituted)
    if resolved is None:
        return None
    try:
        return _eval_expr(resolved)
    except CannotResolveMacroLogic:
        return None


# --- S-B / S-B2: body resolver -----------------------------------------------

_LET_RE = re.compile(r"(?is)^%let\s+(\w+)\s*=(.*);$")
_GLOBAL_ASSIGN_RE = re.compile(r"(?is)^%global\s+(\w+)\s*=(.*);$")
_GLOBAL_DECL_RE = re.compile(r"(?is)^%global\s+(.+?);$")
_DO_ITER_RE = re.compile(r"(?is)^%do\s+(\w+)\s*=\s*(.+?)\s+%to\s+(.+?)(?:\s+%by\s+(.+?))?\s*;$")


class _Resolver:
    """Recursive-descent resolver over a token stream with an explicit cursor."""

    def __init__(self, tokens: list[Token], env: dict[str, str]) -> None:
        """Initialise with the full token list and a mutable copy of the environment."""
        self._tokens = tokens
        self._env = dict(env)
        self._assigned_globals: dict[str, str] = {}
        self._total_emitted = 0
        # Loop variables currently in scope (UPPERCASE -> value). These are the only
        # env vars substituted into SAS_TEXT and %global names; macro params stay intact.
        self._loop_vars: dict[str, str] = {}

    @property
    def assigned_globals(self) -> dict[str, str]:
        """Return the globals assigned (with values) during resolution."""
        return self._assigned_globals

    def resolve(self) -> str:
        """Resolve the whole token stream and return the concatenated taken-path text."""
        # SAS: macro_logic.py:_Resolver.resolve
        return self._resolve_range(0, len(self._tokens))[0]

    def _resolve_range(self, start: int, stop: int) -> tuple[str, bool]:
        """Resolve tokens in ``[start, stop)``; return ``(text, returned)``.

        ``returned`` is True once a ``%return;`` halts the taken path.
        """
        # SAS: macro_logic.py:_Resolver._resolve_range
        parts: list[str] = []
        cursor = start
        while cursor < stop:
            token = self._tokens[cursor]
            text, cursor, returned = self._dispatch(token, cursor, stop)
            if text:
                parts.append(text)
            if returned:
                return "".join(parts), True
        return "".join(parts), False

    def _dispatch(self, token: Token, cursor: int, stop: int) -> tuple[str, int, bool]:
        """Handle a single token; return ``(emitted_text, next_cursor, returned)``."""
        # SAS: macro_logic.py:_Resolver._dispatch
        kind = token.kind
        if kind == "SAS_TEXT":
            # Substitute only active loop variables; macro &params are left intact.
            text = token.text
            if self._loop_vars:
                text = _substitute_let_vars(text, self._loop_vars)
            return text, cursor + 1, False
        if kind in ("MDO_WHILE", "MDO_UNTIL"):
            raise CannotResolveMacroLogic(f"unsupported construct: {token.text}")
        if kind == "MLET":
            self._apply_let(token.text)
            return "", cursor + 1, False
        if kind == "MGLOBAL":
            self._apply_global(token.text)
            return "", cursor + 1, False
        if kind == "MPUT":
            return "", cursor + 1, False
        if kind == "MRETURN":
            return "", cursor + 1, True
        if kind == "MIF":
            return self._resolve_if(cursor, stop)
        if kind == "MDO_ITER":
            return self._resolve_loop(cursor, stop)
        if kind == "MDO_BLOCK":
            return self._resolve_block(cursor)
        # MTHEN / MELSE / MEND should be consumed by their owners.
        raise CannotResolveMacroLogic(f"unexpected token: {kind}")

    # --- %let / %global -------------------------------------------------------

    def _apply_let(self, raw: str) -> None:
        """Apply a ``%let NAME=VALUE;`` to the env, substituting VALUE first."""
        # SAS: macro_logic.py:_Resolver._apply_let
        if self._loop_vars:
            raw = _substitute_let_vars(raw, self._loop_vars)
        match = _LET_RE.match(raw)
        if match is None:
            raise CannotResolveMacroLogic(f"malformed %let: {raw}")
        name, value = match.group(1), match.group(2).strip()
        self._env[name.upper()] = _substitute_let_vars(value, self._env)

    def _apply_global(self, raw: str) -> None:
        """Apply a ``%global`` statement: assignment updates env + records, decl declares only."""
        # SAS: macro_logic.py:_Resolver._apply_global
        if self._loop_vars:
            raw = _substitute_let_vars(raw, self._loop_vars)
        match = _GLOBAL_ASSIGN_RE.match(raw)
        if match is not None:
            name, value = match.group(1), match.group(2).strip()
            resolved = _substitute_let_vars(value, self._env)
            self._env[name.upper()] = resolved
            self._assigned_globals[name.upper()] = resolved
            return
        if _GLOBAL_DECL_RE.match(raw) is not None:
            return  # bare declaration only
        raise CannotResolveMacroLogic(f"malformed %global: {raw}")

    # --- %do; ... %end; -------------------------------------------------------

    def _find_matching_end(self, open_cursor: int, stop: int) -> int:
        """Return the index of the ``MEND`` matching the ``MDO_*`` at *open_cursor*."""
        # SAS: macro_logic.py:_Resolver._find_matching_end
        depth = 0
        cursor = open_cursor
        while cursor < stop:
            kind = self._tokens[cursor].kind
            if kind.startswith("MDO_"):
                depth += 1
            elif kind == "MEND":
                depth -= 1
                if depth == 0:
                    return cursor
            cursor += 1
        raise CannotResolveMacroLogic("unbalanced %do/%end")

    def _resolve_block(self, cursor: int) -> tuple[str, int, bool]:
        """Resolve a bare ``%do;...%end;`` block at *cursor*."""
        # SAS: macro_logic.py:_Resolver._resolve_block
        end = self._find_matching_end(cursor, len(self._tokens))
        text, returned = self._resolve_range(cursor + 1, end)
        return text, end + 1, returned

    # --- %if / %then / %else --------------------------------------------------

    def _resolve_if(self, cursor: int, stop: int) -> tuple[str, int, bool]:
        """Resolve an ``%if`` construct; emit only the taken arm, walk past the untaken one."""
        # SAS: macro_logic.py:_Resolver._resolve_if
        condition = self._tokens[cursor].text
        verdict = evaluate_condition(condition, self._env)
        if verdict is None:
            raise CannotResolveMacroLogic(f"unresolvable condition: {condition}")

        if self._tokens[cursor + 1].kind != "MTHEN":
            raise CannotResolveMacroLogic("%if without %then token")
        then_start = cursor + 2
        then_end = self._arm_bounds(then_start, stop)

        else_start = then_end
        has_else = else_start < stop and self._tokens[else_start].kind == "MELSE"
        if has_else:
            else_body_start = else_start + 1
            else_end = self._arm_bounds(else_body_start, stop)
        else:
            else_body_start = else_end = else_start

        if verdict:
            text, returned = self._resolve_arm(then_start, then_end)
        elif has_else:
            text, returned = self._resolve_arm(else_body_start, else_end)
        else:
            text, returned = "", False

        return text, else_end if has_else else then_end, returned

    def _arm_bounds(self, start: int, stop: int) -> int:
        """Return the index just past one arm beginning at *start* (block or single stmt)."""
        # SAS: macro_logic.py:_Resolver._arm_bounds
        token = self._tokens[start]
        if token.kind == "MDO_BLOCK":
            return self._find_matching_end(start, stop) + 1
        if token.kind in ("MDO_ITER", "MDO_WHILE", "MDO_UNTIL"):
            return self._find_matching_end(start, stop) + 1
        # Single-statement arm: exactly one token (SAS_TEXT/MLET/MGLOBAL/MPUT/MRETURN/MIF).
        if token.kind == "MIF":
            # Nested %if as the arm: consume the whole nested construct.
            return self._arm_consume_if(start, stop)
        return start + 1

    def _arm_consume_if(self, start: int, stop: int) -> int:
        """Return the index past a nested ``%if`` used as a single-statement arm."""
        # SAS: macro_logic.py:_Resolver._arm_consume_if
        then_start = start + 2  # skip MIF, MTHEN
        then_end = self._arm_bounds(then_start, stop)
        if then_end < stop and self._tokens[then_end].kind == "MELSE":
            return self._arm_bounds(then_end + 1, stop)
        return then_end

    def _resolve_arm(self, start: int, end: int) -> tuple[str, bool]:
        """Resolve one arm. A ``%do;`` block arm strips its own ``%do/%end`` wrapper."""
        # SAS: macro_logic.py:_Resolver._resolve_arm
        if self._tokens[start].kind == "MDO_BLOCK":
            return self._resolve_range(start + 1, end - 1)
        return self._resolve_range(start, end)

    # --- %do i=a %to b loop ---------------------------------------------------

    def _resolve_loop(self, cursor: int, stop: int) -> tuple[str, int, bool]:
        """Unroll an iterative ``%do i=START %to END [%by STEP];`` loop."""
        # SAS: macro_logic.py:_Resolver._resolve_loop
        header = self._tokens[cursor].text
        match = _DO_ITER_RE.match(header)
        if match is None:
            raise CannotResolveMacroLogic(f"unsupported %do header: {header}")
        loopvar = match.group(1)
        start_val = self._resolve_int(match.group(2))
        end_val = self._resolve_int(match.group(3))
        step_val = self._resolve_int(match.group(4)) if match.group(4) else 1
        if step_val == 0:
            raise CannotResolveMacroLogic("%do loop step must be non-zero")

        body_end = self._find_matching_end(cursor, stop)
        body_start = cursor + 1

        parts: list[str] = []
        returned = False
        prior_loop = self._loop_vars.get(loopvar.upper())
        prior_env = self._env.get(loopvar.upper())
        for value in self._iter_range(start_val, end_val, step_val):
            self._env[loopvar.upper()] = str(value)
            self._loop_vars[loopvar.upper()] = str(value)
            self._total_emitted += 1
            if self._total_emitted > MAX_UNROLL:
                raise CannotResolveMacroLogic(f"loop exceeds MAX_UNROLL={MAX_UNROLL}")
            text, returned = self._resolve_range(body_start, body_end)
            if text:
                parts.append(text)
            if returned:
                break
        self._restore_scope(loopvar.upper(), prior_loop, prior_env)
        return "".join(parts), body_end + 1, returned

    def _restore_scope(self, key: str, prior_loop: str | None, prior_env: str | None) -> None:
        """Restore the loop/env scope for *key* after a loop completes (supports nesting)."""
        # SAS: macro_logic.py:_Resolver._restore_scope
        if prior_loop is None:
            self._loop_vars.pop(key, None)
        else:
            self._loop_vars[key] = prior_loop
        if prior_env is None:
            self._env.pop(key, None)
        else:
            self._env[key] = prior_env

    def _resolve_int(self, raw: str) -> int:
        """Substitute env vars in *raw* and require an integer literal result."""
        # SAS: macro_logic.py:_Resolver._resolve_int
        substituted = _substitute_let_vars(raw.strip(), self._env).strip()
        if not _INT_RE.match(substituted):
            raise CannotResolveMacroLogic(f"non-integer loop bound: {raw!r} -> {substituted!r}")
        return int(substituted)

    @staticmethod
    def _iter_range(start: int, end: int, step: int) -> list[int]:
        """Return the inclusive integer sequence for ``%do i=start %to end %by step``."""
        # SAS: macro_logic.py:_Resolver._iter_range
        values: list[int] = []
        value = start
        if step > 0:
            while value <= end:
                values.append(value)
                value += step
        else:
            while value >= end:
                values.append(value)
                value += step
        return values


def resolve_macro_body(body: str, env: dict[str, str]) -> MacroLogicResult:
    """Deterministically resolve a SAS macro body against *env*.

    Tokenizes the body then walks the tokens with a recursive-descent resolver, emitting
    only taken ``%if`` branches, unrolling bounded iterative ``%do`` loops, applying
    ``%let``/``%global`` to the running env, recording ``%global`` assignments, and
    halting the taken path on ``%return;``. ``SAS_TEXT`` is emitted verbatim with
    ``&param`` references left intact.

    All-or-nothing: any :class:`CannotResolveMacroLogic` propagates out before returning,
    so no partial text or assigned_globals is ever produced.

    Args:
        body: Raw SAS macro body text.
        env: UPPERCASE-keyed environment of already-bound macro variables.

    Returns:
        A :class:`MacroLogicResult` with the resolved text and recorded global assignments.

    Raises:
        CannotResolveMacroLogic: For any unsupported construct or unresolvable condition.
    """
    # SAS: macro_logic.py:resolve_macro_body
    tokens = _tokenize(body)
    resolver = _Resolver(tokens, env)
    sas_text = resolver.resolve()
    return MacroLogicResult(sas_text=sas_text, assigned_globals=dict(resolver.assigned_globals))
