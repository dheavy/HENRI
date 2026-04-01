"""Data coherence endpoint — UC-3: cross-reference inventory gaps."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pandas as pd
from fastapi import APIRouter

router = APIRouter()
logger = logging.getLogger(__name__)


def _data_dir() -> Path:
    return Path(os.getenv("DATA_DIR", "./data"))


@router.get("")
async def coherence() -> dict:
    """Data coherence report: inventory gaps across sources."""
    data_dir = _data_dir()

    # Load all reference data
    registry = _load(data_dir / "reference" / "delegations.json") or {}
    subsite_map = _load(data_dir / "reference" / "subsite_map.json") or {}
    nb_site_map = _load(data_dir / "reference" / "netbox_site_map.json") or {}
    circuits = _load(data_dir / "reference" / "circuits.json") or []

    grafana_codes = {k for k, v in registry.items() if v.get("source", "").startswith("grafana")}
    all_grafana_codes = set(subsite_map.keys())  # includes sub-sites
    nb_matched = set(nb_site_map.keys())

    # 1. NetBox coverage
    netbox_coverage = {
        "matched": len(nb_matched & grafana_codes),
        "total_grafana": len(grafana_codes),
        "pct": round(len(nb_matched & grafana_codes) / max(len(grafana_codes), 1) * 100),
    }

    # 2. Commit rate coverage
    circuits_with_rate = sum(1 for c in circuits if c.get("commit_rate_kbps"))
    commit_rate_coverage = {
        "with_rate": circuits_with_rate,
        "total_circuits": len(circuits),
        "pct": round(circuits_with_rate / max(len(circuits), 1) * 100),
    }

    # 3. Grafana sites NOT in NetBox
    grafana_not_in_netbox = sorted(grafana_codes - nb_matched)

    # 4. NetBox circuit sites NOT in Grafana
    circuit_sites = {c.get("site_code") for c in circuits if c.get("site_code")}
    netbox_not_in_grafana = sorted(circuit_sites - all_grafana_codes)

    # 5. Sites with zero incidents in 90 days
    zero_incident_sites: list[str] = []
    incidents_path = data_dir / "processed" / "incidents_all.parquet"
    if incidents_path.exists():
        try:
            df = pd.read_parquet(incidents_path)
            code_col = "parent_code" if "parent_code" in df.columns else "delegation_code"
            codes_with_incidents = set(df[code_col].dropna().unique())
            zero_incident_sites = sorted(grafana_codes - codes_with_incidents)
        except Exception:
            pass

    # 6. ServiceNow codes not in Grafana registry
    snow_orphan_codes: list[str] = []
    if incidents_path.exists():
        try:
            df = pd.read_parquet(incidents_path)
            code_col = "parent_code" if "parent_code" in df.columns else "delegation_code"
            snow_codes = set(df[code_col].dropna().unique())
            all_registry_codes = set(registry.keys())
            snow_orphan_codes = sorted(snow_codes - all_registry_codes - all_grafana_codes)
        except Exception:
            pass

    return {
        "netbox_coverage": netbox_coverage,
        "commit_rate_coverage": commit_rate_coverage,
        "grafana_not_in_netbox": grafana_not_in_netbox,
        "netbox_not_in_grafana": netbox_not_in_grafana,
        "zero_incident_sites": zero_incident_sites,
        "snow_orphan_codes": snow_orphan_codes,
    }


def _load(path: Path):
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)
