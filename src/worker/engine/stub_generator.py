"""StubGenerator — emits placeholder Python for untranslatable SAS blocks."""

from src.worker.engine.models import DataFileInfo, GeneratedBlock, JobContext, SASBlock


class StubGenerator:
    """Generates stub Python comments for SAS constructs that cannot be translated.

    The generated stub is a 3-line comment block that flags the block for manual
    review. It does not produce any executable Python code.
    """

    def generate(
        self,
        block: SASBlock,
        strategy: str | None = None,
        data_files: dict[str, DataFileInfo] | None = None,
    ) -> GeneratedBlock:
        """Return a stub GeneratedBlock for an untranslatable SAS block.

        Args:
            block: The untranslatable SAS block.
            strategy: Optional strategy override. When ``"manual_ingestion"``,
                emits a ``pd.read_csv()`` scaffold instead of a comment stub.
            data_files: Optional mapping of normalised relative path → DataFileInfo
                used to resolve the real file path for ``manual_ingestion`` stubs.

        Returns:
            A GeneratedBlock containing either a ``pd.read_csv()`` scaffold
            (for ``manual_ingestion``) or a 3-line comment stub with
            ``is_untranslatable=True``.
        """
        if strategy == "manual_ingestion":
            dataset_name = (
                block.output_datasets[0].lower().replace(".", "_")
                if block.output_datasets
                else "df"
            )
            # Try to resolve real file path from data_files catalogue
            real_path: str | None = None
            disk_path: str | None = None
            col_comment: str = ""
            if data_files:
                candidates = list(block.input_datasets) + list(block.output_datasets)
                for candidate in candidates:
                    norm = candidate.lower().replace(".", "/")
                    for file_path, info in data_files.items():
                        if norm in file_path.lower() or file_path.lower().endswith(norm):
                            real_path = file_path
                            disk_path = info.disk_path
                            if info.columns:
                                col_comment = f"\n# Columns: {', '.join(info.columns)}"
                            break
                    if real_path:
                        break
            # Prefer the normalised relative path key so the generated script is portable;
            # fall back to disk_path if no catalogue match, then a workspace-relative default.
            ingestion_path = real_path or disk_path or f"/workspace/data/{dataset_name}.csv"
            python_code = (
                "import pandas as pd\n\n"
                f"# SAS: {block.source_file}:{block.start_line}\n"
                "# TODO: verify delimiter and encoding\n"
                f'{dataset_name} = pd.read_csv("{ingestion_path}"){col_comment}'
            )
            return GeneratedBlock(
                source_block=block,
                python_code=python_code,
                is_untranslatable=False,
                confidence="medium",
                confidence_score=0.7,
                confidence_band="medium",
            )

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
            confidence="very_low",
            confidence_score=0.0,
            confidence_band="very_low",
        )

    async def translate(
        self, block: SASBlock, context: JobContext, strategy: str | None = None
    ) -> GeneratedBlock:
        """Async translate interface for uniform use by the router caller.

        Args:
            block: The untranslatable SAS block.
            context: The current job context; ``data_files`` is forwarded to generate().
            strategy: Optional strategy override passed through to :meth:`generate`.

        Returns:
            The result of :meth:`generate`.
        """
        return self.generate(block, strategy=strategy, data_files=context.data_files or None)
