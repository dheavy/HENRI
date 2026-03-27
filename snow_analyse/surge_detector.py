"""Regional cluster detection for FortigateSiteDown events."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def detect_surges(
    df: pd.DataFrame,
    registry: dict[str, Any],
    window_hours: int = 48,
) -> list[dict]:
    """Detect regional surges of FortigateSiteDown events.

    For each ICT region, finds time windows where multiple delegations
    experience site_down events simultaneously. Each cluster is scored by
    the number of affected delegations, total duration, and whether the
    cluster was preceded by WAN latency alerts.

    Parameters
    ----------
    df : pd.DataFrame
        Enriched incident DataFrame (must have ``alert_name``,
        ``delegation_code``, ``opened_dt``, ``alert_category`` columns).
    registry : dict
        Delegation registry keyed by site code, each value containing
        at minimum a ``"region"`` key.
    window_hours : int
        Rolling window size in hours for clustering events.

    Returns
    -------
    list[dict]
        Ranked list of surge events, each containing: ``region``,
        ``start_time``, ``end_time``, ``affected_delegations``,
        ``score``, ``preceded_by_latency``.
    """
    if df.empty:
        return []

    # Build delegation -> region lookup from registry
    del_to_region: dict[str, str] = {}
    for code, meta in registry.items():
        region = meta.get("region", "")
        if region:
            del_to_region[code.upper()] = region

    # Filter to FortigateSiteDown events with valid timestamps and delegation codes
    site_down = df[
        (df["alert_name"] == "FortigateSiteDown")
        & df["opened_dt"].notna()
        & df["delegation_code"].notna()
    ].copy()

    if site_down.empty:
        logger.info("No FortigateSiteDown events found")
        return []

    # Assign region from registry; fall back to dataframe column if present
    if "region" in site_down.columns:
        site_down["ict_region"] = site_down.apply(
            lambda r: del_to_region.get(str(r["delegation_code"]).upper(), r.get("region", "")),
            axis=1,
        )
    else:
        site_down["ict_region"] = site_down["delegation_code"].apply(
            lambda c: del_to_region.get(str(c).upper(), "")
        )

    site_down = site_down[site_down["ict_region"] != ""].copy()

    if site_down.empty:
        logger.info("No FortigateSiteDown events with a known region")
        return []

    site_down = site_down.sort_values("opened_dt")

    # Identify WAN latency events for precedence check
    wan_latency = df[
        (df["alert_category"] == "wan_degraded")
        & df["opened_dt"].notna()
        & df["delegation_code"].notna()
    ].copy()

    window_td = timedelta(hours=window_hours)
    surges: list[dict] = []

    for region, group in site_down.groupby("ict_region"):
        group = group.sort_values("opened_dt").reset_index(drop=True)
        events = list(group.itertuples(index=False))

        if len(events) < 2:
            continue

        # Sliding window clustering
        i = 0
        while i < len(events):
            cluster_start = events[i].opened_dt
            cluster_end = cluster_start
            affected: set[str] = {events[i].delegation_code}
            j = i + 1

            while j < len(events) and (events[j].opened_dt - cluster_start) <= window_td:
                affected.add(events[j].delegation_code)
                if events[j].opened_dt > cluster_end:
                    cluster_end = events[j].opened_dt
                j += 1

            if len(affected) >= 2:
                # Check if preceded by WAN latency in any affected delegation
                # within 24 hours before cluster start
                preceded = False
                if not wan_latency.empty:
                    lookback_start = cluster_start - timedelta(hours=24)
                    preceding_wan = wan_latency[
                        (wan_latency["opened_dt"] >= lookback_start)
                        & (wan_latency["opened_dt"] < cluster_start)
                        & (wan_latency["delegation_code"].isin(affected))
                    ]
                    preceded = not preceding_wan.empty

                duration_hours = max(
                    (cluster_end - cluster_start).total_seconds() / 3600, 0.1
                )

                # Score: weighted combination of delegation count, duration, latency flag
                score = (
                    len(affected) * 10
                    + duration_hours * 0.5
                    + (5 if preceded else 0)
                )

                surges.append(
                    {
                        "region": region,
                        "start_time": cluster_start,
                        "end_time": cluster_end,
                        "affected_delegations": sorted(affected),
                        "score": round(score, 2),
                        "preceded_by_latency": preceded,
                    }
                )

            # Advance past current cluster
            i = j if j > i + 1 else i + 1

    # Sort by score descending
    surges.sort(key=lambda s: s["score"], reverse=True)
    logger.info("Detected %d regional surge clusters", len(surges))
    return surges
