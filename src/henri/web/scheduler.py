"""Background scheduler for automated pipeline runs.

Full pipeline runs at a configurable daily schedule (default 06:00 UTC).
Quick OSINT check runs at a configurable interval (default 15 minutes).

All schedule parameters come from environment variables.
"""

from __future__ import annotations

import logging
import os
from datetime import date, timezone

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _run_full_pipeline() -> None:
    """Execute the full HENRI pipeline as a background job."""
    logger.info("Scheduler: starting full pipeline run")
    try:
        from henri.run_all import run_pipeline
        from henri.web.db import (
            init_db, start_pipeline_run, finish_pipeline_run,
            upsert_risk_scores,
        )
        from henri.web.api.pipeline import _acquire_file_lock, _release_file_lock

        if not _acquire_file_lock():
            logger.warning("Scheduler: pipeline lock held, skipping this run")
            return

        init_db()
        run_id = start_pipeline_run()

        result = run_pipeline(fixtures=False)

        # Persist risk scores to SQLite for sparklines
        import json
        from pathlib import Path
        data_dir = Path(os.getenv("DATA_DIR", "./data"))
        scores_path = data_dir / "processed" / "risk_scores.json"
        if scores_path.exists():
            with open(scores_path) as f:
                scores_data = json.load(f)
            cards = scores_data.get("cards", [])
            if cards:
                today = date.today().isoformat()
                count = upsert_risk_scores(today, cards)
                logger.info("Scheduler: persisted %d risk scores to SQLite", count)

        status = "ok" if not result["steps_failed"] else "partial"
        report_path = result["report_paths"][0] if result["report_paths"] else None
        finish_pipeline_run(run_id, status, report_path=report_path)
        logger.info("Scheduler: full pipeline complete — %s", status)

    except Exception as exc:
        logger.error("Scheduler: full pipeline failed — %s", type(exc).__name__)
    finally:
        _release_file_lock()


def _run_osint_quick_check() -> None:
    """Quick OSINT check — IODA summary + Cloudflare outages only."""
    logger.info("Scheduler: starting quick OSINT check")
    try:
        from henri.run_all import run_pipeline
        run_pipeline(fixtures=False, sources={"osint"})
    except Exception as exc:
        logger.error("Scheduler: OSINT quick check failed — %s", type(exc).__name__)


def start_scheduler() -> BackgroundScheduler:
    """Create and start the background scheduler."""
    global _scheduler

    full_hour = int(os.getenv("SCHEDULER_FULL_HOUR", "6"))
    full_minute = int(os.getenv("SCHEDULER_FULL_MINUTE", "0"))
    osint_interval = int(os.getenv("SCHEDULER_OSINT_INTERVAL_MINUTES", "15"))

    _scheduler = BackgroundScheduler(timezone="UTC")

    _scheduler.add_job(
        _run_full_pipeline,
        "cron",
        hour=full_hour,
        minute=full_minute,
        id="full_pipeline",
        name="Full HENRI pipeline",
        replace_existing=True,
    )

    _scheduler.add_job(
        _run_osint_quick_check,
        "interval",
        minutes=osint_interval,
        id="osint_quick",
        name="Quick OSINT check",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info(
        "Scheduler started: full pipeline at %02d:%02d UTC, OSINT every %dm",
        full_hour, full_minute, osint_interval,
    )
    return _scheduler


def stop_scheduler() -> None:
    """Shut down the scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped")
