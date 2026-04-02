"""Forward-looking precursor alerts — detect emerging threats before outages hit.

Checks the last 48 hours of ACLED data against 30-day baselines.
If any ICRC delegation country shows conflict activity > 2× baseline,
emit a warning that network disruption may follow within 24-72 hours.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def check_forward_alerts(
    data_dir: Path,
    registry: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Check for precursor signals in the last 48 hours.

    Returns a list of warning dicts for countries where ACLED conflict
    activity exceeds 2× the 30-day baseline. Each warning includes
    the delegations at risk.
    """
    acled_path = data_dir / "processed" / "acled_events.parquet"
    if not acled_path.exists():
        logger.info("No ACLED parquet found; skipping forward alerts")
        return []

    try:
        acled_df = pd.read_parquet(acled_path)
    except Exception:
        return []

    if acled_df.empty or "event_date" not in acled_df.columns:
        return []

    # Build country → delegations mapping from registry (field regions only)
    field_regions = {"AFRICA East", "AFRICA West", "AMERICAS", "ASIA", "EURASIA", "NAME"}
    country_delegations: dict[str, list[str]] = {}  # country_name_lower → [delegation codes]
    country_names: dict[str, str] = {}  # lower → proper
    country_iso3: dict[str, str] = {}  # lower → iso3

    for code, entry in registry.items():
        region = entry.get("region", "")
        country = entry.get("country")
        iso3 = entry.get("country_iso3")
        if country and region in field_regions:
            key = country.lower()
            country_delegations.setdefault(key, []).append(code)
            country_names[key] = country
            if iso3:
                country_iso3[key] = iso3

    if not country_delegations:
        return []

    # Determine date boundaries
    dates = acled_df["event_date"].dropna()
    if dates.empty:
        return []

    max_date = max(dates)
    try:
        ref_date = date.fromisoformat(str(max_date)[:10])
    except ValueError:
        return []

    cutoff_48h = str(ref_date - timedelta(days=2))
    cutoff_30d = str(ref_date - timedelta(days=32))  # 30 days before the 48h window

    warnings: list[dict[str, Any]] = []

    for country_lower, deleg_codes in country_delegations.items():
        # Filter ACLED to this country
        country_events = acled_df[acled_df["country"].str.lower() == country_lower]
        if country_events.empty:
            continue

        # Events in last 48h
        recent = country_events[country_events["event_date"] >= cutoff_48h]
        recent_count = len(recent)

        # 30-day baseline (before the 48h window)
        baseline = country_events[
            (country_events["event_date"] >= cutoff_30d)
            & (country_events["event_date"] < cutoff_48h)
        ]
        baseline_count = len(baseline)
        baseline_avg_2d = baseline_count / max(30 / 2, 1)  # normalize to 2-day equivalent

        if baseline_avg_2d < 1:
            continue  # Not enough baseline data

        ratio = recent_count / baseline_avg_2d

        if ratio >= 2.0 and recent_count >= 5:
            country_name = country_names[country_lower]
            iso3 = country_iso3.get(country_lower, "")

            msg = (
                f"ACLED reports {ratio:.0f}x normal conflict activity in "
                f"{country_name} over the last 48h ({recent_count} events vs "
                f"{baseline_avg_2d:.0f} baseline). "
                f"Delegations at risk: {', '.join(sorted(deleg_codes))}. "
                f"Historical pattern suggests network disruption within 24-72h."
            )

            warnings.append({
                "country": country_name,
                "country_iso3": iso3,
                "delegations_at_risk": sorted(deleg_codes),
                "acled_events_48h": recent_count,
                "acled_baseline_avg": round(baseline_avg_2d, 1),
                "ratio": round(ratio, 1),
                "message": msg,
            })

            logger.warning("PRECURSOR: %s", msg)

    warnings.sort(key=lambda w: w["ratio"], reverse=True)
    if warnings:
        logger.info("Forward alerts: %d countries with precursor signals", len(warnings))
    return warnings
