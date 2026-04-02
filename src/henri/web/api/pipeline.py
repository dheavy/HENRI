"""Pipeline trigger and status endpoint.

Allows the frontend to trigger report regeneration and poll for completion.
Rate limited: max 1 run per 5 minutes. File lock prevents scheduler/API overlap.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter

router = APIRouter()
logger = logging.getLogger(__name__)

_COOLDOWN_SECONDS = 300  # 5 minutes between regenerations

_lock = threading.Lock()
_state: dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "status": "idle",
    "error": None,
}


def _pipeline_lock_path() -> Path:
    return Path(os.getenv("DATA_DIR", "./data")) / ".pipeline.lock"


def _acquire_file_lock() -> bool:
    """Try to acquire a file-based lock. Returns True if acquired."""
    lock = _pipeline_lock_path()
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        # Check if stale (older than 30 minutes = stuck pipeline)
        try:
            age = time.time() - lock.stat().st_mtime
            if age > 1800:
                lock.unlink(missing_ok=True)
                return _acquire_file_lock()
        except OSError:
            pass
        return False


def _release_file_lock() -> None:
    _pipeline_lock_path().unlink(missing_ok=True)


def _run_pipeline_background() -> None:
    """Run the pipeline in a background thread with file lock."""
    global _state
    from henri.logging import new_correlation_id, get_correlation_id
    cid = new_correlation_id()
    try:
        from henri.run_all import run_pipeline
        from henri.web.db import write_audit
        result = run_pipeline(fixtures=True)
        status = "done" if not result["steps_failed"] else "error"
        with _lock:
            _state["running"] = False
            _state["finished_at"] = time.time()
            _state["status"] = status
            _state["error"] = ", ".join(result["steps_failed"]) if result["steps_failed"] else None
        write_audit(f"pipeline.{status}", detail=f"steps_ok={len(result['steps_run'])}", correlation_id=cid)
    except Exception as exc:
        with _lock:
            _state["running"] = False
            _state["finished_at"] = time.time()
            _state["status"] = "error"
            _state["error"] = type(exc).__name__
        try:
            from henri.web.db import write_audit
            write_audit("pipeline.error", detail=type(exc).__name__, correlation_id=cid)
        except Exception:
            pass
    finally:
        _release_file_lock()


@router.get("/status")
async def pipeline_status() -> dict:
    """Check if the pipeline is running and when it last completed."""
    with _lock:
        return {
            "running": _state["running"],
            "status": _state["status"],
            "started_at": _state["started_at"],
            "finished_at": _state["finished_at"],
            "error": _state["error"],
        }


_audit_logger = logging.getLogger("henri.audit")


@router.post("/regenerate")
async def regenerate(request=None) -> dict:
    """Trigger pipeline regeneration with rate limiting and file locking.

    Rejects if: already running, within cooldown period, or file lock held (scheduler running).
    """
    global _state
    with _lock:
        if _state["running"]:
            return {"accepted": False, "reason": "Pipeline already running"}

        # Cooldown check
        if _state["finished_at"]:
            elapsed = time.time() - _state["finished_at"]
            if elapsed < _COOLDOWN_SECONDS:
                remaining = int(_COOLDOWN_SECONDS - elapsed)
                return {"accepted": False, "reason": f"Cooldown: retry in {remaining}s"}

        # File lock (prevents scheduler/API overlap)
        if not _acquire_file_lock():
            return {"accepted": False, "reason": "Another pipeline process is running"}

        _state["running"] = True
        _state["started_at"] = time.time()
        _state["finished_at"] = None
        _state["status"] = "running"
        _state["error"] = None

    thread = threading.Thread(target=_run_pipeline_background, daemon=True)
    thread.start()
    from henri.logging import get_correlation_id
    from henri.web.db import write_audit
    cid = get_correlation_id()
    _audit_logger.info(
        "Pipeline regeneration triggered",
        extra={"audit_action": "pipeline.regenerate", "audit_user": "api"},
    )
    write_audit("pipeline.regenerate", user="api", correlation_id=cid)

    return {"accepted": True}
