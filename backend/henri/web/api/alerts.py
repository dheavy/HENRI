"""Alert endpoints — active alerts and history."""

from __future__ import annotations

from fastapi import APIRouter, Query

from henri.web.db import get_active_alerts, get_alert_history, init_db

router = APIRouter()


@router.get("")
async def list_alerts(
    active: bool = Query(True),
) -> dict:
    """Get active or all alerts."""
    init_db()
    if active:
        return {"alerts": get_active_alerts()}
    return {"alerts": get_alert_history()}


@router.get("/history")
async def alert_history(
    from_date: str | None = Query(None, alias="from", pattern=r"^\d{4}-\d{2}-\d{2}"),
    until_date: str | None = Query(None, alias="until", pattern=r"^\d{4}-\d{2}-\d{2}"),
) -> dict:
    """Get historical alerts with optional date range."""
    init_db()
    return {"alerts": get_alert_history(from_date, until_date)}
