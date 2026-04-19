"""TranslationRouter — maps SAS BlockType to the correct translator instance."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from src.worker.engine.models import BlockType, GeneratedBlock, JobContext, SASBlock
from src.worker.engine.stub_generator import StubGenerator

if TYPE_CHECKING:
    pass

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


# ── Router ────────────────────────────────────────────────────────────────────


class TranslationRouter:
    """Routes a SASBlock to the appropriate translator.

    Translator instances are injected via the constructor so that agents that
    do not yet exist can be supplied as mocks during testing, and so that
    circular imports are avoided.

    Args:
        data_step_agent: Translator for DATA_STEP blocks.
        proc_agent: Translator for PROC_SQL blocks.
        stub_generator: Translator for UNTRANSLATABLE blocks.
    """

    def __init__(
        self,
        data_step_agent: Any,
        proc_agent: Any,
        stub_generator: StubGenerator,
    ) -> None:
        """Initialise the router with pre-constructed translator instances."""
        self._data_step_agent = data_step_agent
        self._proc_agent = proc_agent
        self._stub_generator = stub_generator
        self._sort_helper = _ProcSortHelper()

    def route(self, block: SASBlock) -> Any:
        """Return the translator responsible for *block*.

        Args:
            block: The SAS block to route.

        Returns:
            The translator instance that should handle the block.

        Raises:
            ValueError: When block.block_type is not a recognised BlockType value.
        """
        match block.block_type:
            case BlockType.DATA_STEP:
                return self._data_step_agent
            case BlockType.PROC_SQL:
                return self._proc_agent
            case BlockType.PROC_SORT:
                return self._sort_helper
            case BlockType.UNTRANSLATABLE:
                return self._stub_generator
            case _:
                raise ValueError(f"Unhandled block type: {block.block_type!r}")
