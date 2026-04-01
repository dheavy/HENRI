"""Delegation inventory endpoints."""

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
        return ""


@router.get("")
async def list_delegations(
    region: str | None = Query(None, pattern=r"^[A-Za-z ]+$"),
    search: str | None = Query(None, max_length=20),
) -> dict:
    """List all delegations with incident counts and metadata."""
    data_dir = _data_dir()
    reg_path = data_dir / "reference" / "delegations.json"
    if not reg_path.exists():
        return {"delegations": []}

    with open(reg_path) as f:
        registry = json.load(f)

    # Load circuits
    circuits: list[dict] = []
    circ_path = data_dir / "reference" / "circuits.json"
    if circ_path.exists():
        with open(circ_path) as f:
            circuits = json.load(f)
    circuits_by_parent: dict[str, list[dict]] = {}
    for c in circuits:
        parent = c.get("parent_code")
        if parent:
            circuits_by_parent.setdefault(parent, []).append({
                "cid": c.get("cid", ""),
                "provider": c.get("provider", ""),
                "commit_rate_fmt": c.get("commit_rate_fmt", ""),
            })

    # Load incident counts
    incident_counts = _incident_counts(data_dir)

    delegations: list[dict] = []
    for code, entry in registry.items():
        entry_region = entry.get("region") or ""
        country = entry.get("country") or ""
        iso3 = entry.get("country_iso3") or ""

        # Filters
        if region and entry_region.upper() != region.upper():
            continue
        if search:
            search_lower = search.lower()
            if (search_lower not in code.lower()
                    and search_lower not in country.lower()
                    and search_lower not in (entry.get("name") or "").lower()):
                continue

        counts = incident_counts.get(code, {})

        delegations.append({
            "site_code": code,
            "name": entry.get("name", code),
            "region": entry_region,
            "country": country,
            "country_iso2": _iso3_to_iso2(iso3),
            "source": entry.get("source", ""),
            "sub_sites": entry.get("sub_sites", []),
            "circuits": circuits_by_parent.get(code, []),
            "incident_count_30d": counts.get("total", 0),
            "sitedown_count_30d": counts.get("sitedown", 0),
            "dominant_alert": counts.get("dominant", "N/A"),
        })

    delegations.sort(key=lambda d: d["incident_count_30d"], reverse=True)
    return {"delegations": delegations, "total": len(delegations)}


@router.get("/{site_code}")
async def delegation_detail(site_code: str) -> dict:
    """Get detail for a single delegation."""
    site_code = site_code.upper()
    if not site_code.isalnum() or len(site_code) > 10:
        raise HTTPException(404, "Not found")

    data_dir = _data_dir()
    reg_path = data_dir / "reference" / "delegations.json"
    if not reg_path.exists():
        raise HTTPException(404, "Not found")

    with open(reg_path) as f:
        registry = json.load(f)

    entry = registry.get(site_code)
    if not entry:
        raise HTTPException(404, "Not found")

    # Circuits for this delegation
    circuits: list[dict] = []
    circ_path = data_dir / "reference" / "circuits.json"
    if circ_path.exists():
        with open(circ_path) as f:
            all_circuits = json.load(f)
        circuits = [c for c in all_circuits if c.get("parent_code") == site_code]

    iso3 = entry.get("country_iso3", "")

    return {
        "site_code": site_code,
        "name": entry.get("name", site_code),
        "region": entry.get("region", ""),
        "country": entry.get("country", ""),
        "country_iso2": _iso3_to_iso2(iso3),
        "source": entry.get("source", ""),
        "sub_sites": entry.get("sub_sites", []),
        "latitude": entry.get("latitude"),
        "longitude": entry.get("longitude"),
        "circuits": circuits,
    }


def _incident_counts(data_dir: Path) -> dict[str, dict]:
    """Get incident counts per parent delegation code."""
    path = data_dir / "processed" / "incidents_all.parquet"
    if not path.exists():
        return {}
    try:
        df = pd.read_parquet(path)
        code_col = "parent_code" if "parent_code" in df.columns else "delegation_code"
        if code_col not in df.columns:
            return {}

        result: dict[str, dict] = {}
        for code, group in df.groupby(code_col):
            if pd.isna(code):
                continue
            code_str = str(code).upper()
            dominant = group["alert_name"].value_counts()
            sitedown = int((group["alert_name"] == "FortigateSiteDown").sum())
            result[code_str] = {
                "total": len(group),
                "sitedown": sitedown,
                "dominant": dominant.index[0] if not dominant.empty else "N/A",
            }
        return result
    except Exception:
        return {}
