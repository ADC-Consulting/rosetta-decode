"""Structured logging configuration for the backend service."""

import logging
import sys

from src.backend.core.config import settings


def configure_logging() -> None:
    """Configure root logger with a structured format."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )
