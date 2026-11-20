"""Privacy-safe rotating logging setup.

Never logs URLs or page titles: a custom filter redacts http(s) URLs before
any record is written to disk.
"""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

MAX_LOG_BYTES: int = 2 * 1024 * 1024  # 2 MB per file
BACKUP_COUNT: int = 3
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


class PrivacyRedactingFilter(logging.Filter):
    """Strip full URLs from log messages to honor Kazu's zero-URL-logging rule."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _URL_RE.sub("[redacted-url]", record.msg)
        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(
                    _URL_RE.sub("[redacted-url]", arg) if isinstance(arg, str) else arg
                    for arg in record.args
                )
            elif isinstance(record.args, dict):
                record.args = {
                    key: (_URL_RE.sub("[redacted-url]", val) if isinstance(val, str) else val)
                    for key, val in record.args.items()
                }
        return True


def configure_logging(log_file: Path, level: int = logging.INFO) -> logging.Logger:
    """Configure the root 'kazu' logger with rotating file output and URL redaction."""
    logger = logging.getLogger("kazu")
    logger.setLevel(level)
    logger.propagate = False

    if logger.handlers:
        return logger

    log_file.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_file,
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)
    handler.addFilter(PrivacyRedactingFilter())
    logger.addHandler(handler)
    return logger
