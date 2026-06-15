"""Worker service — async poll loop for migration jobs."""

import asyncio
import json
import logging
import re
import sys
import time
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
from src.worker.engine.agents.generic_proc import GenericProcAgent
from src.worker.engine.agents.lineage_enricher import LineageEnricherAgent
from src.worker.engine.agents.migration_planner import MigrationPlannerAgent
from src.worker.engine.agents.plain_english import PlainEnglishAgent
from src.worker.engine.agents.proc import ProcAgent
from src.worker.engine.block_executor import BlockExecutor
from src.worker.engine.codegen import CodeGenerator
from src.worker.engine.dependency_checker import detect_missing_dependencies
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
from src.worker.engine.pii_scanner import scan_for_pii
from src.worker.engine.router import TranslationRouter
from src.worker.engine.stub_generator import StubGenerator
from src.worker.engine.trace import JobCancelledError, TraceEmitter
from src.worker.engine.usage import UsageTracker, activate, set_block_type, set_phase
from src.worker.validation.reconciliation import ReconciliationService, RemoteReconciliationService

logging.basicConfig(
    level=getattr(logging, worker_settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("pydantic_ai").setLevel(logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("openai._base_client").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def _map_readstat_type(rs_type: str) -> str:
    """Map a readstat variable type string to a Spark cast type.

    Args:
        rs_type: The readstat type string from ``meta.readstat_variable_types``.

    Returns:
        ``"string"`` for string columns; ``"double"`` for all numeric/unknown types.
    """
    if rs_type == "string":
        return "string"
    return "double"


def _sniff_file(disk_path: str, ext: str) -> tuple[list[str], int | None, dict[str, str]]:
    """Sniff column headers, row count, and declared types from a data file.

    Supports ``.csv``, ``.tsv``, ``.xlsx``/``.xls``, and ``.sas7bdat``.
    Any read error returns ``([], None, {})`` — this function is always non-blocking.

    Args:
        disk_path: Absolute path to the data file on disk.
        ext: File extension including the dot (e.g. ``".csv"``).

    Returns:
        A 3-tuple of ``(columns, row_count, column_types)``. ``column_types`` maps
        lowercased column name to Spark cast type (``"string"`` or ``"double"``),
        populated only for ``.sas7bdat`` files; ``{}`` otherwise.
    """
    import pandas as pd  # local import — pandas may not be installed in all envs

    try:
        if ext in (".csv", ".tsv"):
            sep = "\t" if ext == ".tsv" else ","
            header_df = pd.read_csv(disk_path, nrows=0, sep=sep)
            columns = list(header_df.columns)
            full_df = pd.read_csv(disk_path, sep=sep)
            return columns, len(full_df), {}
        if ext in (".xlsx", ".xls"):
            header_df = pd.read_excel(disk_path, nrows=0)
            columns = list(header_df.columns)
            full_df = pd.read_excel(disk_path)
            return columns, len(full_df), {}
        if ext == ".sas7bdat":
            try:
                import pyreadstat

                _df, meta = pyreadstat.read_sas7bdat(disk_path, row_limit=0)
                columns = list(meta.column_names)
                column_types = {
                    varname.lower(): _map_readstat_type(rs_type)
                    for varname, rs_type in meta.readstat_variable_types.items()
                }
                return columns, None, column_types
            except ImportError:
                return [], None, {}
    except Exception:
        pass
    return [], None, {}


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


def _build_recon_groups(
    blocks: list["SASBlock"],
    context: "JobContext",
    job_ref_csv: str,
    job_ref_sas: str,
) -> dict[int, tuple[str, str]]:
    """Return mapping of block_index → (ref_csv_path, ref_sas_path) for reconciliation.

    Only blocks that directly output a dataset matching the uploaded file stem
    (or a libname alias) are assigned that file as their per-block ref. No backward
    traversal through input_datasets is performed — intermediate/upstream blocks are
    intentionally excluded to avoid wrong schema/row-count failures.

    Blocks with no matching direct output are excluded from per-block recon. The
    final full-pipeline run handles the job-level ref CSV/SAS7BDAT for those blocks.
    """
    # Map: block index → (ref_csv, ref_sas) — start with no assignment
    assignment: dict[int, tuple[str, str]] = {}

    logger.debug(
        "[recon_groups] data_files=%s libname_map=%s",
        list(context.data_files.keys()),
        context.libname_map,
    )
    logger.debug(
        "[recon_groups] block outputs: %s",
        {i: b.output_datasets for i, b in enumerate(blocks)},
    )

    for norm_path, info in context.data_files.items():
        ext = info.extension
        if ext in (".csv", ".tsv"):
            ref_pair = (info.disk_path, "")
        elif ext == ".sas7bdat":
            ref_pair = ("", info.disk_path)
        else:
            continue

        # Match by file stem only — direct output match, no backward traversal
        file_stem = norm_path.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
        match_names: set[str] = {file_stem}
        logger.debug("[recon_groups] file=%s stem=%s", norm_path, file_stem)

        for idx, block in enumerate(blocks):
            for ds in block.output_datasets:
                # Strip libname prefix (e.g. "outdir.revenue" → "revenue")
                ds_stem = ds.lower().rsplit(".", 1)[-1]
                if ds_stem in match_names and idx not in assignment:
                    logger.debug("[recon_groups] MATCH block=%d ds=%s → %s", idx, ds, norm_path)
                    assignment[idx] = ref_pair

    logger.debug("[recon_groups] final assignment=%s", {k: v[0] for k, v in assignment.items()})
    return assignment


class JobOrchestrator:
    """Runs the full agentic migration pipeline for a single job."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        """Initialise all pipeline components.

        Args:
            session_factory: Optional async session factory used by TraceEmitter.
                When None, tracing is a no-op (backward-compatible for tests that
                instantiate JobOrchestrator without a real DB).
        """
        self._session_factory = session_factory
        self._active_phase: str | None = None
        self._analysis_agent = AnalysisAgent()
        stub = StubGenerator()
        self._router = TranslationRouter(
            data_step_agent=DataStepAgent(),
            proc_agent=ProcAgent(),
            stub_generator=stub,
            generic_proc_agent=GenericProcAgent(),
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
        # Instantiate a per-job tracer; fall back to a no-op when no factory is available.
        tracer: TraceEmitter | None = (
            TraceEmitter(str(job.id), self._session_factory)
            if self._session_factory is not None
            else None
        )
        self._tracer = tracer  # stored for use by _translate_blocks
        self._current_job = job  # stored for cancel checks inside _translate_blocks
        try:
            await self._execute(session, job)
            if tracer is not None:
                await tracer.emit("job_done", {"job_id": str(job.id), "final_status": job.status})
        except JobCancelledError as exc:
            logger.info("Job %s cancelled: %s", job.id, exc)
            _tracker = getattr(self, "_usage_tracker", None)
            await session.execute(
                update(Job)
                .where(Job.id == job.id)
                .values(
                    status="cancelled",
                    token_usage=_tracker.snapshot() if _tracker is not None else None,
                )
            )
            await session.commit()
            if tracer is not None and self._active_phase:
                await tracer.emit(
                    "phase_done",
                    {
                        "phase": self._active_phase,
                        "status": "error",
                        "elapsed_ms": 0,
                    },
                )
                self._active_phase = None
            if tracer is not None:
                await tracer.emit("job_done", {"job_id": str(job.id), "final_status": "cancelled"})
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                logger.warning("Job %s: circuit breaker tripped (HTTP 429)", job.id)
                _tracker = getattr(self, "_usage_tracker", None)
                await session.execute(
                    update(Job)
                    .where(Job.id == job.id)
                    .values(
                        status="failed",
                        error="circuit_breaker_tripped",
                        error_detail={"error": "circuit_breaker_tripped"},
                        token_usage=_tracker.snapshot() if _tracker is not None else None,
                    )
                )
                await session.commit()
            else:
                raise
        except Exception as exc:
            logger.warning("Job %s failed: %s", job.id, exc)
            await session.rollback()
            _tracker = getattr(self, "_usage_tracker", None)
            await session.execute(
                update(Job)
                .where(Job.id == job.id)
                .values(
                    status="failed",
                    error=str(exc)[:500],
                    token_usage=_tracker.snapshot() if _tracker is not None else None,
                )
            )
            await session.commit()
            if tracer is not None and self._active_phase:
                await tracer.emit(
                    "phase_done",
                    {
                        "phase": self._active_phase,
                        "status": "error",
                        "elapsed_ms": 0,
                    },
                )
                self._active_phase = None

    async def _execute(self, session: AsyncSession, job: Job) -> None:
        """Inner pipeline — raises on unhandled errors."""
        _usage_tracker = UsageTracker()
        self._usage_tracker = _usage_tracker
        activate(_usage_tracker)
        files: dict[str, str] = {
            k: v
            for k, v in job.files.items()
            if k not in ("__ref_csv__", "__ref_sas7bdat__", "__refine_context__")
        }
        ref_csv_path: str = str(job.files.get("__ref_csv__", ""))
        ref_sas7bdat_path: str = str(job.files.get("__ref_sas7bdat__", ""))
        data_dir: str = worker_settings.upload_dir.rstrip("/") + "/" + str(job.id)

        # Refine context — injected by POST /jobs/{id}/refine
        refine_context_raw = job.files.get("__refine_context__")
        refine_context: dict[str, Any] | None = None
        if refine_context_raw:
            import contextlib

            with contextlib.suppress(json.JSONDecodeError, TypeError):
                refine_context = json.loads(refine_context_raw)

        # Build data-file catalogue from __ref_* sentinel keys
        data_files: dict[str, DataFileInfo] = {}
        log_contents: dict[str, str] = {}
        for key, disk_path in job.files.items():
            if not key.startswith("__ref_") or not key.endswith("__"):
                continue
            # Handle log sentinels: __ref_log_<norm_path>__
            if key.startswith("__ref_log_"):
                norm_path = key[len("__ref_log_") : -2]
                if norm_path:
                    try:
                        with open(disk_path) as _fh:
                            log_contents[norm_path] = _fh.read()
                    except OSError as _exc:
                        logger.warning("Could not read log file %s: %s", disk_path, _exc)
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
            columns, row_count, column_types = _sniff_file(disk_path, file_ext)
            data_files[norm_path] = DataFileInfo(
                path=norm_path,
                disk_path=disk_path,
                extension=file_ext,
                columns=columns,
                row_count=row_count,
                column_types=column_types,
            )

        if job.skip_llm:
            await self._execute_rereconcile(job, session, ref_csv_path, ref_sas7bdat_path)
            return

        tracer: TraceEmitter | None = getattr(self, "_tracer", None)

        # Phase 1: parse_analysis — parse + macro expand + analyse + libname map
        _t0 = time.monotonic()
        if tracer:
            await tracer.emit("phase_start", {"phase": "parse_analysis"})
            self._active_phase = "parse_analysis"
            set_phase("parse_analysis")

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

        if tracer:
            from collections import Counter

            type_counts = Counter(b.block_type.value for b in blocks)
            await tracer.emit(
                "parse_result",
                {
                    "block_count": len(blocks),
                    "file_count": len({b.source_file for b in blocks}),
                    "macro_var_count": len(parse_result.macro_vars),
                    "block_type_counts": dict(type_counts),
                },
            )

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
                "log_contents": log_contents,
                "format_catalog": parse_result.format_catalog,
            }
        )
        if expansion_warnings:
            context = context.model_copy(
                update={"risk_flags": context.risk_flags + expansion_warnings}
            )

        if tracer:
            await tracer.emit(
                "phase_done",
                {
                    "phase": "parse_analysis",
                    "status": "done",
                    "elapsed_ms": int((time.monotonic() - _t0) * 1000),
                },
            )
            self._active_phase = None

        # Phase 2: migration_planning
        _t0 = time.monotonic()
        if tracer:
            await tracer.emit("phase_start", {"phase": "migration_planning"})
            self._active_phase = "migration_planning"
            set_phase("migration_planning")

        # Step 3.5: Migration planning (best-effort with fallback)
        try:
            plan = await self._migration_planner.plan(context)
            context = context.model_copy(update={"migration_plan": plan})
        except Exception as exc:
            logger.error("Job %s: migration planning failed: %s", job.id, exc)
            raise RuntimeError(f"Migration planning failed: {exc}") from exc

        # Attach missing-dependency findings to the plan (best-effort; never crashes pipeline)
        if context.migration_plan is not None:
            context.migration_plan.missing_dependencies = detect_missing_dependencies(
                parse_result, files
            )
            context.migration_plan.sensitive_data_findings = scan_for_pii(
                parse_result.blocks, context.data_files
            )

        if tracer:
            await tracer.emit(
                "plan_result",
                {
                    "overall_risk": plan.overall_risk,
                    "summary": (plan.summary or "")[:500],
                    "block_count": len(blocks),
                    "review_block_count": len(plan.recommended_review_blocks or []),
                    "cross_file_dependencies": plan.cross_file_dependencies[:10],
                    "block_plans": [
                        {
                            "block_id": bp.block_id,
                            "block_type": bp.block_type,
                            "strategy": bp.strategy.value,
                            "risk": bp.risk.value,
                            "rationale": bp.rationale[:200],
                        }
                        for bp in plan.block_plans
                    ],
                },
            )
            await tracer.emit(
                "phase_done",
                {
                    "phase": "migration_planning",
                    "status": "done",
                    "elapsed_ms": int((time.monotonic() - _t0) * 1000),
                },
            )
            self._active_phase = None

        # Steps 4-7: Translate + two-phase refinement
        prior_python_code: str | None = None
        hint: str | None = None
        if refine_context:
            prior_python_code = refine_context.get("prior_python_code") or None
            hint = refine_context.get("hint") or None

        # Phase 3: translation
        _t0 = time.monotonic()
        if tracer:
            await tracer.emit("phase_start", {"phase": "translation"})
            self._active_phase = "translation"
            set_phase("translation")

        generated, recon_failed = await self._translate_two_phase(
            expanded_blocks,
            context,
            ref_csv_path,
            ref_sas7bdat_path,
            prior_python_code=prior_python_code,
            hint=hint,
            data_dir=data_dir,
            session=session,
        )

        if tracer:
            await tracer.emit(
                "phase_done",
                {
                    "phase": "translation",
                    "status": "done",
                    "elapsed_ms": int((time.monotonic() - _t0) * 1000),
                },
            )
            self._active_phase = None

        # Phase 4: assembly_recon
        _t0 = time.monotonic()
        if tracer:
            await tracer.emit("phase_start", {"phase": "assembly_recon"})
            self._active_phase = "assembly_recon"
            set_phase("assembly_recon")

        # Step 5: Assemble — dict form for generated_files, flat str for python_code column
        generated_files: dict[str, str] = self._codegen.assemble(
            generated, macro_vars=parse_result.macro_vars
        )
        python_code: str = self._codegen.assemble_flat(
            generated, macro_vars=parse_result.macro_vars
        )

        # Step 6: Final reconciliation — runs in executor container (isolates Spark from worker)
        backend = BackendFactory.create()
        report = await RemoteReconciliationService().run(
            ref_csv_path,
            python_code,
            backend,
            ref_sas7bdat_path,
            data_dir=data_dir,
        )

        if tracer:
            await tracer.emit(
                "phase_done",
                {
                    "phase": "assembly_recon",
                    "status": "done",
                    "elapsed_ms": int((time.monotonic() - _t0) * 1000),
                },
            )
            self._active_phase = None

        # Phase 5: enrichment
        _t0 = time.monotonic()
        if tracer:
            await tracer.emit("phase_start", {"phase": "enrichment"})
            self._active_phase = "enrichment"
            set_phase("enrichment")

        # Step 7.5: Lineage enrichment (best-effort)
        try:
            enriched = await self._lineage_enricher.enrich(context)
            context = context.model_copy(update={"enriched_lineage": enriched})
            if tracer:
                await tracer.emit("enrichment_item_done", {"item": "lineage", "status": "done"})
        except Exception as exc:
            logger.warning("Job %s: lineage enrichment failed, continuing: %s", job.id, exc)
            if tracer:
                await tracer.emit("enrichment_item_done", {"item": "lineage", "status": "skipped"})

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
        if tracer:
            await tracer.emit("enrichment_item_done", {"item": "documentation", "status": "done"})

        plain_english_text: str | None = (
            plain_english
            if isinstance(plain_english, str)
            else (context.migration_plan.summary if context.migration_plan else None)
        )
        if not isinstance(plain_english, str):
            logger.warning("Job %s: plain-English generation failed: %s", job.id, plain_english)
        if tracer:
            await tracer.emit("enrichment_item_done", {"item": "plain_english", "status": "done"})

        if plain_english_text:
            report = {**(report or {}), "non_technical_doc": plain_english_text}

        if tracer:
            await tracer.emit(
                "phase_done",
                {
                    "phase": "enrichment",
                    "status": "done",
                    "elapsed_ms": int((time.monotonic() - _t0) * 1000),
                },
            )
            self._active_phase = None

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

        # Step 10: Persist — use under_review if recon failed, proposed if all passed
        final_status = "under_review" if recon_failed else "proposed"
        if recon_failed:
            logger.warning(
                "Job %s completed with reconciliation failures — status=under_review", job.id
            )

        # Step 10a: Write status + code immediately (UI shows result before doc/lineage is ready)
        await session.execute(
            update(Job)
            .where(Job.id == job.id)
            .values(
                status=final_status,
                python_code=python_code,
                generated_files=generated_files,
                migration_plan=(
                    context.migration_plan.model_dump() if context.migration_plan else None
                ),
                llm_model=worker_settings.llm_model,
                token_usage=_usage_tracker.snapshot(),
            )
        )
        await session.commit()
        logger.info("Job %s completed successfully", job.id)

        # Step 10b: Write doc/lineage (best-effort enrichment — already computed above)
        await session.execute(
            update(Job)
            .where(Job.id == job.id)
            .values(
                report=report,
                lineage=lineage_data,
                doc=doc,
            )
        )
        await session.commit()

        # Step 10c: Persist initial BlockRevision rows for every translated block
        await self._persist_initial_revisions(session, job, generated, context)

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

        # Step 11: Per-block reconciliation is handled during _translate_blocks with
        # correctly matched per-block ref files. The old job-level post-pass is
        # intentionally skipped here to avoid reconciling intermediate blocks against
        # the final output schema.

    async def _persist_initial_revisions(
        self,
        session: AsyncSession,
        job: Job,
        generated_blocks: list[GeneratedBlock],
        context: JobContext,
    ) -> None:
        """Create revision-1 BlockRevision rows for every translated block.

        Sets reconciliation_status from exec_ok so the Plan table shows pass/fail
        immediately without waiting for the full reference-based recon pass.
        Skips blocks that already have a revision row (idempotent).
        """
        block_plan_map: dict[str, BlockPlan] = {}
        if context.migration_plan:
            for bp in context.migration_plan.block_plans:
                block_plan_map[bp.block_id] = bp

        for gb in generated_blocks:
            block_id = f"{gb.source_block.source_file}:{gb.source_block.start_line}"

            existing = await session.execute(
                select(BlockRevision)
                .where(BlockRevision.job_id == str(job.id), BlockRevision.block_id == block_id)
                .limit(1)
            )
            if existing.scalar_one_or_none() is not None:
                continue

            block_plan: BlockPlan | None = block_plan_map.get(block_id)
            strategy = block_plan.strategy if block_plan is not None else gb.strategy_used

            rev = BlockRevision(
                id=str(_uuid.uuid4()),
                job_id=str(job.id),
                block_id=block_id,
                revision_number=1,
                python_code=gb.python_code,
                strategy=strategy,
                confidence=gb.confidence_band,
                uncertainty_notes=gb.uncertainty_notes,
                reconciliation_status="pass" if gb.exec_ok else "fail",
                trigger="agent",
                notes=None,
                hint=None,
                diff_vs_previous=None,
            )
            session.add(rev)

        await session.commit()

    async def _reconcile_initial_blocks(
        self,
        session: AsyncSession,
        job: Job,
        context: JobContext,
        ref_csv_path: str,
        ref_sas7bdat_path: str,
        generated_blocks: list[GeneratedBlock],
        data_dir: str = "",
        tracer: TraceEmitter | None = None,
    ) -> None:
        """Run RemoteReconciliationService for each eligible block and persist status.

        Skips blocks with strategy ``manual``, ``manual_ingestion``, or ``skip``.
        Skips entirely when no reference data paths are available.
        Writes ``reconciliation_status`` to the block's initial BlockRevision row.
        Uses cumulative code slices so prior block outputs are available.

        Args:
            session: Active database session.
            job: The job whose blocks should be reconciled.
            context: JobContext holding the migration plan.
            ref_csv_path: Path to reference CSV (may be empty string).
            ref_sas7bdat_path: Path to reference .sas7bdat (may be empty string).
            generated_blocks: Ordered list of GeneratedBlock from the translation phase.
            data_dir: Job-specific upload directory forwarded to the executor for
                /workspace/data/ path resolution.
            tracer: Optional TraceEmitter — when provided, emits ``recon_result``
                and corrective ``block_done`` events into the SSE stream.
        """
        skip_strategies = frozenset({"manual", "manual_ingestion", "skip"})
        remote = RemoteReconciliationService()
        backend = BackendFactory.create()

        block_plans = (
            context.migration_plan.model_dump().get("block_plans", [])
            if context.migration_plan
            else []
        )

        # Build lookup: block_id → index in generated_blocks
        # block_id convention mirrors TranslationRouter: "<source_file>:<start_line>"
        block_order = {
            f"{b.source_block.source_file}:{b.source_block.start_line}": i
            for i, b in enumerate(generated_blocks)
        }

        for bp in block_plans:
            block_id: str = bp.get("block_id", "")
            strategy: str = bp.get("strategy", "translate")
            if strategy in skip_strategies:
                continue

            # Fetch the initial (first) BlockRevision for this block (for DB status update)
            rev_result = await session.execute(
                select(BlockRevision)
                .where(BlockRevision.job_id == str(job.id), BlockRevision.block_id == block_id)
                .order_by(BlockRevision.revision_number.asc())
                .limit(1)
            )
            initial_rev = rev_result.scalar_one_or_none()
            if initial_rev is None or not initial_rev.python_code:
                continue
            already_recon = getattr(initial_rev, "recon_checks", None)
            if initial_rev.reconciliation_status == "pass" and already_recon:
                continue

            # Build cumulative code slice up to and including this block
            idx = block_order.get(block_id)
            if idx is not None:
                cumulative_code = self._codegen.assemble_flat(
                    generated_blocks[: idx + 1],
                    macro_vars=context.resolved_macros,
                )
            else:
                cumulative_code = initial_rev.python_code

            try:
                logger.debug(
                    "_reconcile_initial_blocks: block_id=%s, rawdir_customers=%s",
                    block_id,
                    "rawdir_customers" in cumulative_code,
                )
                report = await remote.run(
                    ref_csv_path,
                    cumulative_code,
                    backend,
                    ref_sas7bdat_path,
                    data_dir=data_dir,
                )
                checks: list[dict[str, Any]] = report.get("checks", [])
                if not checks:
                    continue
                all_passed = all(c.get("status") == "pass" for c in checks)
                recon_status = "pass" if all_passed else "fail"
                await session.execute(
                    update(BlockRevision)
                    .where(BlockRevision.id == initial_rev.id)
                    .values(reconciliation_status=recon_status, recon_checks=checks)
                )
                await session.commit()
                if tracer is not None:
                    await tracer.emit(
                        "recon_result",
                        {
                            "block_id": block_id,
                            "checks": [
                                {
                                    "name": c.get("name", ""),
                                    "status": c.get("status", ""),
                                    "detail": c.get("detail", ""),
                                }
                                for c in checks
                            ],
                            "all_passed": all_passed,
                        },
                    )
                    await tracer.emit(
                        "block_done",
                        {
                            "block_id": block_id,
                            "attempt": 1,
                            "status": recon_status,
                            "elapsed_ms": 0,
                        },
                    )
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
        data_dir: str = "",
        session: AsyncSession | None = None,
    ) -> tuple[list[GeneratedBlock], bool]:
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
            data_dir: Job-specific upload directory forwarded to the executor.
            session: Active database session forwarded for cancel checks.

        Returns:
            (generated_blocks, recon_failed) tuple.
        """
        # Phase 1 — translate all blocks with group-aware per-block reconciliation
        generated_v1, recon_failed = await self._translate_blocks(
            blocks,
            context,
            ref_csv_path,
            ref_sas7bdat_path,
            prior_python_code,
            hint,
            data_dir=data_dir,
            session=session,
        )

        # If per-block recon already flagged failure, skip phase 2 — return what we have
        if recon_failed:
            return generated_v1, True

        python_code_v1 = self._codegen.assemble_flat(
            generated_v1, macro_vars=context.resolved_macros
        )
        backend = BackendFactory.create()
        raw_report_v1 = await RemoteReconciliationService().run(
            ref_csv_path,
            python_code_v1,
            backend,
            ref_sas7bdat_path,
            data_dir=data_dir,
        )
        report_v1 = (
            _dict_to_recon_report(raw_report_v1)
            if isinstance(raw_report_v1, dict)
            else raw_report_v1
        )
        if report_v1.passed or not report_v1.diff_summary:
            return generated_v1, False

        # Phase 2 — interpret failure and re-translate the affected block only
        try:
            retry_hint, affected_id = await self._failure_interpreter.interpret(
                report_v1.diff_summary, python_code_v1, context
            )
        except Exception as exc:
            logger.warning("FailureInterpreterAgent failed, skipping phase 2: %s", exc)
            return generated_v1, False

        generated_v2 = await self._retry_affected_block(
            blocks, generated_v1, context, affected_id, retry_hint
        )
        context = context.model_copy(update={"retry_count": context.retry_count + 1})
        return generated_v2, False

    async def _translate_blocks(
        self,
        blocks: list[SASBlock],
        context: JobContext,
        ref_csv_path: str = "",
        ref_sas7bdat_path: str = "",
        prior_python_code: str | None = None,
        hint: str | None = None,
        data_dir: str = "",
        session: AsyncSession | None = None,
    ) -> tuple[list[GeneratedBlock], bool]:
        """Translate every block via the TranslationRouter with a per-block refine loop.

        Each block is translated up to 3 times.  After each attempt the generated
        code is executed via :class:`BlockExecutor`.  On failure, a
        ``recon_failure_attempt_N`` flag is injected into ``effective_context`` so
        the next attempt benefits from the error summary.  After 3 failed attempts
        the last generated code is kept as-is.

        Reconciliation runs once after all blocks are translated (in _translate_two_phase).
        Always returns recon_failed=False; the caller determines pass/fail from the full recon.

        After each block completes, the job row is refreshed from the DB to check
        ``cancellation_requested``.  If set, :class:`JobCancelledError` is raised.

        Args:
            blocks: Expanded SAS blocks to translate.
            context: Current job context.
            ref_csv_path: Path to reference CSV (may be empty string).
            ref_sas7bdat_path: Path to reference .sas7bdat (may be empty string).
            prior_python_code: Previous translation to improve (from refine context).
            hint: Reviewer hint to prepend to the LLM prompt (from refine context).
            data_dir: Job-specific upload directory forwarded to BlockExecutor.
            session: Active database session used for cancel checks (optional).

        Returns:
            (generated_blocks, False)
        """
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

        backend = BackendFactory.create()
        block_ex = BlockExecutor(executor_url=worker_settings.executor_url)
        generated: list[GeneratedBlock] = []
        tracer: TraceEmitter | None = getattr(self, "_tracer", None)

        # Build per-block reference file mapping using output_datasets + uploaded files
        recon_groups = _build_recon_groups(blocks, context, ref_csv_path, ref_sas7bdat_path)

        for block_idx, block in enumerate(blocks):
            block_id = f"{block.source_file}:{block.start_line}"
            set_block_type(block.block_type.value.lower())
            block_plan = block_plan_map.get(block_id)
            translator = self._router.route(block, block_plan=block_plan)

            gb: GeneratedBlock | None = None
            exec_ok: bool = True
            attempt_context = effective_context

            for attempt in range(1, 4):
                logger.info(
                    "[F19] %s block %s attempt %d/3",
                    type(translator).__name__,
                    block_id,
                    attempt,
                )
                if tracer is not None:
                    await tracer.emit(
                        "block_start",
                        {
                            "block_id": block_id,
                            "agent": type(translator).__name__,
                            "attempt": attempt,
                        },
                    )
                t0 = time.monotonic()
                try:
                    gb = await translator.translate(block, attempt_context)
                except Exception as exc:
                    logger.warning(
                        "[F19] %s block %s attempt %d/3 --> translation error: %s",
                        type(translator).__name__,
                        block_id,
                        attempt,
                        type(exc).__name__,
                    )
                    elapsed_ms = int((time.monotonic() - t0) * 1000)
                    if tracer is not None:
                        await tracer.emit(
                            "block_done",
                            {
                                "block_id": block_id,
                                "attempt": attempt,
                                "status": "error",
                                "elapsed_ms": elapsed_ms,
                            },
                        )
                    gb = None
                    if attempt < 3:
                        flag = (
                            f"translation_error_attempt_{attempt}: "
                            f"{type(exc).__name__}: {str(exc)[:200]}"
                        )
                        attempt_context = attempt_context.model_copy(
                            update={"risk_flags": [*attempt_context.risk_flags, flag]}
                        )
                        continue
                    break

                # Build cumulative code: all prior blocks' code + this block's code.
                # This ensures upstream variables (e.g. revenue_sorted from block N-1)
                # are defined when block N runs — no cross-process session cache needed.
                prior_code = self._codegen.assemble_flat(
                    generated, macro_vars=context.resolved_macros
                )
                exec_code = (
                    (prior_code + "\n\n" + gb.python_code).strip() if prior_code else gb.python_code
                )
                # Point the result-capture snippet at this block's output var
                if gb.output_var:
                    exec_code += f"\nresult = {gb.output_var}\n"
                recon_result = await block_ex.run(
                    exec_code,
                    block_id,
                    backend,
                    data_dir=data_dir or None,
                    ref_csv_path=recon_groups.get(block_idx, ("", ""))[0],
                    ref_sas7bdat_path=recon_groups.get(block_idx, ("", ""))[1],
                )
                elapsed_ms = int((time.monotonic() - t0) * 1000)

                if recon_result is None:
                    # No reference data — treat as pass
                    if tracer is not None:
                        await tracer.emit(
                            "block_done",
                            {
                                "block_id": block_id,
                                "attempt": attempt,
                                "status": "pass",
                                "elapsed_ms": elapsed_ms,
                            },
                        )
                    break

                checks: list[dict[str, Any]] = recon_result.get("checks", [])
                _runtime_error: str = recon_result.get("runtime_error", "")
                _stderr: str = recon_result.get("stderr", "")
                all_passed = all(c.get("status") == "pass" for c in checks)
                recon_passed = all_passed
                exec_ok = all_passed

                if tracer is not None:
                    await tracer.emit(
                        "block_done",
                        {
                            "block_id": block_id,
                            "attempt": attempt,
                            "status": "pass" if recon_passed else "fail",
                            "elapsed_ms": elapsed_ms,
                        },
                    )
                    if checks:
                        await tracer.emit(
                            "recon_result",
                            {
                                "block_id": block_id,
                                "checks": [
                                    {
                                        "name": c.get("name", ""),
                                        "status": c.get("status", ""),
                                        "detail": c.get("detail", ""),
                                    }
                                    for c in checks
                                ],
                                "all_passed": all_passed,
                            },
                        )

                if all_passed:
                    break

                if attempt < 3:
                    # Summarise first failure for the next attempt's context
                    failed_details = [
                        c.get("detail", c.get("name", "unknown"))
                        for c in checks
                        if c.get("status") != "pass"
                    ]
                    extra_hints: list[str] = []
                    for check in checks:
                        if check.get("status") == "pass":
                            continue
                        name = check.get("name", "")
                        detail = check.get("detail", "")
                        if name == "schema_parity" and detail:
                            for col_part in detail.split(";"):
                                col_part = col_part.strip()
                                if "ref=" in col_part and "actual=" in col_part:
                                    col_name = col_part.split(":")[0].strip()
                                    try:
                                        ref_type = col_part.split("ref=")[1].split(",")[0].strip()
                                        actual_type = col_part.split("actual=")[1].strip()
                                        # Generate a concrete cast instruction
                                        if ref_type == "object" and "numeric" in actual_type:
                                            cast_hint = (
                                                f"column '{col_name}': ref is string/object"
                                                f" but output is {actual_type} —"
                                                f" add .withColumn('{col_name}',"
                                                f" F.col('{col_name}').cast('string'))"
                                            )
                                        elif "numeric" in ref_type and ref_type != actual_type:
                                            cast_hint = (
                                                f"column '{col_name}': ref is {ref_type}"
                                                f" but output is {actual_type} —"
                                                f" add .withColumn('{col_name}',"
                                                f" F.col('{col_name}').cast('{ref_type}'))"
                                            )
                                        else:
                                            cast_hint = (
                                                f"column '{col_name}': output is"
                                                f" {actual_type} but ref expects"
                                                f" {ref_type} — cast to match"
                                            )
                                        extra_hints.append(cast_hint)
                                    except IndexError:
                                        pass
                        elif name == "aggregate_parity" and detail:
                            for col_part in detail.split(";"):
                                col_part = col_part.strip()
                                if "ref_sum=" in col_part:
                                    try:
                                        ref_sum = float(
                                            col_part.split("ref_sum=")[1].split(",")[0].strip()
                                        )
                                        if abs(ref_sum) < 1e-3:
                                            extra_hints.append(
                                                "ref_sum is near zero — this may be floating point"
                                                " drift between SAS and Spark rather than a logic"
                                                " error; if so, add a comment in the generated code"
                                                " explaining this (e.g. '# NOTE: sum ≈ 0 by"
                                                " construction; deviation from SAS ref is IEEE 754"
                                                " floating point drift, not a logic error')"
                                            )
                                    except (IndexError, ValueError):
                                        pass
                    error_summary = "; ".join(failed_details + extra_hints)
                    error_summary = error_summary.replace("\n", " ")[:500]
                    flag = f"recon_failure_attempt_{attempt}: {error_summary}"
                    retry_flags: list[str] = [flag]
                    # Change #1: when we have concrete corrective hints, surface them
                    # as a high-salience MANDATORY directive (an imperative command)
                    # distinct from the flat diagnostic flags — the model otherwise
                    # buries the fix and rerolls it away.
                    if extra_hints:
                        fix_instructions = "; ".join(extra_hints).replace("\n", " ")[:500]
                        mandatory_flag = (
                            f"MANDATORY FIX (attempt {attempt}): your previous output was wrong."
                            f" The corrected code MUST contain these changes: {fix_instructions}."
                            f" Apply them exactly; do not omit them."
                        )
                        retry_flags.append(mandatory_flag)
                    # Change #3: feed the prior attempt's code back so the model
                    # patches it instead of regenerating from scratch. Reuses the
                    # same fenced-python mechanism as the job-level refine flow.
                    if gb is not None:
                        retry_flags.append(
                            "this is your previous attempt for THIS block; modify it"
                            " minimally to apply the MANDATORY FIX above and fix the"
                            " issues; keep everything else identical:\n```python\n"
                            f"{gb.python_code}\n```"
                        )
                    # Surface the actual Python traceback so the LLM can fix the root cause
                    if _runtime_error:
                        rt_flag = (
                            f"runtime_error_attempt_{attempt}: "
                            + _runtime_error.replace("\n", " ")[:400]
                        )
                        retry_flags.append(rt_flag)
                    elif _stderr:
                        # Extract the last meaningful line from stderr (usually the exception)
                        _err_tail = " | ".join(
                            line for line in _stderr.splitlines() if line.strip()
                        )[-400:]
                        stderr_flag = f"stderr_attempt_{attempt}: {_err_tail}"
                        retry_flags.append(stderr_flag)
                    attempt_context = attempt_context.model_copy(
                        update={"risk_flags": [*attempt_context.risk_flags, *retry_flags]}
                    )
                # On attempt 3 fall through — use last generated code as-is

            if gb is not None:
                gb.exec_ok = exec_ok
                generated.append(gb)

            # Cancel check: open a fresh session so we don't touch the outer
            # session's identity map (the job object may be detached or expired).
            _job: Job | None = getattr(self, "_current_job", None)
            if self._session_factory is not None and _job is not None:
                async with self._session_factory() as _cs:
                    fresh = await _cs.get(Job, _job.id)
                    if fresh is not None and fresh.cancellation_requested:
                        raise JobCancelledError(f"Job {_job.id} cancelled by user")

        # Clear block-type context after translation loop completes
        set_block_type("")

        # Final full-pipeline recon — all blocks concatenated, no session cache
        if tracer is not None and generated and (ref_csv_path or ref_sas7bdat_path):
            await tracer.emit(
                "block_start",
                {"block_id": "pipeline:full", "agent": "FinalRecon", "attempt": 1},
            )
            full_code = self._codegen.assemble_flat(generated, macro_vars=context.resolved_macros)
            t0_f = time.monotonic()
            final_result = await block_ex.run(
                full_code,
                "pipeline:full",
                backend,
                data_dir=data_dir or None,
                session_dir="",  # run everything fresh — no cache
                ref_csv_path=ref_csv_path,
                ref_sas7bdat_path=ref_sas7bdat_path,
            )
            elapsed_f = int((time.monotonic() - t0_f) * 1000)
            final_checks: list[dict[str, Any]] = (
                final_result.get("checks", []) if final_result else []
            )
            all_passed_f = (
                all(c.get("status") == "pass" for c in final_checks) if final_checks else False
            )
            if final_checks:
                await tracer.emit(
                    "recon_result",
                    {
                        "block_id": "pipeline:full",
                        "checks": [
                            {
                                "name": c.get("name", ""),
                                "status": c.get("status", ""),
                                "detail": c.get("detail", ""),
                            }
                            for c in final_checks
                        ],
                        "all_passed": all_passed_f,
                    },
                )
            await tracer.emit(
                "block_done",
                {
                    "block_id": "pipeline:full",
                    "attempt": 1,
                    "status": "pass" if (final_result is not None and all_passed_f) else "fail",
                    "elapsed_ms": elapsed_f,
                },
            )

        # Reconciliation runs once after all blocks are translated (see _translate_two_phase).
        return generated, False

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


async def _recover_stale_jobs(session: AsyncSession) -> None:
    """Reset any jobs stuck in 'running' back to 'queued' at startup.

    Jobs left in 'running' after a worker crash would never be retried otherwise.
    """
    result = await session.execute(
        update(Job).where(Job.status == "running").values(status="queued").returning(Job.id)
    )
    recovered = [row[0] for row in result.fetchall()]
    if recovered:
        await session.commit()
        logger.warning("Recovered %d stale running job(s) → queued: %s", len(recovered), recovered)


async def poll_loop() -> None:
    """Continuously poll for queued jobs and process them."""
    session_factory = _make_session_factory()
    orchestrator = JobOrchestrator(session_factory=session_factory)
    logger.info("Worker started — polling every %ds", worker_settings.poll_interval_seconds)

    async with session_factory() as session:
        await _recover_stale_jobs(session)

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
