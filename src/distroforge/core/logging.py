"""File logging with rotation and secret redaction.

The console is owned by the TUI (or the headless reporter); this module only
configures the persistent log file so every run leaves an audit trail.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGGER_NAME = "distroforge"

_SECRET_PATTERNS = [
    # key=value / key: value pairs whose key looks sensitive
    re.compile(
        r"(?i)\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|APIKEY)[A-Z0-9_]*)"
        r"(\s*[=:]\s*)(\S+)"
    ),
    # Authorization headers
    re.compile(r"(?i)(authorization:\s*)(\w+\s+)?(\S+)"),
]


def redact(text: str) -> str:
    """Mask values that look like credentials."""
    text = _SECRET_PATTERNS[0].sub(lambda m: f"{m.group(1)}{m.group(2)}***", text)
    return _SECRET_PATTERNS[1].sub(lambda m: f"{m.group(1)}***", text)


class _RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = None
        return True


def get_logger(name: str | None = None) -> logging.Logger:
    return logging.getLogger(LOGGER_NAME if name is None else f"{LOGGER_NAME}.{name}")


def setup_logging(log_dir: Path, *, keep: int = 20) -> Path:
    """Attach a per-run log file to the DistroForge logger and return its path.

    Old run logs beyond ``keep`` are pruned so the directory cannot grow forever.
    """
    log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    log_file = log_dir / f"distroforge-{datetime.now():%Y%m%d-%H%M%S}.log"

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    handler = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s"))
    handler.addFilter(_RedactingFilter())
    logger.addHandler(handler)
    log_file.chmod(0o600)

    runs = sorted(log_dir.glob("distroforge-*.log"))
    for stale in runs[:-keep]:
        stale.unlink(missing_ok=True)

    return log_file
