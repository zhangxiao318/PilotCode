"""Unified logging configuration for PilotCode.

Usage:
    from .log import get_logger
    logger = get_logger(__name__)
    logger.info("Starting mission %s", mission_id)
    logger.warning("Backend probe failed: %s", exc)
    logger.error("Task execution failed", exc_info=True)

Log levels:
    DEBUG    - Detailed internal state (tool I/O, token counts, state transitions)
    INFO     - Normal operation (server lifecycle, session lifecycle, query iterations)
    WARNING  - Recoverable issues (API retry, probe failed, non-critical IO error)
    ERROR    - Operation failures that need investigation (task rejected, auth failure)
    CRITICAL - System-level failures (config corruption, DB crash)

Console output conventions:
    - print() to stdout: User-facing UI only (banners, startup URLs, Rich-formatted text)
    - logger.* to stderr: All internal diagnostic information
    - Default console level: INFO  (shows lifecycle milestones)
    - Use --verbose / -v  flag:  DEBUG (shows internal details)
    - Log file always records:  DEBUG+ (rotated daily, kept 30 days)

Log files are written to:
    ~/.pilotcode/logs/pilotcode.log   (date-based rotation, kept 30 days)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler

# =============================================================================
# Windows-safe rotating file handler
# =============================================================================


class _SafeTimedRotatingFileHandler(TimedRotatingFileHandler):
    """TimedRotatingFileHandler that gracefully handles Windows file-lock errors."""

    def doRollover(self):
        try:
            super().doRollover()
        except PermissionError as exc:
            if getattr(exc, "winerror", None) == 32:
                # super().doRollover() may have closed the stream on failure;
                # re-open it so subsequent logging works.
                if self.stream is None:
                    self.stream = self._open()
                if self.stream:
                    self.stream.write(f"[log] Rollover skipped (file locked on Windows): {exc}\n")
                    self.stream.flush()
            else:
                raise


# =============================================================================
# Log level rules
# =============================================================================

LEVEL_RULES = """
CRITICAL (50): System unusable. Config corruption, DB crash, unrecoverable errors.
ERROR    (40): Operation failed, needs investigation. Auth failure, task rejected.
WARNING  (30): Recoverable issue. API retry, IO error with fallback, deprecated usage.
INFO     (20): Normal operation milestones. Server lifecycle, session lifecycle.
DEBUG    (10): Internal details. Tool I/O, WebSocket messages, token counts.
"""


# =============================================================================
# Logger registry
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

    Output strategy:
      - stdout: Reserved for user-facing UI (banners, Rich output via print())
      - stderr (console handler):  Internal diagnostics.
          default level = INFO, verbose level = DEBUG
      - File (rotating):          Full detail.
          level = DEBUG (always), so verbose only affects console.

    Args:
        level: Base log level (default INFO).
        log_file: Optional log file path. Default: ~/.pilotcode/logs/pilotcode.log
        verbose: If True, show DEBUG-level messages on stderr.
    """
    global _LOG_CONFIGURED
    if _LOG_CONFIGURED:
        return
    _LOG_CONFIGURED = True

    root = logging.getLogger("pilotcode")
    root.setLevel(logging.DEBUG)  # Always capture DEBUG for file; console handler filters.
    root.handlers.clear()

    # Compact formatter for console (no date — context is obvious in real-time)
    console_fmt = logging.Formatter(
        "[%(levelname)-5s] %(name)s: %(message)s",
    )

    # Full formatter for file (date + module for post-mortem analysis)
    file_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # --- File handler: always DEBUG+, rotated daily, kept 30 days ---
    log_dir = get_log_dir()
    log_path = log_file or str(log_dir / "pilotcode.log")
    file_handler = _SafeTimedRotatingFileHandler(
        log_path,
        when="midnight",
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_fmt)
    root.addHandler(file_handler)

    # --- Console handler (stderr): INFO by default, DEBUG in verbose mode ---
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.DEBUG if verbose else logging.INFO)
    console.setFormatter(console_fmt)
    root.addHandler(console)

    # Suppress noisy third-party logs (only ERROR+ to console, WARNING+ to file)
    for noisy in ("httpx", "httpcore", "urllib3", "asyncio", "websockets"):
        logging.getLogger(noisy).setLevel(logging.ERROR)
    # websockets protocol level is especially chatty
    logging.getLogger("websockets.protocol").setLevel(logging.WARNING)

    # Announce startup in log file (never on console — use print() for that)
    root.debug("Logging configured: verbose=%s, level=%s, file=%s", verbose, level, log_path)


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
    # Keep the name clean — strip "src.pilotcode." / "pilotcode." prefix if present
    # so log output shows the short module path.
    clean = name
    if clean.startswith("pilotcode."):
        clean = clean[len("pilotcode.") :]
    return logging.getLogger(f"pilotcode.{clean}")
