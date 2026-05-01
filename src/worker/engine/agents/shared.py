"""Shared post-processing utilities for translation agents.

All three translation agents (DataStepAgent, ProcAgent, GenericProcAgent) produce
a python_code string and an output_var string from their LLM call.  The LLM
sometimes uses the libname-qualified form (e.g. ``rawdir_customers`` or
``rawdir.customers``) instead of the required stem-only form (``customers``).
These helpers normalise both fields in one place so each agent delegates the fix
rather than duplicating it.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def normalise_output_var(
    output_datasets: list[str],
    output_var: str | None,
) -> str | None:
    """Return *output_var* normalised to the dataset stem, or unchanged if already correct.

    Matches the LLM-returned value against every known output dataset in both the
    dot form (``libname.table``) and the underscore form (``libname_table``).  When
    a match is found the stem (``table``) is returned instead.

    Args:
        output_datasets: Dataset names from the SAS parser (may be ``libname.table``).
        output_var: Raw ``output_var`` string returned by the LLM.

    Returns:
        Stem-only variable name, or the original *output_var* if no correction needed.
    """
    if not output_var:
        return output_var
    fov = output_var.lower()
    for ds in output_datasets:
        stem = ds.lower().split(".")[-1]
        if ds.lower() == stem:
            continue  # no libname prefix — nothing to correct
        if fov in (ds.lower(), ds.lower().replace(".", "_")):
            return stem
    return output_var


def normalise_output_var_in_code(
    python_code: str,
    output_datasets: list[str],
    agent_name: str,
) -> str:
    """Replace libname-qualified output variable names in *python_code* with stems.

    For each output dataset that has a libname prefix, replaces every word-boundary
    occurrence of the underscore form (``libname_table``) in *python_code* with the
    stem (``table``).  Logs a WARNING when a substitution is made so it is visible
    in the worker logs.

    Args:
        python_code: Generated Python source from the LLM.
        output_datasets: Dataset names from the SAS parser (may be ``libname.table``).
        agent_name: Agent class name used in log messages (e.g. ``"DataStepAgent"``).

    Returns:
        Python source with all libname-qualified output variables replaced.
    """
    for ds in output_datasets:
        stem = ds.lower().split(".")[-1]  # customers
        if ds.lower() == stem:
            continue  # no libname prefix — nothing to correct
        underscore_form = ds.lower().replace(".", "_")  # outdir_customers
        dot_form = ds.lower()  # outdir.customers
        for wrong, pattern in (
            (underscore_form, rf"\b{re.escape(underscore_form)}\b"),
            (dot_form, re.escape(dot_form)),
        ):
            if not re.search(pattern, python_code):
                continue
            logger.warning(
                "%s: renaming '%s' → '%s' in generated code (LLM used libname form)",
                agent_name,
                wrong,
                stem,
            )
            python_code = re.sub(pattern, stem, python_code)
    return python_code
