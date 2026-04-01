"""Surge and precursor analysis endpoints."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Query

router = APIRouter()
logger = logging.getLogger(__name__)


def _data_dir() -> Path:
    return Path(os.getenv("DATA_DIR", "./data"))


@router.get("")
async def list_surges(
    region: str | None = Query(None, pattern=r"^[A-Za-z ]+$"),
    has_precursor: bool | None = Query(None),
    limit: int = Query(30, ge=1, le=100),
) -> dict:
    """List surge events with precursor analysis."""
    path = _data_dir() / "processed" / "precursor_analysis.parquet"
    if not path.exists():
        return {"surges": [], "stats": {}}

    try:
        df = pd.read_parquet(path)
    except Exception:
        return {"surges": [], "stats": {}}

    # Filters
    if region:
        df = df[df["region"].str.upper() == region.upper()]
    if has_precursor is True:
        df = df[df["any_external"] | df["internal_detected"]]
    elif has_precursor is False:
        df = df[~df["any_external"] & ~df["internal_detected"]]

    # Sort: precursor-positive first by lead time asc, then by score desc
    has_p = df[df["any_external"] | df["internal_detected"]].copy()
    no_p = df[~df["any_external"] & ~df["internal_detected"]].copy()

    has_p = has_p.sort_values("lead_time_hours", ascending=True, na_position="last")
    no_p = no_p.sort_values("surge_score", ascending=False)

    sorted_df = pd.concat([has_p, no_p]).head(limit)

    # Build response
    surges = []
    for _, row in sorted_df.iterrows():
        lead_h = float(row["lead_time_hours"]) if pd.notna(row.get("lead_time_hours")) else None
        surges.append({
            "id": int(row.get("surge_id", 0)),
            "date": row.get("date", ""),
            "region": row.get("region", ""),
            "delegations": str(row.get("delegations", "")).split(","),
            "countries": str(row.get("countries", "")).split(","),
            "score": round(float(row.get("surge_score", 0)), 1),
            "precursors": {
                "acled": {
                    "detected": bool(row.get("acled_detected", False)),
                    "events": int(row.get("acled_events", 0)),
                    "ratio": float(row.get("acled_ratio", 0)),
                },
                "ioda": {
                    "detected": bool(row.get("ioda_detected", False)),
                    "alerts": int(row.get("ioda_alerts", 0)),
                },
                "cloudflare": {
                    "detected": bool(row.get("cf_detected", False)),
                    "events": int(row.get("cf_events", 0)),
                },
                "internal": {
                    "detected": bool(row.get("internal_detected", False)),
                    "latency_alerts": int(row.get("internal_latency_alerts", 0)),
                },
            },
            "lead_time_h": lead_h,
            "any_precursor": bool(row.get("any_external", False)) or bool(row.get("internal_detected", False)),
        })

    # Stats
    total = len(df)
    with_ext = int(df["any_external"].sum())
    with_int = int(df["internal_detected"].sum())
    lead_times = df.loc[df["lead_time_hours"].notna(), "lead_time_hours"]
    avg_lead = round(float(lead_times.mean()), 1) if not lead_times.empty else 0

    stats = {
        "total_surges": total,
        "with_external_precursor": with_ext,
        "with_internal_precursor": with_int,
        "pct_with_precursor": round(with_ext / max(total, 1) * 100, 1),
        "avg_lead_time_hours": avg_lead,
    }

    return {"surges": surges, "stats": stats}


@router.get("/{surge_id}")
async def surge_detail(surge_id: int) -> dict:
    """Get a single surge with full precursor detail."""
    path = _data_dir() / "processed" / "precursor_analysis.parquet"
    if not path.exists():
        return {"error": "No precursor data"}

    try:
        df = pd.read_parquet(path)
        row = df[df["surge_id"] == surge_id]
        if row.empty:
            return {"error": f"Surge {surge_id} not found"}
        row = row.iloc[0]

        lead_h = float(row["lead_time_hours"]) if pd.notna(row.get("lead_time_hours")) else None

        return {
            "id": int(row["surge_id"]),
            "date": row.get("date", ""),
            "region": row.get("region", ""),
            "delegations": str(row.get("delegations", "")).split(","),
            "countries": str(row.get("countries", "")).split(","),
            "score": round(float(row.get("surge_score", 0)), 1),
            "acled": {
                "detected": bool(row.get("acled_detected", False)),
                "events": int(row.get("acled_events", 0)),
                "fatalities": int(row.get("acled_fatalities", 0)),
                "ratio": float(row.get("acled_ratio", 0)),
                "spike_onset": row.get("acled_spike_onset"),
            },
            "ioda": {
                "detected": bool(row.get("ioda_detected", False)),
                "alerts": int(row.get("ioda_alerts", 0)),
            },
            "cloudflare": {
                "detected": bool(row.get("cf_detected", False)),
                "events": int(row.get("cf_events", 0)),
            },
            "internal": {
                "detected": bool(row.get("internal_detected", False)),
                "latency_alerts": int(row.get("internal_latency_alerts", 0)),
            },
            "lead_time_h": lead_h,
        }
    except Exception:
        return {"error": "Failed to load surge data"}
