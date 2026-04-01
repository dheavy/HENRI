"""Dashboard endpoint — returns everything the main page needs in one call."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter

router = APIRouter()
logger = logging.getLogger(__name__)


def _data_dir() -> Path:
    return Path(os.getenv("DATA_DIR", "./data"))


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _load_forward_alerts(data_dir: Path, registry: dict) -> list[dict]:
    try:
        from henri.forward_alert import check_forward_alerts
        return check_forward_alerts(data_dir, registry)
    except Exception:
        return []


def _load_delta_alerts(data_dir: Path) -> list[dict]:
    scores_path = data_dir / "processed" / "risk_scores.json"
    if not scores_path.exists():
        return []
    try:
        from henri.delta import compute_deltas
        from osint.risk_scorer import compute_risk_cards
        registry = _load_json(data_dir / "reference" / "delegations.json") or {}
        cards = compute_risk_cards(data_dir, registry, use_fixtures=True)
        return compute_deltas(cards, data_dir)
    except Exception:
        return []


def _risk_summary(scores: list[dict]) -> dict[str, int]:
    tiers = {"high": 0, "medium": 0, "low": 0, "minimal": 0}
    for card in scores:
        s = card.get("combined_risk", 0)
        if s >= 70:
            tiers["high"] += 1
        elif s >= 50:
            tiers["medium"] += 1
        elif s >= 25:
            tiers["low"] += 1
        else:
            tiers["minimal"] += 1
    return tiers


@router.get("/dashboard")
async def dashboard() -> dict:
    data_dir = _data_dir()
    registry = _load_json(data_dir / "reference" / "delegations.json") or {}

    # Risk scores
    scores_data = _load_json(data_dir / "processed" / "risk_scores.json") or {}
    risk_cards = scores_data.get("cards", [])
    generated_at = scores_data.get("_generated_at", "")

    # Forward alerts (precursor warnings)
    forward = _load_forward_alerts(data_dir, registry)
    alerts = [
        {
            "type": "precursor",
            "severity": "warning",
            "country": a["country"],
            "message": a["message"],
            "delegations_at_risk": a["delegations_at_risk"],
            "detected_at": generated_at,
        }
        for a in forward
    ]

    # Delta alerts
    deltas = _load_delta_alerts(data_dir)
    delta_alerts = [
        {
            "country": d["country"],
            "old_score": d["previous_score"],
            "new_score": d["current_score"],
            "delta": d["delta"],
            "direction": d["alert_type"].lower(),
            "primary_driver": ", ".join(d.get("signals_changed", [])),
        }
        for d in deltas
    ]

    # Pipeline status — check file mtimes and compute record counts
    sources: dict[str, dict] = {}

    def _source(name: str, path: Path, metric: str | None = None) -> None:
        if path.exists():
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
            sources[name] = {"status": "ok", "last_pull": mtime, "metric": metric}
        else:
            sources[name] = {"status": "unavailable", "last_pull": None, "metric": None}

    # ServiceNow — count rows in parquet
    snow_path = data_dir / "processed" / "incidents_all.parquet"
    snow_metric = None
    if snow_path.exists():
        try:
            import pyarrow.parquet as pq
            snow_metric = f"{pq.read_metadata(snow_path).num_rows:,} incidents"
        except Exception:
            pass
    _source("servicenow", snow_path, snow_metric)

    # Grafana — count delegations in registry
    grafana_path = data_dir / "reference" / "delegations.json"
    grafana_metric = None
    if grafana_path.exists():
        try:
            reg = _load_json(grafana_path) or {}
            grafana_sites = sum(1 for v in reg.values() if v.get("source", "").startswith("grafana"))
            grafana_metric = f"{grafana_sites} sites"
        except Exception:
            pass
    _source("grafana", grafana_path, grafana_metric)

    # NetBox — count circuits
    netbox_path = data_dir / "reference" / "circuits.json"
    netbox_metric = None
    if netbox_path.exists():
        try:
            circuits = _load_json(netbox_path) or []
            netbox_metric = f"{len(circuits)} circuits"
        except Exception:
            pass
    _source("netbox", netbox_path, netbox_metric)

    # ACLED — count events in parquet
    acled_path = data_dir / "processed" / "acled_events.parquet"
    acled_metric = None
    if acled_path.exists():
        try:
            import pyarrow.parquet as pq
            acled_metric = f"{pq.read_metadata(acled_path).num_rows:,} events"
        except Exception:
            pass
    _source("acled", acled_path, acled_metric)

    # IODA and Cloudflare — count from risk cards
    osint_mtime = generated_at or None
    ioda_countries = sum(1 for c in risk_cards if c.get("ioda_score", 0) > 0)
    cf_countries = sum(1 for c in risk_cards if c.get("cf_outages", 0) > 0)
    sources["ioda"] = {
        "status": "ok" if osint_mtime else "unavailable",
        "last_pull": osint_mtime,
        "metric": f"{ioda_countries} countries" if ioda_countries else None,
    }
    sources["cloudflare"] = {
        "status": "ok" if osint_mtime else "unavailable",
        "last_pull": osint_mtime,
        "metric": f"{cf_countries} countries with outages" if cf_countries else None,
    }

    return {
        "generated_at": generated_at,
        "alerts": alerts,
        "delta_alerts": delta_alerts,
        "risk_summary": _risk_summary(risk_cards),
        "risk_cards": risk_cards,
        "pipeline_status": {
            "last_run": generated_at,
            "sources": sources,
        },
    }
