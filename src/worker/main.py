"""Worker service — async poll loop for migration jobs."""

import asyncio
import json
import logging
import sys
from typing import Any

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.backend.db.models import Job
from src.worker.compute.factory import BackendFactory
from src.worker.core.config import worker_settings
from src.worker.engine.agents.analysis import AnalysisAgent
from src.worker.engine.agents.data_step import DataStepAgent
from src.worker.engine.agents.documentation import DocumentationAgent
from src.worker.engine.agents.failure_interpreter import FailureInterpreterAgent
from src.worker.engine.agents.lineage_enricher import LineageEnricherAgent
from src.worker.engine.agents.migration_planner import MigrationPlannerAgent
from src.worker.engine.agents.proc import ProcAgent
from src.worker.engine.codegen import CodeGenerator
from src.worker.engine.doc_generator import DocGenerator
from src.worker.engine.llm_client import LLMClient, LLMTranslationError
from src.worker.engine.macro_expander import CannotExpandError, MacroExpander
from src.worker.engine.models import GeneratedBlock, JobContext, ReconciliationReport, SASBlock
from src.worker.engine.parser import SASParser, extract_lineage
from src.worker.engine.router import TranslationRouter
from src.worker.engine.stub_generator import StubGenerator
from src.worker.validation.reconciliation import ReconciliationService

logging.basicConfig(
    level=getattr(logging, worker_settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


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

        # Step 3: Analyse
        context = await self._analysis_agent.analyse(files, parse_result.macro_vars, blocks)
        context = context.model_copy(update={"blocks": expanded_blocks})
        if expansion_warnings:
            context = context.model_copy(
                update={"risk_flags": context.risk_flags + expansion_warnings}
            )

        # Step 3.5: Migration planning (best-effort)
        try:
            plan = await self._migration_planner.plan(context)
            context = context.model_copy(update={"migration_plan": plan})
        except Exception as exc:
            logger.warning("Job %s: migration planning failed, continuing: %s", job.id, exc)

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
        try:
            doc = await self._doc_agent.generate(context, python_code, recon_summary)
        except Exception as exc:
            logger.warning("Job %s: doc generation failed: %s", job.id, exc)

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

        generated: list[GeneratedBlock] = []
        for block in blocks:
            translator = self._router.route(block)
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
                translator = self._router.route(block)
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
