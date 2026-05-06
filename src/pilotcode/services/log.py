"""Unified logging configuration for PilotCode.

Usage:
    from .log import get_logger
    logger = get_logger(__name__)
    logger.info("Starting mission %s", mission_id)
    logger.warning("Backend probe failed: %s", exc)
    logger.error("Task execution failed", exc_info=True)

Log levels:
    DEBUG    - Detailed internal state (tool I/O, token counts, state transitions)
    INFO     - Normal operation (mission started, task completed, file written)
    WARNING  - Recoverable issues (API retry, probe failed, non-critical IO error)
    ERROR    - Operation failures that need investigation (task rejected, auth failure)
    CRITICAL - System-level failures (config corruption, DB crash)

Log files are written to:
    ~/.pilotcode/logs/pilotcode_{date}.log   (rotated daily, kept 30 days)
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from typing import Any

# =============================================================================
# Log level rules
# =============================================================================
# These constants document what each level should be used for across the codebase.

LEVEL_RULES = """
CRITICAL (50): System unusable. Config corruption, DB crash, unrecoverable errors.
ERROR    (40): Operation failed, needs investigation. Auth failure, task rejected.
WARNING  (30): Recoverable issue. API retry, IO error with fallback, deprecated usage.
INFO     (20): Normal operation milestones. Mission started/completed, file written.
DEBUG    (10): Internal details. Tool I/O, token counts, state transitions, LLM prompts.
"""


# =============================================================================
# Logger registry — ensures all loggers use the same config
# =============================================================================

_LOG_CONFIGURED = False
_LOG_DIR: Path | None = None


def get_log_dir() -> Path:
    """Get the log directory, creating it if necessary."""
    global _LOG_DIR
    if _LOG_DIR is None:
        _LOG_DIR = Path.home() / ".pilotcode" / "logs"
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
    return _LOG_DIR


def configure_logging(
    level: int | str = logging.INFO,
    log_file: str | None = None,
    verbose: bool = False,
) -> None:
    """Configure PilotCode logging globally.

    Args:
        level: Log level (default INFO). Use DEBUG for verbose mode.
        log_file: Optional log file path. Default: ~/.pilotcode/logs/pilotcode_{date}.log
        verbose: If True, also log DEBUG to stderr.
    """
    global _LOG_CONFIGURED
    if _LOG_CONFIGURED:
        return
    _LOG_CONFIGURED = True

    root = logging.getLogger("pilotcode")
    root.setLevel(logging.DEBUG if verbose else level)
    root.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler: daily rotation, kept 30 days
    log_dir = get_log_dir()
    log_path = log_file or str(log_dir / "pilotcode.log")
    file_handler = TimedRotatingFileHandler(
        log_path,
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG if verbose else level)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # Console handler: only WARNING+ by default, or DEBUG+ in verbose mode
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.DEBUG if verbose else logging.WARNING)
    console.setFormatter(formatter)
    root.addHandler(console)

    # Suppress noisy third-party logs
    for noisy in ("httpx", "httpcore", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a PilotCode logger.

    All loggers are children of the ``pilotcode`` root.
    Use ``get_logger(__name__)`` at module level.

    Args:
        name: Usually ``__name__``.

    Returns:
        Logger instance.
    """
    if not _LOG_CONFIGURED:
        configure_logging()
    # Ensure name is under pilotcode namespace
    if not name.startswith("pilotcode"):
        name = f"pilotcode.{name}"
    return logging.getLogger(name)
