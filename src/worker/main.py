"""Worker service — async poll loop for migration jobs."""

import asyncio
import json
import logging
import re
import sys
import uuid as _uuid
from typing import Any

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.backend.db.models import BlockRevision, Job, JobVersion
from src.worker.compute.factory import BackendFactory
from src.worker.core.config import worker_settings
from src.worker.engine.agents.analysis import AnalysisAgent
from src.worker.engine.agents.data_step import DataStepAgent
from src.worker.engine.agents.documentation import DocumentationAgent
from src.worker.engine.agents.failure_interpreter import FailureInterpreterAgent
from src.worker.engine.agents.lineage_enricher import LineageEnricherAgent
from src.worker.engine.agents.migration_planner import MigrationPlannerAgent
from src.worker.engine.agents.plain_english import PlainEnglishAgent
from src.worker.engine.agents.proc import ProcAgent
from src.worker.engine.codegen import CodeGenerator
from src.worker.engine.doc_generator import DocGenerator
from src.worker.engine.llm_client import LLMClient, LLMTranslationError
from src.worker.engine.macro_expander import CannotExpandError, MacroExpander
from src.worker.engine.models import (
    BlockPlan,
    DataFileInfo,
    GeneratedBlock,
    JobContext,
    ReconciliationReport,
    SASBlock,
)
from src.worker.engine.parser import SASParser, extract_lineage
from src.worker.engine.router import TranslationRouter
from src.worker.engine.stub_generator import StubGenerator
from src.worker.validation.reconciliation import ReconciliationService, RemoteReconciliationService

