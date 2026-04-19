"""StubGenerator — emits placeholder Python for untranslatable SAS blocks."""

from src.worker.engine.models import GeneratedBlock, JobContext, SASBlock


class StubGenerator:
    """Generates stub Python comments for SAS constructs that cannot be translated.

    The generated stub is a 3-line comment block that flags the block for manual
    review. It does not produce any executable Python code.
    """

    def generate(self, block: SASBlock) -> GeneratedBlock:
        """Return a stub GeneratedBlock for an untranslatable SAS block.

        Args:
            block: The untranslatable SAS block.

        Returns:
            A GeneratedBlock containing a 3-line comment stub with
            ``is_untranslatable=True``.
        """
        reason = block.untranslatable_reason or "unsupported construct"
        python_code = (
            f"# SAS-UNTRANSLATABLE: {reason}\n"
            "# TODO: manual review required\n"
            f"# SAS: {block.source_file}:{block.start_line}"
        )
        return GeneratedBlock(
            source_block=block,
            python_code=python_code,
            is_untranslatable=True,
        )

    async def translate(self, block: SASBlock, context: JobContext) -> GeneratedBlock:
        """Async translate interface for uniform use by the router caller.

        Args:
            block: The untranslatable SAS block.
            context: The current job context (unused, present for interface parity).

        Returns:
            The result of :meth:`generate`.
        """
        return self.generate(block)
