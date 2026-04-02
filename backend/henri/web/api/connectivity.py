"""Connectivity quality endpoint — ETU (Effective Throughput per User) scoring."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter

from henri.etu.calculator import compute_etu

router = APIRouter()
logger = logging.getLogger(__name__)


def _data_dir() -> Path:
    return Path(os.getenv("DATA_DIR", "./data"))


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _build_site_links(
    site_code: str,
    circuits: list[dict],
    bandwidth: dict[str, dict],
) -> list[dict]:
    """Build link dicts for a site by joining NetBox circuits with Grafana bandwidth."""
    site_circuits = [c for c in circuits if c.get("parent_code") == site_code]
    bw = bandwidth.get(site_code, {})

    if site_circuits:
        links = []
        for i, c in enumerate(site_circuits):
            links.append({
                "cid": c.get("cid", f"{site_code}ISP{i+1}"),
                "link_type": c.get("circuit_type") or None,
                "provider": c.get("provider") or None,
                "committed_rate_kbps": c.get("commit_rate_kbps"),
                "measured_peak_bps": bw.get("peak_bps") if i == 0 else None,
                "measured_rtt_ms": None,  # no blackbox exporter yet
                "packet_loss_ratio": None,  # no blackbox exporter yet
                "is_primary": i == 0,
            })
        return links

    # No NetBox circuits — create a synthetic link from Grafana bandwidth alone
    if bw:
        return [{
            "cid": f"{site_code}ISP1",
            "link_type": None,
            "provider": None,
            "committed_rate_kbps": None,
            "measured_peak_bps": bw.get("peak_bps"),
            "measured_rtt_ms": None,
            "packet_loss_ratio": None,
            "is_primary": True,
        }]

    return []


def _compute_availability(
    site_code: str,
    sub_sites: list[str],
    incidents_df: pd.DataFrame | None,
    days: int = 90,
) -> float | None:
    """Estimate availability from FortigateSiteDown incident frequency."""
    if incidents_df is None or incidents_df.empty:
        return None

    all_codes = [site_code] + sub_sites
    site_incidents = incidents_df[
        (incidents_df["parent_code"].isin(all_codes))
        & (incidents_df["alert_name"] == "FortigateSiteDown")
    ]

    if site_incidents.empty:
        return None

    count = len(site_incidents)
    # Rough estimate: each FortigateSiteDown ~4h average downtime
    estimated_downtime_hours = count * 4
    total_hours = days * 24
    ratio = max(0.0, 1.0 - estimated_downtime_hours / total_hours)
    return round(ratio, 4)


def _identify_limiting_factor(result: Any) -> str:
    """Identify which component drags the score down the most."""
    if result.num_links == 0:
        return "No data"

    factors: list[tuple[str, float]] = []

    if result.availability_penalty < 0.9:
        factors.append(("Availability", result.availability_penalty))

    if result.jitter_penalty < 0.8:
        factors.append(("Jitter", result.jitter_penalty))

    # Check if Mathis throughput is limiting
    for link in result.links:
        if link.capacity_bps and link.mathis_bps < link.capacity_bps * 0.5:
            if link.rtt_ms > 100:
                factors.append(("Latency", link.mathis_bps / (link.capacity_bps or 1)))
            else:
                factors.append(("Loss", link.mathis_bps / (link.capacity_bps or 1)))

    if factors:
        factors.sort(key=lambda x: x[1])
        return factors[0][0]

    # If raw ETU is already low, check why
    if result.etu_raw_mbps < 0.1:
        if result.num_users > 20:
            return "Users"
        return "Bandwidth"

    return "\u2014"


@router.get("")
async def connectivity_scores() -> dict:
    """ETU connectivity quality scores for all field sites."""
    data_dir = _data_dir()

    # Load delegation registry
    registry: dict = _load_json(data_dir / "reference" / "delegations.json") or {}
    hq_sites = {k for k, v in registry.items() if v.get("region") == "HQ"}

    # Load circuits
    circuits: list[dict] = _load_json(data_dir / "reference" / "circuits.json") or []

    # Load bandwidth
    bw_path = data_dir / "processed" / "bandwidth_by_site.parquet"
    bandwidth: dict[str, dict] = {}
    if bw_path.exists():
        try:
            df_bw = pd.read_parquet(bw_path)
            for _, row in df_bw.groupby("site").agg(
                peak_bps=("peak_bps", "max"),
                avg_bps=("avg_bps", "mean"),
            ).reset_index().iterrows():
                bandwidth[row["site"]] = {
                    "peak_bps": float(row["peak_bps"]),
                    "avg_bps": float(row["avg_bps"]),
                }
        except Exception as e:
            logger.warning("Failed to load bandwidth data: %s", e)

    # Load incidents for availability estimation
    inc_path = data_dir / "processed" / "incidents_all.parquet"
    incidents_df = None
    if inc_path.exists():
        try:
            incidents_df = pd.read_parquet(
                inc_path,
                columns=["parent_code", "alert_name"],
            )
        except Exception as e:
            logger.warning("Failed to load incidents: %s", e)

    # Coverage counters
    has_bandwidth = 0
    has_circuits = 0
    has_rtt = 0
    has_loss = 0
    has_jitter = 0
    has_dhcp = 0
    has_availability = 0
    full_data = 0

    sites_output: list[dict] = []
    grade_counts: dict[str, int] = {
        "Excellent": 0, "Good": 0, "Adequate": 0,
        "Degraded": 0, "Critical": 0, "No data": 0,
    }
    total_completeness = 0.0
    scored_count = 0

    field_sites = {k: v for k, v in registry.items() if k not in hq_sites}

    for site_code, meta in field_sites.items():
        sub_sites = meta.get("sub_sites", [])

        # Check what data we have
        site_has_bw = site_code in bandwidth
        site_circuits = [c for c in circuits if c.get("parent_code") == site_code]
        site_has_circuits = len(site_circuits) > 0

        if site_has_bw:
            has_bandwidth += 1
        if site_has_circuits:
            has_circuits += 1

        # Build links
        links = _build_site_links(site_code, circuits, bandwidth)
        if not links:
            continue

        # Availability from FortigateSiteDown
        avail = _compute_availability(site_code, sub_sites, incidents_df)
        if avail is not None:
            has_availability += 1

        # No DHCP or jitter data currently available
        dhcp_count = None
        jitter = None

        result = compute_etu(
            site_code=site_code,
            links=links,
            dhcp_lease_count=dhcp_count,
            jitter_ms=jitter,
            availability_ratio=avail,
        )

        # Track coverage
        for link in result.links:
            if link.rtt_source == "measured":
                has_rtt += 1
                break
        for link in result.links:
            if link.loss_source == "measured":
                has_loss += 1
                break

        # Check if site has full data
        site_missing = set(result.missing_data)
        if not site_missing - {"jitter"}:  # jitter is expected to be missing for all
            full_data += 1

        grade_counts[result.grade] = grade_counts.get(result.grade, 0) + 1
        total_completeness += result.data_completeness
        scored_count += 1

        limiting = _identify_limiting_factor(result)

        sites_output.append({
            "site_code": site_code,
            "country": meta.get("country", ""),
            "region": meta.get("region", ""),
            "score": result.score,
            "grade": result.grade,
            "etu_mbps": round(result.etu_mbps, 3),
            "etu_raw_mbps": round(result.etu_raw_mbps, 3),
            "num_users": result.num_users,
            "num_users_source": result.num_users_source,
            "num_links": result.num_links,
            "jitter_penalty": round(result.jitter_penalty, 3),
            "availability_penalty": round(result.availability_penalty, 3),
            "diversity_bonus": round(result.diversity_bonus, 2),
            "data_completeness": round(result.data_completeness, 2),
            "missing_data": result.missing_data,
            "limiting_factor": limiting,
            "links": [
                {
                    "cid": l.cid,
                    "link_type": l.link_type,
                    "provider": l.provider,
                    "effective_mbps": round(l.effective_bps / 1e6, 3),
                    "mathis_mbps": round(l.mathis_bps / 1e6, 3),
                    "capacity_mbps": round(l.capacity_bps / 1e6, 3) if l.capacity_bps else None,
                    "rtt_ms": round(l.rtt_ms, 1),
                    "rtt_source": l.rtt_source,
                    "loss": round(l.loss, 5),
                    "loss_source": l.loss_source,
                    "is_primary": l.is_primary,
                }
                for l in result.links
            ],
        })

    # Sort by score ascending (worst first)
    sites_output.sort(key=lambda s: s["score"])

    # Remove "No data" from grade counts for summary
    grade_counts.pop("No data", None)

    total_field = len(field_sites)
    avg_comp = total_completeness / scored_count if scored_count > 0 else 0.0

    return {
        "sites": sites_output,
        "summary": {
            "total_sites": total_field,
            "scored_sites": scored_count,
            "by_grade": grade_counts,
            "avg_completeness": round(avg_comp, 2),
        },
        "coverage": {
            "has_bandwidth": has_bandwidth,
            "has_circuits": has_circuits,
            "has_rtt": has_rtt,
            "has_loss": has_loss,
            "has_jitter": has_jitter,
            "has_dhcp": has_dhcp,
            "has_availability": has_availability,
            "full_data": full_data,
            "total_sites": total_field,
        },
    }
