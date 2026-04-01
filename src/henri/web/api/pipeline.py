"""Pipeline trigger and status endpoint.

Allows the frontend to trigger report regeneration and poll for completion.
Only one regeneration can run at a time.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from fastapi import APIRouter

router = APIRouter()
logger = logging.getLogger(__name__)

_lock = threading.Lock()
_state: dict[str, Any] = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "status": "idle",  # idle | running | done | error
    "error": None,
}


def _run_pipeline_background() -> None:
    """Run the pipeline in a background thread."""
    global _state
    try:
        from henri.run_all import run_pipeline
        result = run_pipeline(fixtures=True)
        with _lock:
            _state["running"] = False
            _state["finished_at"] = time.time()
            _state["status"] = "done" if not result["steps_failed"] else "error"
            _state["error"] = ", ".join(result["steps_failed"]) if result["steps_failed"] else None
    except Exception as exc:
        with _lock:
            _state["running"] = False
            _state["finished_at"] = time.time()
            _state["status"] = "error"
            _state["error"] = type(exc).__name__


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


@router.post("/regenerate")
async def regenerate() -> dict:
    """Trigger pipeline regeneration. Returns immediately; poll /status for completion.

    Rejects if already running.
    """
    global _state
    with _lock:
        if _state["running"]:
            return {"accepted": False, "reason": "Pipeline already running"}
        _state["running"] = True
        _state["started_at"] = time.time()
        _state["finished_at"] = None
        _state["status"] = "running"
        _state["error"] = None

    thread = threading.Thread(target=_run_pipeline_background, daemon=True)
    thread.start()
    logger.info("Pipeline regeneration triggered via API")

    return {"accepted": True}
