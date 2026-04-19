"""LLM-powered documentation generator for completed migration jobs.

Produces a structured Markdown summary describing what the original SAS code
does, key datasets, business logic, and migration notes.
"""

import logging
import textwrap
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.backend.db.models import Job
    from src.worker.engine.llm_client import LLMClient

logger = logging.getLogger(__name__)


def _build_doc_prompt(files: dict[str, str], report: dict[str, Any] | None) -> str:
    """Construct the LLM user prompt from source files and reconciliation report.

    Args:
        files: Mapping of filename to SAS source text (sentinel keys excluded).
        report: Reconciliation report dict, or None if not yet available.

    Returns:
        Formatted prompt string ready for the LLM.
    """
    sources_section = "\n\n".join(
        f"### {name}\n```sas\n{content}\n```" for name, content in files.items()
    )
    report_summary = "No reconciliation report available."
    if report:
        checks = report.get("checks", [])
        passed = sum(1 for c in checks if c.get("status") == "pass")
        total = len(checks)
        report_summary = f"Reconciliation: {passed}/{total} checks passed."

    return textwrap.dedent(f"""\
        You are a technical documentation expert. Produce a structured Markdown
        summary for the SAS migration below.

        Include these sections using ## headings:
        ## Overview
        What the SAS code does in plain English (2-4 sentences).

        ## Key Datasets
        Table: | Dataset | Role (Input/Output) | Description |

        ## Business Logic
        Numbered list of the core transformations and filters.

        ## Migration Notes
        Bullet list of any untranslatable constructs or review items.
        Write "No migration issues identified." if none.

        Source files:
        {sources_section}

        Reconciliation summary:
        {report_summary}

        IMPORTANT: Your entire response must be the raw Markdown document.
        Do NOT wrap it in a code fence (no ```markdown). Do NOT add any preamble
        or explanation before the first ## heading.
    """)


class DocGenerator:
    """Generates a Markdown documentation summary for a completed migration job."""

    async def generate(self, job: "Job", llm_client: "LLMClient") -> str | None:
        """Ask the LLM to produce documentation for *job*.

        Builds a prompt from the job's source files and reconciliation report,
        then calls the LLM via llm_client.  Returns None on any failure so the
        worker is never blocked by doc generation.

        Args:
            job: The completed (or running) migration job with files and report.
            llm_client: Configured LLM client instance.

        Returns:
            Markdown string on success, None on any exception.
        """
        try:
            files: dict[str, str] = {
                k: v for k, v in (job.files or {}).items() if not k.startswith("__")
            }
            if not files:
                logger.warning("Job %s has no source files; skipping doc generation", job.id)
                return None

            prompt = _build_doc_prompt(files, job.report)
            doc = await llm_client.generate_text(prompt)
            return doc
        except Exception as exc:
            logger.warning("Doc generation failed for job %s: %s", job.id, exc)
            return None
