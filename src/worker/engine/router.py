"""TranslationRouter — maps SAS BlockType to the correct translator instance."""

from __future__ import annotations

import logging
import re
from typing import Any

from src.worker.engine.models import (
    BlockPlan,
    BlockType,
    GeneratedBlock,
    JobContext,
    SASBlock,
    TranslationStrategy,
)
from src.worker.engine.stub_generator import StubGenerator

# Block types that the GenericProcAgent handles (everything that isn't DATA/SQL/SORT)
_GENERIC_PROC_TYPES: frozenset[BlockType] = frozenset(
    {
        BlockType.PROC_IML,
        BlockType.PROC_FCMP,
        BlockType.PROC_MEANS,
        BlockType.PROC_FREQ,
        BlockType.PROC_TRANSPOSE,
        BlockType.PROC_IMPORT,
        BlockType.PROC_EXPORT,
        BlockType.PROC_PRINT,
        BlockType.PROC_CONTENTS,
        BlockType.PROC_DATASETS,
        BlockType.PROC_OPTMODEL,
        BlockType.PROC_UNKNOWN,
    }
)

logger = logging.getLogger("src.worker.engine.router")


# ── Private helpers ───────────────────────────────────────────────────────────


class _ProcSortHelper:
    """Inline (no-LLM) translator for PROC SORT blocks.

    Emits a single ``.sort_values(...)`` call with provenance comment.
    """

    def _parse_by_clause(self, raw_sas: str) -> tuple[list[str], list[bool]]:
        """Extract variable names and ascending flags from a BY clause.

        Parses the text between ``BY`` and the end of the clause (either a
        semicolon or end-of-string), honouring ``DESCENDING`` prefixes.

        Args:
            raw_sas: Raw SAS source for the PROC SORT block.

        Returns:
            A 2-tuple of (variable_names, ascending_flags).
        """
        by_match = re.search(r"\bBY\b(.*?)(?:;|$)", raw_sas, re.IGNORECASE | re.DOTALL)
        vars_: list[str] = []
        ascending: list[bool] = []

        if not by_match:
            return vars_, ascending

        clause = by_match.group(1).strip()
        tokens = clause.split()
        descending_next = False

        for token in tokens:
            if token.upper() == "DESCENDING":
                descending_next = True
            elif token.upper() == "ASCENDING":
                descending_next = False
            else:
                vars_.append(token)
                ascending.append(not descending_next)
                descending_next = False

        return vars_, ascending

    def _parse_out_dataset(self, raw_sas: str, input_datasets: list[str]) -> tuple[str, str]:
        """Determine the output and input dataset names for the sort.

        Args:
            raw_sas: Raw SAS source for the PROC SORT block.
            input_datasets: Dataset names declared on the block.

        Returns:
            A 2-tuple of (out_dataset, in_dataset).
        """
        out_match = re.search(r"\bOUT\s*=\s*(\w+)", raw_sas, re.IGNORECASE)
        in_dataset = input_datasets[0] if input_datasets else "df"

        out_dataset = out_match.group(1) if out_match else in_dataset

        return out_dataset, in_dataset

    async def translate(self, block: SASBlock, context: JobContext) -> GeneratedBlock:
        """Translate a PROC SORT block to a ``.sort_values(...)`` expression.

        Args:
            block: The PROC SORT SAS block.
            context: The current job context (macro vars, dependency order, etc.).

        Returns:
            A GeneratedBlock with inline sort code and ``is_untranslatable=False``.
        """
        vars_, ascending = self._parse_by_clause(block.raw_sas)
        out_dataset, in_dataset = self._parse_out_dataset(block.raw_sas, block.input_datasets)

        vars_repr = ", ".join(f'"{v}"' for v in vars_)
        ascending_repr = ", ".join(str(a) for a in ascending)

        python_code = (
            f"# SAS: {block.source_file}:{block.start_line}\n"
            f"{out_dataset} = {in_dataset}.sort_values("
            f"by=[{vars_repr}], ascending=[{ascending_repr}])"
        )

        return GeneratedBlock(
            source_block=block,
            python_code=python_code,
            is_untranslatable=False,
        )


