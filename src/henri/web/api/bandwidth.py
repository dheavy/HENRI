"""Bandwidth scorecard endpoint — UC-1: actual vs contracted capacity."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter

router = APIRouter()
logger = logging.getLogger(__name__)


def _data_dir() -> Path:
    return Path(os.getenv("DATA_DIR", "./data"))


@router.get("")
async def bandwidth_scorecard() -> dict:
    """Bandwidth utilisation scorecard for all field sites."""
    data_dir = _data_dir()

    # Load registry
    reg_path = data_dir / "reference" / "delegations.json"
    registry = {}
    if reg_path.exists():
        with open(reg_path) as f:
            registry = json.load(f)

    hq_sites = {k for k, v in registry.items() if v.get("region") == "HQ"}

    # Load bandwidth
    bw_path = data_dir / "processed" / "bandwidth_by_site.parquet"
    if not bw_path.exists():
        return {"sites": [], "summary": _empty_summary()}

    df = pd.read_parquet(bw_path)
    df = df[~df["site"].isin(hq_sites)]
    if df.empty:
        return {"sites": [], "summary": _empty_summary()}

    # Load circuits for commit_rate
    circuits: list[dict] = []
    circ_path = data_dir / "reference" / "circuits.json"
    if circ_path.exists():
        with open(circ_path) as f:
            circuits = json.load(f)

    # Build per-parent commit_rate and circuit details
    circuits_by_parent: dict[str, list[dict]] = {}
    for c in circuits:
        parent = c.get("parent_code")
        if not parent:
            continue
        rate_kbps = c.get("commit_rate_kbps")
        circuits_by_parent.setdefault(parent, []).append({
            "cid": c.get("cid", ""),
            "provider": c.get("provider", ""),
            "type": c.get("circuit_type", ""),
            "commit_rate_mbps": round(rate_kbps / 1000, 2) if rate_kbps else None,
        })

    # Aggregate bandwidth per site
    site_agg = df.groupby("site").agg(
        avg_bps=("avg_bps", "mean"),
        peak_bps=("peak_bps", "max"),
        p95_bps=("p95_bps", "mean"),
    ).reset_index()

    # Also compute directional averages
    in_df = df[df["direction"] == "in"].groupby("site")["avg_bps"].mean().reset_index()
    in_df.columns = ["site", "avg_in_bps"]
    out_df = df[df["direction"] == "out"].groupby("site")["avg_bps"].mean().reset_index()
    out_df.columns = ["site", "avg_out_bps"]
    site_agg = site_agg.merge(in_df, on="site", how="left").merge(out_df, on="site", how="left")

    sites: list[dict] = []
    over_utilised: list[dict] = []
    under_utilised: list[dict] = []
    zero_traffic: list[dict] = []
    sites_with_util = 0

    for _, row in site_agg.iterrows():
        site = row["site"]
        entry = registry.get(site, {})
        peak_mbps = round(row["peak_bps"] / 1e6, 2)
        avg_in = round(row.get("avg_in_bps", 0) / 1e6, 2) if pd.notna(row.get("avg_in_bps")) else 0
        avg_out = round(row.get("avg_out_bps", 0) / 1e6, 2) if pd.notna(row.get("avg_out_bps")) else 0
        p95_mbps = round(row["p95_bps"] / 1e6, 2)

        # Calculate utilisation against highest commit_rate for this site
        site_circuits = circuits_by_parent.get(site, [])
        max_commit_mbps = max(
            (c["commit_rate_mbps"] for c in site_circuits if c["commit_rate_mbps"]),
            default=None,
        )

        util_pct = None
        if max_commit_mbps and max_commit_mbps > 0:
            util_pct = round(peak_mbps / max_commit_mbps * 100, 1)
            sites_with_util += 1

        # Enrich circuits with utilisation
        for c in site_circuits:
            if c["commit_rate_mbps"] and c["commit_rate_mbps"] > 0:
                c["utilisation_pct"] = round(peak_mbps / c["commit_rate_mbps"] * 100, 1)
            else:
                c["utilisation_pct"] = None

        site_info = {
            "site_code": site,
            "region": entry.get("region", ""),
            "country": entry.get("country", ""),
            "avg_mbps_in": avg_in,
            "avg_mbps_out": avg_out,
            "peak_mbps": peak_mbps,
            "p95_mbps": p95_mbps,
            "utilisation_pct": util_pct,
            "circuits": site_circuits,
        }
        sites.append(site_info)

        if util_pct is not None and util_pct > 80:
            over_utilised.append({"site": site, "pct": util_pct,
                                  "provider": site_circuits[0]["provider"] if site_circuits else ""})
        elif util_pct is not None and util_pct < 10:
            under_utilised.append({"site": site, "pct": util_pct,
                                   "provider": site_circuits[0]["provider"] if site_circuits else ""})

        if peak_mbps < 0.01:
            zero_traffic.append({"site": site, "region": entry.get("region", "")})

    sites.sort(key=lambda s: s["peak_mbps"], reverse=True)

    return {
        "sites": sites,
        "summary": {
            "sites_with_bandwidth": len(sites),
            "sites_with_utilisation": sites_with_util,
            "over_utilised": sorted(over_utilised, key=lambda x: x["pct"], reverse=True),
            "under_utilised": sorted(under_utilised, key=lambda x: x["pct"]),
            "zero_traffic": zero_traffic,
        },
    }


def _empty_summary() -> dict:
    return {
        "sites_with_bandwidth": 0,
        "sites_with_utilisation": 0,
        "over_utilised": [],
        "under_utilised": [],
        "zero_traffic": [],
    }