logging.basicConfig(
    level=getattr(logging, worker_settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def _sniff_file(disk_path: str, ext: str) -> tuple[list[str], int | None]:
    """Sniff column headers and row count from a data file.

    Supports ``.csv``, ``.tsv``, ``.xlsx``/``.xls``, and ``.sas7bdat``.
    Any read error returns ``([], None)`` — this function is always non-blocking.

    Args:
        disk_path: Absolute path to the data file on disk.
        ext: File extension including the dot (e.g. ``".csv"``).

    Returns:
        A 2-tuple of ``(columns, row_count)``. ``columns`` is an empty list and
        ``row_count`` is ``None`` when the file cannot be read.
    """
    import pandas as pd  # local import — pandas may not be installed in all envs

    try:
        if ext in (".csv", ".tsv"):
            sep = "\t" if ext == ".tsv" else ","
            header_df = pd.read_csv(disk_path, nrows=0, sep=sep)
            columns = list(header_df.columns)
            full_df = pd.read_csv(disk_path, sep=sep)
            return columns, len(full_df)
        if ext in (".xlsx", ".xls"):
            header_df = pd.read_excel(disk_path, nrows=0)
            columns = list(header_df.columns)
            full_df = pd.read_excel(disk_path)
            return columns, len(full_df)
        if ext == ".sas7bdat":
            try:
                import pyreadstat

                _df, meta = pyreadstat.read_sas7bdat(disk_path, row_limit=0)
                columns = list(meta.column_names)
                return columns, None
            except ImportError:
                return [], None
    except Exception:
        pass
    return [], None


def _make_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create an async SQLAlchemy session factory from settings."""
    engine = create_async_engine(worker_settings.database_url, pool_pre_ping=True)
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def _claim_job(session: AsyncSession) -> Job | None:
    """Atomically claim one queued job by setting status=running.

    Returns:
        The claimed Job, or None if the queue is empty.
    """
    result = await session.execute(
        select(Job).where(Job.status == "queued").limit(1).with_for_update(skip_locked=True)
    )
    job: Job | None = result.scalar_one_or_none()
    if job is None:
        return None

    await session.execute(update(Job).where(Job.id == job.id).values(status="running"))
    await session.commit()
    await session.refresh(job)
    return job


def _inject_data_file_nodes(
    lineage_data: dict[str, Any],
    blocks: list[SASBlock],
    context: "JobContext",
) -> dict[str, Any]:
    """Append data-file nodes and edges to an existing lineage dict.

    For each file in context.data_files, creates a node of type DATA_FILE.
    Then links it to any block whose input_datasets or output_datasets reference
    a libname alias that resolves to that file path.
    """
    extra_nodes: list[dict[str, Any]] = []
    extra_edges: list[dict[str, Any]] = []

    # Build reverse map: norm_path → file info
    for norm_path, info in context.data_files.items():
        file_node_id = f"__data_file__{norm_path}"
        filename = norm_path.split("/")[-1]
        extra_nodes.append(
            {
                "id": file_node_id,
                "label": filename,
                "node_type": "DATA_FILE",
                "path": norm_path,
                "disk_path": info.disk_path,
                "extension": info.extension,
                "columns": info.columns,
                "row_count": info.row_count,
            }
        )

        # Match blocks that reference this file via libname or filename alias
        for block in blocks:
            block_node_id = f"{block.source_file}::{block.start_line}"
            matched_input = _dataset_matches_file(block.input_datasets, norm_path, context)
            matched_output = _dataset_matches_file(block.output_datasets, norm_path, context)
            if matched_input:
                extra_edges.append(
                    {
                        "source": file_node_id,
                        "target": block_node_id,
                        "dataset": norm_path,
                        "inferred": True,
                    }
                )
            if matched_output:
                extra_edges.append(
                    {
                        "source": block_node_id,
                        "target": file_node_id,
                        "dataset": norm_path,
                        "inferred": True,
                    }
                )

    nodes = list(lineage_data.get("nodes", [])) + extra_nodes
    edges = list(lineage_data.get("edges", [])) + extra_edges
    return {**lineage_data, "nodes": nodes, "edges": edges}


def _dataset_matches_file(
    datasets: list[str],
    norm_path: str,
    context: "JobContext",
) -> bool:
    """Return True if any dataset name resolves to norm_path via libname_map."""
    filename_stem = norm_path.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
    for ds in datasets:
        ds_lower = ds.lower()
        # Direct stem match (e.g. "customers" matches "data/raw/customers.csv")
        ds_stem = ds_lower.split(".")[-1]
        if ds_stem == filename_stem:
            return True
        # Libname resolution: "rawdir.customers" → look up rawdir in libname_map
        if "." in ds_lower:
            lib, table = ds_lower.split(".", 1)
            folder = context.libname_map.get(lib, "")
            if folder and norm_path.startswith(folder) and table == filename_stem:
                return True
        # Filename alias match from libname_map
        alias_path = context.libname_map.get(ds_lower, "")
        if alias_path and alias_path == norm_path:
            return True
    return False


class JobOrchestrator:
    """Runs the full agentic migration pipeline for a single job."""

    def __init__(self) -> None:
        """Initialise all pipeline components."""
        self._analysis_agent = AnalysisAgent()
        stub = StubGenerator()
        self._router = TranslationRouter(
            data_step_agent=DataStepAgent(),
            proc_agent=ProcAgent(),
            stub_generator=stub,
        )
        self._codegen = CodeGenerator()
        self._reconciler = ReconciliationService()
        self._failure_interpreter = FailureInterpreterAgent()
        self._doc_agent = DocumentationAgent()
        self._plain_english_agent = PlainEnglishAgent()
        self._expander = MacroExpander()
        self._migration_planner = MigrationPlannerAgent()
        self._lineage_enricher = LineageEnricherAgent()

    async def run(self, session: AsyncSession, job: Job) -> None:
        """Execute the full pipeline and persist results.

        Args:
            session: Database session for status updates.
            job: The claimed job to process.
        """
        logger.info("Processing job %s (agentic pipeline)", job.id)
        try:
            await self._execute(session, job)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                logger.warning("Job %s: circuit breaker tripped (HTTP 429)", job.id)
                await session.execute(
                    update(Job)
                    .where(Job.id == job.id)
                    .values(
                        status="failed",
                        error="circuit_breaker_tripped",
                        error_detail={"error": "circuit_breaker_tripped"},
                    )
                )
                await session.commit()
            else:
                raise
        except Exception as exc:
            logger.warning("Job %s failed: %s", job.id, exc)
            await session.execute(
                update(Job).where(Job.id == job.id).values(status="failed", error=str(exc))
            )
            await session.commit()

    async def _execute(self, session: AsyncSession, job: Job) -> None:
        """Inner pipeline — raises on unhandled errors."""
        files: dict[str, str] = {
            k: v
            for k, v in job.files.items()
            if k not in ("__ref_csv__", "__ref_sas7bdat__", "__refine_context__")
        }
        ref_csv_path: str = str(job.files.get("__ref_csv__", ""))
        ref_sas7bdat_path: str = str(job.files.get("__ref_sas7bdat__", ""))

        # Refine context — injected by POST /jobs/{id}/refine
        refine_context_raw = job.files.get("__refine_context__")
        refine_context: dict[str, Any] | None = None
        if refine_context_raw:
            import contextlib

            with contextlib.suppress(json.JSONDecodeError, TypeError):
                refine_context = json.loads(refine_context_raw)

        # Build data-file catalogue from __ref_* sentinel keys
        data_files: dict[str, DataFileInfo] = {}
        for key, disk_path in job.files.items():
            if not key.startswith("__ref_") or not key.endswith("__"):
                continue
            # key format: __ref_{ext}_{normalized_path}__
            inner = key[len("__ref_") : -2]  # e.g. "csv_data/raw/customers.csv"
            sep_idx = inner.find("_")
            if sep_idx == -1:
                continue
            file_ext = "." + inner[:sep_idx]
            norm_path = inner[sep_idx + 1 :]
            if not norm_path:
                continue
            columns, row_count = _sniff_file(disk_path, file_ext)
            data_files[norm_path] = DataFileInfo(
                path=norm_path,
                disk_path=disk_path,
                extension=file_ext,
                columns=columns,
                row_count=row_count,
            )

        if job.skip_llm:
            await self._execute_rereconcile(job, session, ref_csv_path, ref_sas7bdat_path)
            return

        # Step 1: Parse
        parse_result = SASParser().parse(files)
        blocks = parse_result.blocks

        # Step 2: Macro expand (per-block, soft-fail on CannotExpandError)
        expansion_warnings: list[str] = []
        expanded_blocks: list[SASBlock] = []
        for block in blocks:
            try:
                (expanded,) = self._expander.expand([block], parse_result.macro_vars)
                expanded_blocks.append(expanded)
            except CannotExpandError as exc:
                logger.warning("Job %s: macro expansion skipped for block: %s", job.id, exc)
                expansion_warnings.append(str(exc))
                expanded_blocks.append(block)

        # Build libname/filename alias map by grepping all SAS source file contents
        libname_map: dict[str, str] = {}
        _libname_re = re.compile(
            r'\b(?:libname|filename)\s+(\w+)\s+"([^"]+)"',
            re.IGNORECASE,
        )
        for _src_content in files.values():
            for _alias, _path in _libname_re.findall(_src_content):
                libname_map[_alias.lower()] = _path

        # Step 3: Analyse
        context = await self._analysis_agent.analyse(files, parse_result.macro_vars, blocks)
        context = context.model_copy(
            update={
                "blocks": expanded_blocks,
                "data_files": data_files,
                "libname_map": libname_map,
            }
        )
        if expansion_warnings:
            context = context.model_copy(
                update={"risk_flags": context.risk_flags + expansion_warnings}
            )

        # Step 3.5: Migration planning (best-effort with fallback)
        try:
            plan = await self._migration_planner.plan(context)
            context = context.model_copy(update={"migration_plan": plan})
        except Exception as exc:
            logger.error("Job %s: migration planning failed: %s", job.id, exc)
            raise RuntimeError(f"Migration planning failed: {exc}") from exc

        # Steps 4-7: Translate + two-phase refinement
        prior_python_code: str | None = None
        hint: str | None = None
        if refine_context:
            prior_python_code = refine_context.get("prior_python_code") or None
            hint = refine_context.get("hint") or None

        generated = await self._translate_two_phase(
            expanded_blocks,
            context,
            ref_csv_path,
            ref_sas7bdat_path,
            prior_python_code=prior_python_code,
            hint=hint,
        )

        # Step 5: Assemble — dict form for generated_files, flat str for python_code column
        generated_files: dict[str, str] = self._codegen.assemble(
            generated, macro_vars=parse_result.macro_vars
        )
        python_code: str = self._codegen.assemble_flat(
            generated, macro_vars=parse_result.macro_vars
        )

        # Step 6: Final reconciliation
        backend = BackendFactory.create()
        report = await asyncio.to_thread(
            self._reconciler.run,
            ref_csv_path,
            python_code,
            backend,
            ref_sas7bdat_path,
        )

        # Step 7.5: Lineage enrichment (best-effort)
        try:
            enriched = await self._lineage_enricher.enrich(context)
            context = context.model_copy(update={"enriched_lineage": enriched})
        except Exception as exc:
            logger.warning("Job %s: lineage enrichment failed, continuing: %s", job.id, exc)

        # Step 8: Documentation
        recon_summary = _recon_summary(report)
        doc: str | None = None
        doc_result, plain_english = await asyncio.gather(
            self._doc_agent.generate(context, python_code, recon_summary or ""),
            self._plain_english_agent.generate(context, python_code, recon_summary or ""),
            return_exceptions=True,
        )
        if isinstance(doc_result, str):
            doc = doc_result
        else:
            logger.warning("Job %s: doc generation failed: %s", job.id, doc_result)
        plain_english_text: str | None = (
            plain_english
            if isinstance(plain_english, str)
            else (context.migration_plan.summary if context.migration_plan else None)
        )
        if not isinstance(plain_english, str):
            logger.warning("Job %s: plain-English generation failed: %s", job.id, plain_english)
        if plain_english_text:
            report = {**(report or {}), "non_technical_doc": plain_english_text}

        # Step 9: Lineage extraction + merge enriched fields (best-effort)
        lineage_data = None
        try:
            lineage_data = extract_lineage(blocks, str(job.id))
        except Exception as exc:
            logger.warning("Job %s: lineage extraction failed: %s", job.id, exc)

        # Merge enriched lineage fields into lineage_data dict when available
        if context.enriched_lineage is not None and lineage_data is not None:
            lineage_data = {**lineage_data, **context.enriched_lineage.model_dump()}
        elif context.enriched_lineage is not None:
            lineage_data = context.enriched_lineage.model_dump()

        # Inject data-file nodes + edges from the data_files catalogue
        if lineage_data is not None and context.data_files:
            lineage_data = _inject_data_file_nodes(lineage_data, blocks, context)

        # Step 10: Persist
        await session.execute(
            update(Job)
            .where(Job.id == job.id)
            .values(
                status="proposed",
                python_code=python_code,
                generated_files=generated_files,
                migration_plan=(
                    context.migration_plan.model_dump() if context.migration_plan else None
                ),
                report=report,
                llm_model=worker_settings.llm_model,
                lineage=lineage_data,
                doc=doc,
            )
        )
        await session.commit()
        logger.info("Job %s completed successfully", job.id)

        # Auto-save initial v1 for every tab so the rail shows the agent-generated baseline.
        plan_overrides = (
            context.migration_plan.model_dump().get("block_overrides", [])
            if context.migration_plan
            else []
        )
        initial_versions = [
            JobVersion(
                id=str(_uuid.uuid4()),
                job_id=str(job.id),
                tab="editor",
                content={"python_code": python_code, "generated_files": generated_files},
                trigger="agent",
            ),
            JobVersion(
                id=str(_uuid.uuid4()),
                job_id=str(job.id),
                tab="report",
                content={"doc": doc or ""},
                trigger="agent",
            ),
            JobVersion(
                id=str(_uuid.uuid4()),
                job_id=str(job.id),
                tab="plan",
                content={"block_overrides": plan_overrides},
                trigger="agent",
            ),
        ]
        for v in initial_versions:
            session.add(v)
        await session.commit()

        # Step 11: Initial per-block reconciliation via remote executor (best-effort)
        if context.migration_plan and (ref_csv_path or ref_sas7bdat_path):
            await self._reconcile_initial_blocks(
                session,
                job,
                context,
                ref_csv_path,
                ref_sas7bdat_path,
            )

    async def _reconcile_initial_blocks(
        self,
        session: AsyncSession,
        job: Job,
        context: JobContext,
        ref_csv_path: str,
        ref_sas7bdat_path: str,
    ) -> None:
        """Run RemoteReconciliationService for each eligible block and persist status.

        Skips blocks with strategy ``manual``, ``manual_ingestion``, or ``skip``.
        Skips entirely when no reference data paths are available.
        Writes ``reconciliation_status`` to the block's initial BlockRevision row.

        Args:
            session: Active database session.
            job: The job whose blocks should be reconciled.
            context: JobContext holding the migration plan.
            ref_csv_path: Path to reference CSV (may be empty string).
            ref_sas7bdat_path: Path to reference .sas7bdat (may be empty string).
        """
        skip_strategies = frozenset({"manual", "manual_ingestion", "skip"})
        remote = RemoteReconciliationService()
        backend = BackendFactory.create()

        block_plans = (
            context.migration_plan.model_dump().get("block_plans", [])
            if context.migration_plan
            else []
        )

        for bp in block_plans:
            block_id: str = bp.get("block_id", "")
            strategy: str = bp.get("strategy", "translate")
            if strategy in skip_strategies:
                continue

            # Fetch the initial (first) BlockRevision for this block
            rev_result = await session.execute(
                select(BlockRevision)
                .where(BlockRevision.job_id == str(job.id), BlockRevision.block_id == block_id)
                .order_by(BlockRevision.revision_number.asc())
                .limit(1)
            )
            initial_rev = rev_result.scalar_one_or_none()
            if initial_rev is None or not initial_rev.python_code:
                continue

            try:
                report = await remote.run(
                    ref_csv_path,
                    initial_rev.python_code,
                    backend,
                    ref_sas7bdat_path,
                )
                checks: list[dict[str, Any]] = report.get("checks", [])
                if not checks:
                    continue
                all_passed = all(c.get("status") == "pass" for c in checks)
                recon_status = "pass" if all_passed else "fail"
                await session.execute(
                    update(BlockRevision)
                    .where(BlockRevision.id == initial_rev.id)
                    .values(reconciliation_status=recon_status)
                )
                await session.commit()
            except Exception as exc:
                logger.warning("Job %s: block recon failed for %s: %s", job.id, block_id, exc)

    async def _translate_two_phase(
        self,
        blocks: list[SASBlock],
        context: JobContext,
        ref_csv_path: str,
        ref_sas7bdat_path: str,
        *,
        prior_python_code: str | None = None,
        hint: str | None = None,
    ) -> list[GeneratedBlock]:
        """Translate blocks using an explicit two-phase sequence.

        Phase 1: translate all blocks, reconcile. Return immediately if passed.
        Phase 2 (only on failure): FailureInterpreterAgent identifies the affected
        block, re-translates it, then reconciles once more (final regardless of result).

        Args:
            blocks: Expanded SAS blocks to translate.
            context: Current job context.
            ref_csv_path: Path to reference CSV for reconciliation.
            ref_sas7bdat_path: Path to reference SAS7BDAT (optional).
            prior_python_code: Previous translation to improve (from refine context).
            hint: Reviewer hint to prepend to the LLM prompt (from refine context).

        Returns:
            Final list of GeneratedBlock instances.
        """
        # Phase 1 — translate all blocks then reconcile
        generated_v1 = await self._translate_blocks(blocks, context, prior_python_code, hint)
        python_code_v1 = self._codegen.assemble_flat(
            generated_v1, macro_vars=context.resolved_macros
        )
        backend = BackendFactory.create()
        raw_report_v1 = await asyncio.to_thread(
            self._reconciler.run,
            ref_csv_path,
            python_code_v1,
            backend,
            ref_sas7bdat_path,
        )
        report_v1 = (
            _dict_to_recon_report(raw_report_v1)
            if isinstance(raw_report_v1, dict)
            else raw_report_v1
        )
        if report_v1.passed or not report_v1.diff_summary:
            return generated_v1

        # Phase 2 — interpret failure and re-translate the affected block only
        try:
            retry_hint, affected_id = await self._failure_interpreter.interpret(
                report_v1.diff_summary, python_code_v1, context
            )
        except Exception as exc:
            logger.warning("FailureInterpreterAgent failed, skipping phase 2: %s", exc)
            return generated_v1

        generated_v2 = await self._retry_affected_block(
            blocks, generated_v1, context, affected_id, retry_hint
        )
        context = context.model_copy(update={"retry_count": context.retry_count + 1})
        return generated_v2

    async def _translate_blocks(
        self,
        blocks: list[SASBlock],
        context: JobContext,
        prior_python_code: str | None = None,
        hint: str | None = None,
    ) -> list[GeneratedBlock]:
        """Translate every block via the TranslationRouter."""
        effective_context = context
        extra_flags: list[str] = []
        if prior_python_code:
            extra_flags.append(f"prior_translation:\n```python\n{prior_python_code}\n```")
        if hint:
            extra_flags.append(f"reviewer_hint: {hint}")
        if extra_flags:
            effective_context = context.model_copy(
                update={"risk_flags": context.risk_flags + extra_flags}
            )

        block_plan_map: dict[str, BlockPlan] = {}
        if context.migration_plan:
            for bp in context.migration_plan.block_plans:
                block_plan_map[bp.block_id] = bp

        generated: list[GeneratedBlock] = []
        for block in blocks:
            block_id = f"{block.source_file}:{block.start_line}"
            block_plan = block_plan_map.get(block_id)
            translator = self._router.route(block, block_plan=block_plan)
            gb = await translator.translate(block, effective_context)
            generated.append(gb)
        return generated

    async def _retry_affected_block(
        self,
        blocks: list[SASBlock],
        generated: list[GeneratedBlock],
        context: JobContext,
        affected_id: str,
        retry_hint: str,
    ) -> list[GeneratedBlock]:
        """Re-translate the block identified by affected_id using the retry hint.

        Args:
            blocks: Original SAS blocks.
            generated: Current generated blocks.
            context: Current job context.
            affected_id: Block ID in "source_file:start_line" format.
            retry_hint: Hint from FailureInterpreterAgent.

        Returns:
            Updated generated blocks list with the affected block replaced.
        """
        updated = list(generated)
        for i, (block, _gb) in enumerate(zip(blocks, generated, strict=False)):
            block_id = f"{block.source_file}:{block.start_line}"
            if block_id != affected_id:
                continue
            hint_context = context.model_copy(
                update={"risk_flags": [*context.risk_flags, f"retry_hint: {retry_hint}"]}
            )
            try:
                bp = (
                    next(
                        (p for p in context.migration_plan.block_plans if p.block_id == block_id),
                        None,
                    )
                    if context.migration_plan
                    else None
                )
                translator = self._router.route(block, block_plan=bp)
                new_gb = await translator.translate(block, hint_context)
                updated[i] = new_gb
                logger.info("Retried block %s with hint", affected_id)
            except Exception as exc:
                logger.warning("Retry for block %s failed: %s", affected_id, exc)
            break
        return updated

    async def _execute_rereconcile(
        self,
        job: Job,
        session: AsyncSession,
        ref_csv_path: str,
        ref_sas7bdat_path: str,
    ) -> None:
        """Re-run only reconciliation against the existing python_code (no LLM).

        Used when ``job.skip_llm=True`` (triggered by PUT /jobs/{id}/python_code).

        Args:
            job: The job with manually updated Python code.
            session: Database session for persisting results.
            ref_csv_path: Path to reference CSV (may be empty string).
            ref_sas7bdat_path: Path to reference SAS7BDAT (may be empty string).
        """
        try:
            backend = BackendFactory.create()
            report = await asyncio.to_thread(
                self._reconciler.run,
                ref_csv_path,
                job.python_code or "",
                backend,
                ref_sas7bdat_path,
            )
            await session.execute(
                update(Job)
                .where(Job.id == job.id)
                .values(status="proposed", report=report, skip_llm=False)
            )
            await session.commit()
            logger.info("Job %s re-reconciliation complete", job.id)
        except Exception as exc:
            logger.warning("Job %s re-reconciliation failed: %s", job.id, exc)
            await session.execute(
                update(Job).where(Job.id == job.id).values(status="failed", error=str(exc))
            )
            await session.commit()
            raise


def _dict_to_recon_report(report: dict[str, Any]) -> ReconciliationReport:
    """Convert a ReconciliationService dict result to a ReconciliationReport model.

    Args:
        report: Dict with ``{"checks": [{"name", "status", "detail?"}]}`` structure.

    Returns:
        A ReconciliationReport with aggregated pass/fail fields.
    """
    checks: list[dict[str, Any]] = report.get("checks", [])
    # No checks run = no reference data supplied → treat as passed (skip reconciliation)
    if not checks:
        return ReconciliationReport(
            passed=True, row_count_match=True, column_match=True, diff_summary="no checks run"
        )
    passed_checks = [c for c in checks if c.get("status") == "pass"]
    failed_checks = [c for c in checks if c.get("status") != "pass"]
    all_passed = len(failed_checks) == 0
    row_ok = any(c.get("name") == "row_count" and c.get("status") == "pass" for c in checks)
    col_ok = any(c.get("name") == "columns" and c.get("status") == "pass" for c in checks)
    details = "; ".join(c.get("detail", "") for c in failed_checks if c.get("detail"))
    diff = details or (
        f"{len(passed_checks)}/{len(checks)} checks passed" if checks else "no checks run"
    )
    return ReconciliationReport(
        passed=all_passed,
        row_count_match=row_ok,
        column_match=col_ok,
        diff_summary=diff,
    )


def _recon_summary(report: object) -> str | None:
    """Build a human-readable reconciliation summary string.

    Args:
        report: The reconciliation report dict or ReconciliationReport model.

    Returns:
        A one-line summary string, or None if report is falsy.
    """
    if report is None:
        return None
    if isinstance(report, dict):
        checks = report.get("checks", [])
        passed = sum(1 for c in checks if c.get("status") == "pass")
        return f"{passed}/{len(checks)} checks passed."
    # ReconciliationReport model
    status = "passed" if getattr(report, "passed", False) else "failed"
    return f"Reconciliation {status}. {getattr(report, 'diff_summary', '')}"


async def poll_loop() -> None:
    """Continuously poll for queued jobs and process them."""
    session_factory = _make_session_factory()
    orchestrator = JobOrchestrator()
    logger.info("Worker started — polling every %ds", worker_settings.poll_interval_seconds)

    while True:
        async with session_factory() as session:
            job = await _claim_job(session)
            if job is not None:
                async with session_factory() as proc_session:
                    await orchestrator.run(proc_session, job)
            else:
                logger.debug("No queued jobs")

        await asyncio.sleep(worker_settings.poll_interval_seconds)


async def _process_job(session: AsyncSession, job: Job) -> None:
    """Compatibility shim — delegates to JobOrchestrator.run().

    Kept for existing tests that patch src.worker.main.* module-level symbols.
    New code should use JobOrchestrator directly.

    Args:
        session: Database session for updating job state.
        job: The claimed job to process.
    """
    logger.info("Processing job %s", job.id)
    try:
        files: dict[str, str] = {
            k: v for k, v in job.files.items() if k not in ("__ref_csv__", "__ref_sas7bdat__")
        }
        ref_csv_path: str = str(job.files.get("__ref_csv__", ""))
        ref_sas7bdat_path: str = str(job.files.get("__ref_sas7bdat__", ""))

        result = SASParser().parse(files)
        blocks = result.blocks

        lineage_data: dict | None = None  # type: ignore[type-arg]
        try:
            lineage_data = extract_lineage(blocks, str(job.id))
        except Exception as exc:
            logger.warning("Lineage extraction failed for job %s: %s", job.id, exc)

        client = LLMClient()
        generated: list[GeneratedBlock] = []
        for idx, block in enumerate(blocks):
            try:
                gb = await asyncio.to_thread(client.translate, block)
                generated.append(gb)
            except LLMTranslationError as exc:
                partial_code = (
                    CodeGenerator().assemble_flat(generated, macro_vars=result.macro_vars)
                    if generated
                    else None
                )
                logger.error(
                    "Job %s failed at block %d/%d: %s",
                    job.id,
                    idx,
                    len(blocks),
                    exc,
                    exc_info=True,
                )
                await session.execute(
                    update(Job)
                    .where(Job.id == job.id)
                    .values(
                        status="failed",
                        error=str(exc),
                        error_detail={
                            "stage": "llm_translation",
                            "block_index": idx,
                            "block_count": len(blocks),
                            "is_transient": exc.is_transient,
                            "resumable": exc.is_transient,
                            "exception_type": (
                                type(exc.cause).__name__ if exc.cause else type(exc).__name__
                            ),
                            **({"python_code": partial_code} if partial_code else {}),
                        },
                        python_code=partial_code,
                    )
                )
                await session.commit()
                return

        python_code = CodeGenerator().assemble_flat(generated, macro_vars=result.macro_vars)
        backend = BackendFactory.create()
        reconciler = ReconciliationService()
        report = await asyncio.to_thread(
            reconciler.run,
            ref_csv_path,
            python_code,
            backend,
            ref_sas7bdat_path,
        )

        doc: str | None = None
        try:
            doc = await DocGenerator().generate(job, client)
        except Exception as exc:
            logger.warning("Doc generation failed for job %s: %s", job.id, exc)

        await session.execute(
            update(Job)
            .where(Job.id == job.id)
            .values(
                status="proposed",
                python_code=python_code,
                report=report,
                llm_model=worker_settings.llm_model,
                lineage=lineage_data,
                doc=doc,
            )
        )
        await session.commit()
        logger.info("Job %s completed successfully", job.id)
    except Exception as exc:
        logger.warning("Job %s failed: %s", job.id, exc)
        await session.execute(
            update(Job).where(Job.id == job.id).values(status="failed", error=str(exc))
        )
        await session.commit()


if __name__ == "__main__":
    asyncio.run(poll_loop())
