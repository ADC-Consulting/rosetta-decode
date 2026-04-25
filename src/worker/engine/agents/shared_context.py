"""Shared prompt-building utilities for all translation agents.

# SAS: src/worker/engine/agents/shared_context.py:1
"""

from src.worker.engine.models import JobContext


def build_context_section(context: JobContext) -> str:
    """Return a ``## Project context`` prompt block, or ``''`` if nothing to show.

    Dynamically renders:
    - A ``### SAS libname / filename mappings`` sub-section when ``context.libname_map``
      is non-empty.
    - A ``### Data files in this project`` sub-section when ``context.data_files``
      is non-empty, listing each file's path, columns (if known), and row count (if known).

    The section ends with a note directing the agent to use the listed paths for
    any file I/O block.

    Args:
        context: The current job context (or a windowed view of it).

    Returns:
        A formatted Markdown-style string suitable for prepending to a user prompt,
        or an empty string when both ``libname_map`` and ``data_files`` are empty.
    """
    if not context.libname_map and not context.data_files:
        return ""

    parts: list[str] = ["## Project context", ""]

    if context.libname_map:
        parts.append("### SAS libname / filename mappings")
        for alias, path in sorted(context.libname_map.items()):
            parts.append(f"- {alias} → {path}")
        parts.append("")

    if context.data_files:
        parts.append("### Data files in this project")
        for norm_path, info in sorted(context.data_files.items()):
            col_str = ""
            if info.columns:
                col_str = f"  [columns: {', '.join(info.columns)}]"
            row_str = ""
            if info.row_count is not None:
                row_str = f"  ({info.row_count} rows)"
            parts.append(f"- {norm_path}{col_str}{row_str}")
        parts.append("")

    parts.append("For any file I/O block: use the actual relative paths listed above.")
    parts.append("")

    return "\n".join(parts)
