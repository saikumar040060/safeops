"""Structured application logging.

Every log record automatically carries request_id/execution_id/agent_id
from the current request context (see request_context.py) without callers
having to pass them explicitly. A redaction filter masks any `extra` field
whose key looks like a secret before it ever reaches a handler -- the same
sensitive-key pattern the frontend uses for display redaction, applied here
to a different sink (application logs).
"""

import json
import logging
import re
import sys

from app.core.request_context import get_agent_id, get_execution_id, get_request_id

_SENSITIVE_KEY_PATTERN = re.compile(
    r"pass(word)?|secret|token|api[_-]?key|private[_-]?key|credential|"
    r"authorization|access[_-]?key|refresh[_-]?key|cookie",
    re.IGNORECASE,
)

_RESERVED_LOG_RECORD_ATTRS = set(logging.makeLogRecord({}).__dict__)


def _is_sensitive_key(key: str) -> bool:
    return bool(_SENSITIVE_KEY_PATTERN.search(key))


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        record.execution_id = get_execution_id()
        record.agent_id = get_agent_id()
        return True


class RedactingJSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "execution_id": getattr(record, "execution_id", None),
            "agent_id": getattr(record, "agent_id", None),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOG_RECORD_ATTRS or key in payload:
                continue
            payload[key] = "***REDACTED***" if _is_sensitive_key(key) else value
        if record.exc_info:
            # Deliberately never included: this is server-side-only logging
            # (never returned to a caller), but we still avoid dumping raw
            # tracebacks into structured fields consumed by log pipelines
            # that might forward them elsewhere.
            payload["exc_type"] = str(record.exc_info[0].__name__) if record.exc_info[0] else None
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(RedactingJSONFormatter())
    handler.addFilter(ContextFilter())
    root.addHandler(handler)


logger = logging.getLogger("safeops")
