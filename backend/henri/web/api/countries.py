"""Country endpoints — risk table and country drill-down."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import pandas as pd
import pycountry
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()
logger = logging.getLogger(__name__)


def _data_dir() -> Path:
    return Path(os.getenv("DATA_DIR", "./data"))


def _iso3_to_iso2(iso3: str) -> str:
    try:
        return pycountry.countries.get(alpha_3=iso3).alpha_2.lower()
    except (AttributeError, LookupError):
        return iso3.lower()[:2]


def _load_risk_cards() -> list[dict]:
    path = _data_dir() / "processed" / "risk_scores.json"
    if not path.exists():
        return []
    with open(path) as f:
        data = json.load(f)
    return data.get("cards", [])


def _load_registry() -> dict:
    path = _data_dir() / "reference" / "delegations.json"
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _enrich_card(card: dict, registry: dict) -> dict:
    """Add delegation list and iso2 to a risk card."""
    iso3 = card.get("country_iso3", "")
    iso2 = _iso3_to_iso2(iso3)

    # Find delegations for this country
    delegations = []
    for code, entry in registry.items():
        if entry.get("country_iso3") == iso3:
            delegations.append(code)

    # Risk tier
    score = card.get("combined_risk", 0)
    if score >= 70:
        tier = "high"
    elif score >= 50:
        tier = "medium"
    elif score >= 25:
        tier = "low"
    else:
        tier = "minimal"

    return {
        "iso2": iso2,
        "iso3": iso3,
        "name": card.get("country", ""),
        "risk_score": score,
        "risk_tier": tier,
        "acled_events": card.get("acled_events", 0),
        "acled_fatalities": card.get("acled_fatalities", 0),
        "acled_trend": card.get("acled_trend", "n/a"),
        "ioda_score": card.get("ioda_score", 0),
        "cf_outages": card.get("cf_outages", 0),
        "snow_sitedown": card.get("snow_sitedown", 0),
        "delegations": sorted(delegations),
    }


@router.get("")
async def list_countries(
    sort: str = Query("risk_score", pattern="^(risk_score|name|acled_events|snow_sitedown)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    tier: str | None = Query(None, pattern="^(high|medium|low|minimal)(,(high|medium|low|minimal))*$"),
) -> dict:
    """List all ICRC field countries with risk scores."""
    cards = _load_risk_cards()
    registry = _load_registry()
    countries = [_enrich_card(c, registry) for c in cards]

    # Filter by tier
    if tier:
        allowed = set(tier.split(","))
        countries = [c for c in countries if c["risk_tier"] in allowed]

    # Sort
    reverse = order == "desc"
    countries.sort(key=lambda c: c.get(sort, 0) or 0, reverse=reverse)

    return {"countries": countries}


@router.get("/{iso2}")
async def country_detail(iso2: str) -> dict:
    """Deep drill-down for a single country."""
    iso2 = iso2.upper()
    if len(iso2) != 2 or not iso2.isalpha():
        raise HTTPException(404, "Not found")

    # Resolve iso2 → iso3
    try:
        country_obj = pycountry.countries.get(alpha_2=iso2)
        if not country_obj:
            raise HTTPException(404, "Not found")
        iso3 = country_obj.alpha_3
        country_name = country_obj.name
    except LookupError:
        raise HTTPException(404, "Not found")

    data_dir = _data_dir()
    registry = _load_registry()

    # Find risk card
    cards = _load_risk_cards()
    card = next((c for c in cards if c.get("country_iso3") == iso3), None)
    if not card:
        raise HTTPException(404, "Not found")

    enriched = _enrich_card(card, registry)

    # ACLED timeline (last 90 days, daily)
    acled_timeline = _acled_timeline(data_dir, country_name)

    # ServiceNow incidents per delegation
    snow_incidents = _snow_by_delegation(data_dir, registry, iso3)

    # Surges affecting this country's delegations
    surges = _surges_for_country(data_dir, registry, iso3)

    return {
        "country": enriched,
        "acled_timeline": acled_timeline,
        "servicenow_incidents": snow_incidents,
        "surges": surges,
    }


def _acled_timeline(data_dir: Path, country_name: str) -> list[dict]:
    """Daily ACLED event counts for a country."""
    path = data_dir / "processed" / "acled_events.parquet"
    if not path.exists():
        return []
    try:
        df = pd.read_parquet(path)
        country_df = df[df["country"].str.lower() == country_name.lower()]
        if country_df.empty:
            return []
        daily = (
            country_df.groupby("event_date")
            .agg(events=("event_date", "size"),
                 fatalities=("fatalities", lambda x: int(x.fillna(0).astype(int).sum())))
            .reset_index()
            .sort_values("event_date")
            .tail(90)
        )
        return daily.to_dict("records")
    except Exception:
        return []


def _snow_by_delegation(data_dir: Path, registry: dict, iso3: str) -> list[dict]:
    """ServiceNow incident counts per delegation for a country."""
    path = data_dir / "processed" / "incidents_all.parquet"
    if not path.exists():
        return []
    try:
        df = pd.read_parquet(path)
        code_col = "parent_code" if "parent_code" in df.columns else "delegation_code"
        # Find delegation codes for this country
        codes = {c for c, e in registry.items() if e.get("country_iso3") == iso3}
        if not codes:
            return []
        subset = df[df[code_col].isin(codes)]
        if subset.empty:
            return []
        grouped = subset.groupby(code_col).agg(
            total=("number", "size"),
            sitedown=("alert_name", lambda x: (x == "FortigateSiteDown").sum()),
        ).reset_index()
        grouped.columns = ["delegation", "total", "sitedown"]
        # Dominant alert per delegation
        result = []
        for _, row in grouped.iterrows():
            deleg = row["delegation"]
            deleg_df = subset[subset[code_col] == deleg]
            dominant = deleg_df["alert_name"].value_counts()
            result.append({
                "delegation": deleg,
                "total_incidents": int(row["total"]),
                "sitedown_count": int(row["sitedown"]),
                "dominant_alert": dominant.index[0] if not dominant.empty else "N/A",
            })
        result.sort(key=lambda r: r["total_incidents"], reverse=True)
        return result
    except Exception:
        return []


def _surges_for_country(data_dir: Path, registry: dict, iso3: str) -> list[dict]:
    """Surge events that affected delegations in this country."""
    path = data_dir / "processed" / "precursor_analysis.parquet"
    if not path.exists():
        return []
    try:
        df = pd.read_parquet(path)
        # Find delegation codes for this country
        codes = {c for c, e in registry.items() if e.get("country_iso3") == iso3}
        matching = []
        for _, row in df.iterrows():
            delegs = str(row.get("delegations", "")).split(",")
            if codes & set(delegs):
                matching.append({
                    "surge_id": int(row.get("surge_id", 0)),
                    "date": row.get("date", ""),
                    "region": row.get("region", ""),
                    "score": float(row.get("surge_score", 0)),
                    "acled_detected": bool(row.get("acled_detected", False)),
                    "cf_detected": bool(row.get("cf_detected", False)),
                    "ioda_detected": bool(row.get("ioda_detected", False)),
                    "lead_time_hours": float(row["lead_time_hours"]) if pd.notna(row.get("lead_time_hours")) else None,
                })
        return matching[:20]
    except Exception:
        return []
