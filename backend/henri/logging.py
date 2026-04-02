"""Structured JSON logging with correlation IDs.

All log output is JSON — one object per line — for easy ingestion
by Elasticsearch, Splunk, or OpenShift log aggregation.

Usage:
    from henri.logging import setup_logging, get_correlation_id, set_correlation_id

    setup_logging()  # Call once at startup
    set_correlation_id("pipeline-20260402-0600")  # Optional per-run ID
"""

from __future__ import annotations

import json
import logging
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

# Thread-local storage for correlation ID
_context = threading.local()


def get_correlation_id() -> str:
    """Get the current correlation ID, or generate one."""
    cid = getattr(_context, "correlation_id", None)
    if not cid:
        cid = uuid.uuid4().hex[:12]
        _context.correlation_id = cid
    return cid


def set_correlation_id(cid: str) -> None:
    """Set the correlation ID for the current thread."""
    _context.correlation_id = cid


def new_correlation_id() -> str:
    """Generate and set a new correlation ID. Returns it."""
    cid = uuid.uuid4().hex[:12]
    _context.correlation_id = cid
    return cid


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects.

    Output fields:
    - ts: ISO 8601 timestamp (UTC)
    - level: DEBUG/INFO/WARNING/ERROR/CRITICAL
    - logger: logger name (e.g. "osint.acled")
    - msg: the log message
    - cid: correlation ID (links all logs from one pipeline run)
    - extra fields: any extra kwargs passed via logger.info("msg", extra={...})

    Alert-specific fields (when present):
    - alert_type: "precursor" | "escalation" | "de-escalation"
    - alert_country: country name
    - alert_delegations: list of delegation codes

    Request fields (when present):
    - method: HTTP method
    - path: request path
    - status: response status code
    - duration_ms: request duration
    - client_ip: client IP address

    Audit fields (when present):
    - audit_action: "pipeline.regenerate" | "pipeline.complete" etc.
    - audit_user: client identifier (IP for now, user ID when auth is added)
    """

    def format(self, record: logging.LogRecord) -> str:
        obj: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "cid": get_correlation_id(),
        }

        # Merge any extra fields (alert_type, method, audit_action, etc.)
        for key in (
            "alert_type", "alert_country", "alert_delegations",
            "method", "path", "status", "duration_ms", "client_ip",
            "audit_action", "audit_user", "audit_detail",
            "source", "records", "step", "pipeline_run_id",
        ):
            val = getattr(record, key, None)
            if val is not None:
                obj[key] = val

        return json.dumps(obj, default=str, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    """Configure structured JSON logging for the entire application.

    Call this once at startup (in __main__.py or app.py).
    Replaces any existing handlers on the root logger.
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)

    # Quiet noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