class _SimpleCopyHelper:
    """Inline (no-LLM) translator for DATA steps that are pure SET+KEEP/DROP.

    Handles DATA steps containing only SET and optionally KEEP or DROP statements.
    Blocks containing IF, DO, MERGE, RETAIN, ARRAY, or OUTPUT are excluded and
    routed to the full DataStepAgent instead.
    """

    # Patterns that indicate the block requires full LLM translation
    _COMPLEX_PATTERNS: tuple[str, ...] = (
        "IF ",
        "DO ",
        "DO;",
        "MERGE ",
        "RETAIN ",
        "ARRAY ",
        "OUTPUT;",
    )

    @classmethod
    def is_simple(cls, block: SASBlock) -> bool:  # SAS: src/worker/engine/router.py:111
        """Return True when *block* is a pure SET+KEEP/DROP DATA step.

        Args:
            block: The SAS block to inspect.

        Returns:
            True if the block can be handled without LLM translation.
        """
        raw_upper = block.raw_sas.upper()
        return not any(pat in raw_upper for pat in cls._COMPLEX_PATTERNS)

    # SAS: src/worker/engine/router.py:127
    async def translate(self, block: SASBlock, context: JobContext) -> GeneratedBlock:
        """Translate a simple DATA step to a pandas copy/filter expression.

        Args:
            block: A DATA step SAS block with only SET and optional KEEP/DROP.
            context: The current job context.

        Returns:
            A GeneratedBlock with inline pandas code and confidence ``"high"``.
        """
        raw = block.raw_sas.upper()

        data_match = re.search(r"DATA\s+([\w.]+)\s*;", raw)
        set_match = re.search(r"SET\s+([\w.]+)\s*;", raw)
        keep_match = re.search(r"KEEP\s+([\w\s]+)\s*;", raw)
        drop_match = re.search(r"DROP\s+([\w\s]+)\s*;", raw)

        out_ds = data_match.group(1).lower().replace(".", "_") if data_match else "output"
        in_ds = set_match.group(1).lower().replace(".", "_") if set_match else "input"

        if keep_match:
            cols = [c.lower() for c in keep_match.group(1).split()]
            code = (
                f"{out_ds} = {in_ds}[{cols}].copy()  # SAS: {block.source_file}:{block.start_line}"
            )
        elif drop_match:
            cols = [c.lower() for c in drop_match.group(1).split()]
            code = (
                f"{out_ds} = {in_ds}.drop(columns={cols}).copy()"
                f"  # SAS: {block.source_file}:{block.start_line}"
            )
        else:
            code = f"{out_ds} = {in_ds}.copy()  # SAS: {block.source_file}:{block.start_line}"

        return GeneratedBlock(source_block=block, python_code=code, confidence="high")


# ── Router ────────────────────────────────────────────────────────────────────


class _StrategyStubAdapter:
    """Wraps StubGenerator to forward a fixed strategy string into generate().

    Args:
        stub_generator: The shared StubGenerator instance.
        strategy: The strategy string to pass when generating the stub.
    """

    def __init__(self, stub_generator: StubGenerator, strategy: str) -> None:
        """Initialise with a StubGenerator and a fixed strategy."""
        self._stub = stub_generator
        self._strategy = strategy

    async def translate(self, block: SASBlock, context: JobContext) -> GeneratedBlock:
        """Delegate to StubGenerator.generate() with the bound strategy.

        Args:
            block: The SAS block to translate.
            context: The current job context; ``data_files`` is forwarded to the stub.

        Returns:
            A GeneratedBlock produced by the StubGenerator.
        """
        return self._stub.generate(
            block, strategy=self._strategy, data_files=context.data_files or None
        )


class TranslationRouter:
    """Routes a SASBlock to the appropriate translator.

    Translator instances are injected via the constructor so that agents that
    do not yet exist can be supplied as mocks during testing, and so that
    circular imports are avoided.

    Args:
        data_step_agent: Translator for DATA_STEP blocks.
        proc_agent: Translator for PROC_SQL blocks.
        stub_generator: Translator for UNTRANSLATABLE blocks.
        generic_proc_agent: Translator for all other PROC_* block types.
    """

    def __init__(
        self,
        data_step_agent: Any,
        proc_agent: Any,
        stub_generator: StubGenerator,
        generic_proc_agent: Any | None = None,
    ) -> None:
        """Initialise the router with pre-constructed translator instances."""
        self._data_step_agent = data_step_agent
        self._proc_agent = proc_agent
        self._stub_generator = stub_generator
        self._generic_proc_agent = generic_proc_agent
        self._sort_helper = _ProcSortHelper()
        self._simple_copy = _SimpleCopyHelper()

    def route(self, block: SASBlock, block_plan: BlockPlan | None = None) -> Any:
        """Return the translator responsible for *block*.

        When a *block_plan* is provided, strategy-based overrides are applied
        before falling through to the block_type dispatch:
        - ``manual`` / ``manual_ingestion`` → stub generator (human must write code)
        - ``skip`` → stub generator (block is intentionally omitted)
        - all other strategies → normal block_type routing

        Args:
            block: The SAS block to route.
            block_plan: Optional per-block plan from the MigrationPlan. When
                present the plan strategy may override block-type routing.

        Returns:
            The translator instance that should handle the block.

        Raises:
            ValueError: When block.block_type is not a recognised BlockType value.
        """
        if block_plan is not None:
            match block_plan.strategy:
                case TranslationStrategy.MANUAL_INGESTION:
                    return _StrategyStubAdapter(self._stub_generator, "manual_ingestion")
                case TranslationStrategy.MANUAL:
                    return self._stub_generator
                case TranslationStrategy.SKIP:
                    return self._stub_generator
                case _:
                    pass  # translate / translate_with_review fall through

        match block.block_type:
            case BlockType.DATA_STEP:
                if _SimpleCopyHelper.is_simple(block):
                    return self._simple_copy
                return self._data_step_agent
            case BlockType.PROC_SQL:
                return self._proc_agent
            case BlockType.PROC_SORT:
                return self._sort_helper
            case BlockType.UNTRANSLATABLE:
                return self._stub_generator
            case _ if block.block_type in _GENERIC_PROC_TYPES:
                if self._generic_proc_agent is not None:
                    return self._generic_proc_agent
                # Fallback: stub (only if GenericProcAgent was not injected)
                return self._stub_generator
            case _:
                # Unknown future block types → generic proc agent or stub
                if self._generic_proc_agent is not None:
                    return self._generic_proc_agent
                return self._stub_generator
