"""Logging that redacts credential-shaped text before it reaches a handler."""

from __future__ import annotations

import logging
import re

_SECRET_ASSIGNMENT = re.compile(
    r"(?i)((?:authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"client[_-]?secret|password|secret|token|bearer)\s*[=:]\s*)(\S+)"
)


def redact_text(value: str) -> str:
    return _SECRET_ASSIGNMENT.sub(r"\1[redacted]", value)


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        if record.args:
            record.args = tuple(redact_text(a) if isinstance(a, str) else a for a in record.args)
        return True


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RedactFilter())
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    # Uvicorn and SQLAlchemy must pass through the same filter.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "sqlalchemy.engine"):
        logger = logging.getLogger(name)
        logger.addFilter(RedactFilter())
