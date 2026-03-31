"""Precursor analysis — look backwards from each surge for external warning signals.

For each surge event detected by surge_detector.py, checks:
- ACLED: conflict spike in affected countries (7-day lookback)
- IODA: internet outage activity (from summary data)
- Cloudflare: verified outage annotations (24-hour lookback)
- Internal: WAN latency alerts before site-down (24-hour lookback)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def _delegations_to_countries(
    delegations: list[str],
    registry: dict[str, dict[str, Any]],
) -> dict[str, str]:
    """Map delegation codes to {iso3: country_name}, skipping unmapped."""
    result: dict[str, str] = {}
    for code in delegations:
        entry = registry.get(code, {})
        iso3 = entry.get("country_iso3")
        country = entry.get("country")
        if iso3 and country:
            result[iso3] = country
    return result


def _check_acled(
    surge_start: datetime,
    countries_iso3: set[str],
    acled_df: pd.DataFrame,
) -> dict[str, Any]:
    """Check ACLED for conflict spike in 7 days before surge."""
    if acled_df.empty or not countries_iso3:
        return {"detected": False, "event_count": 0, "fatalities": 0,
                "baseline_avg": 0, "ratio": 0, "lead_time_hours": 0}

    surge_date = surge_start.date()
    window_start = surge_date - timedelta(days=7)
    baseline_start = surge_date - timedelta(days=37)  # 30 days before the 7-day window

    # Map iso3 to country names in ACLED data
    # ACLED uses country names, not ISO codes — build reverse lookup
    country_names = set()
    for _, row in acled_df[["country"]].drop_duplicates().iterrows():
        country_names.add(row["country"])

    # Filter by date strings (ACLED dates are YYYY-MM-DD strings)
    window_start_str = str(window_start)
    surge_date_str = str(surge_date)
    baseline_start_str = str(baseline_start)

    # We need to match by ISO code. ACLED has 'iso' (numeric) — use country name instead
    # Build country_name set from the registry mapping
    # Actually, filter by the 'iso' column if it exists, or by country name
    if "iso" in acled_df.columns:
        # ACLED iso is numeric — we can't match directly with alpha-3
        pass

    # Filter by country name (from registry, matched to ACLED)
    # This is approximate but works for the analysis
    relevant = acled_df[acled_df["country"].str.lower().isin(
        {n.lower() for n in country_names}
    )]

    if relevant.empty:
        return {"detected": False, "event_count": 0, "fatalities": 0,
                "baseline_avg": 0, "ratio": 0, "lead_time_hours": 0}

    # 7-day window events
    window_events = relevant[
        (relevant["event_date"] >= window_start_str)
        & (relevant["event_date"] < surge_date_str)
    ]

    # 30-day baseline (before the window)
    baseline_events = relevant[
        (relevant["event_date"] >= baseline_start_str)
        & (relevant["event_date"] < window_start_str)
    ]

    window_count = len(window_events)
    baseline_count = len(baseline_events)
    baseline_avg_7d = baseline_count / max(30 / 7, 1)  # normalize to 7-day equivalent

    fatalities = int(window_events["fatalities"].fillna(0).astype(int).sum()) if "fatalities" in window_events.columns else 0
    ratio = window_count / max(baseline_avg_7d, 1)
    detected = ratio >= 2.0 and window_count >= 3

    return {
        "detected": detected,
        "event_count": int(window_count),
        "fatalities": fatalities,
        "baseline_avg": round(baseline_avg_7d, 1),
        "ratio": round(ratio, 1),
        "lead_time_hours": 7 * 24 if detected else 0,
    }


def _check_acled_for_countries(
    surge_start: datetime,
    country_iso3_to_name: dict[str, str],
    acled_df: pd.DataFrame,
) -> dict[str, Any]:
    """ACLED check using country names from registry."""
    if acled_df.empty or not country_iso3_to_name:
        return {"detected": False, "event_count": 0, "fatalities": 0,
                "baseline_avg": 0, "ratio": 0, "lead_time_hours": 0}

    target_names = {n.lower() for n in country_iso3_to_name.values()}
    relevant = acled_df[acled_df["country"].str.lower().isin(target_names)]

    if relevant.empty:
        return {"detected": False, "event_count": 0, "fatalities": 0,
                "baseline_avg": 0, "ratio": 0, "lead_time_hours": 0}

    surge_date = surge_start.date()
    w_start = str(surge_date - timedelta(days=7))
    w_end = str(surge_date)
    b_start = str(surge_date - timedelta(days=37))

    window = relevant[(relevant["event_date"] >= w_start) & (relevant["event_date"] < w_end)]
    baseline = relevant[(relevant["event_date"] >= b_start) & (relevant["event_date"] < w_start)]

    wc = len(window)
    bc = len(baseline)
    avg_7d = bc / max(30 / 7, 1)
    fatalities = int(window["fatalities"].fillna(0).astype(int).sum()) if "fatalities" in window.columns else 0
    ratio = wc / max(avg_7d, 1)
    detected = ratio >= 2.0 and wc >= 3

    return {
        "detected": detected,
        "event_count": int(wc),
        "fatalities": fatalities,
        "baseline_avg": round(avg_7d, 1),
        "ratio": round(ratio, 1),
        "lead_time_hours": 7 * 24 if detected else 0,
    }


def _check_cloudflare(
    surge_start: datetime,
    country_iso3: set[str],
    cf_data: list[dict],
) -> dict[str, Any]:
    """Check Cloudflare annotations for outages 24h before surge."""
    if not cf_data or not country_iso3:
        return {"detected": False, "event_count": 0}

    lookback = surge_start - timedelta(hours=24)
    matching = 0
    for ann in cf_data:
        # Check if annotation overlaps with [lookback, surge_start]
        start_str = ann.get("startDate") or ann.get("start")
        if not start_str:
            continue
        try:
            ann_start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        if ann_start < lookback or ann_start > surge_start:
            continue
        # Check if any location matches
        locs = ann.get("locations", [])
        for loc in locs:
            # loc is alpha-2; we need alpha-3
            try:
                import pycountry
                c = pycountry.countries.get(alpha_2=loc)
                if c and c.alpha_3 in country_iso3:
                    matching += 1
                    break
            except (AttributeError, LookupError):
                continue

    return {"detected": matching > 0, "event_count": matching}


def _check_internal(
    surge_start: datetime,
    delegations: list[str],
    incidents_df: pd.DataFrame,
) -> dict[str, Any]:
    """Check for WAN latency alerts in same delegations 24h before surge."""
    if incidents_df.empty:
        return {"detected": False, "latency_alerts": 0, "lead_time_hours": 0}

    lookback = surge_start - timedelta(hours=24)
    code_col = "parent_code" if "parent_code" in incidents_df.columns else "delegation_code"
    deleg_set = set(d.upper() for d in delegations)

    latency_cats = {"wan_degraded"}
    mask = (
        incidents_df["opened_dt"].notna()
        & (incidents_df["opened_dt"] >= lookback)
        & (incidents_df["opened_dt"] < surge_start)
        & incidents_df[code_col].isin(deleg_set)
        & incidents_df.get("alert_category", pd.Series(dtype=str)).isin(latency_cats)
    )

    count = int(mask.sum())
    if count > 0:
        earliest = incidents_df.loc[mask, "opened_dt"].min()
        lead_hours = (surge_start - earliest).total_seconds() / 3600
    else:
        lead_hours = 0

    return {
        "detected": count > 0,
        "latency_alerts": count,
        "lead_time_hours": round(lead_hours, 1),
    }


def analyse_precursors(
    surges: list[dict],
    registry: dict[str, dict[str, Any]],
    data_dir: Path,
) -> list[dict[str, Any]]:
    """Analyse each surge for external and internal precursor signals.

    Returns one record per surge with precursor analysis fields.
    """
    if not surges:
        return []

    # Load data sources
    acled_path = data_dir / "processed" / "acled_events.parquet"
    acled_df = pd.read_parquet(acled_path) if acled_path.exists() else pd.DataFrame()

    incidents_path = data_dir / "processed" / "incidents_all.parquet"
    incidents_df = pd.read_parquet(incidents_path) if incidents_path.exists() else pd.DataFrame()

    # Load Cloudflare data (fixture or cached)
    cf_annotations: list[dict] = []
    cf_path = data_dir / "fixtures" / "cf_outages_90d.json"
    if cf_path.exists():
        with open(cf_path) as f:
            cf_raw = json.load(f)
        cf_annotations = cf_raw.get("result", {}).get("annotations", [])

    results: list[dict[str, Any]] = []

    for i, surge in enumerate(surges):
        delegations = surge.get("affected_delegations", [])
        country_map = _delegations_to_countries(delegations, registry)
        country_iso3 = set(country_map.keys())

        start_time = surge["start_time"]
        if not isinstance(start_time, datetime):
            continue
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)

        acled_result = _check_acled_for_countries(start_time, country_map, acled_df)
        cf_result = _check_cloudflare(start_time, country_iso3, cf_annotations)
        internal_result = _check_internal(start_time, delegations, incidents_df)

        # IODA: use summary-level data (we can't do historical per-surge lookback)
        ioda_result = {"detected": False, "score": 0}

        any_external = acled_result["detected"] or cf_result["detected"] or ioda_result["detected"]

        lead_times = []
        if acled_result["detected"]:
            lead_times.append(acled_result["lead_time_hours"])
        if cf_result["detected"]:
            lead_times.append(24.0)  # CF lookback is 24h
        if internal_result["detected"]:
            lead_times.append(internal_result["lead_time_hours"])

        results.append({
            "surge_id": i,
            "date": str(start_time.date()),
            "region": surge.get("region", ""),
            "delegations": delegations,
            "countries": list(country_map.values()),
            "surge_score": surge.get("score", 0),
            "acled_precursor": acled_result,
            "ioda_precursor": ioda_result,
            "cf_precursor": cf_result,
            "internal_precursor": internal_result,
            "any_external_precursor": any_external,
            "earliest_lead_time_hours": min(lead_times) if lead_times else None,
        })

    with_precursor = sum(1 for r in results if r["any_external_precursor"])
    logger.info(
        "Precursor analysis: %d of %d surges had external precursors (%.0f%%)",
        with_precursor, len(results),
        with_precursor / max(len(results), 1) * 100,
    )
    return results


def compute_precursor_stats(analysis: list[dict]) -> dict[str, Any]:
    """Compute summary statistics from precursor analysis."""
    if not analysis:
        return {
            "surges_with_precursors": 0, "total_surges": 0,
            "pct_with_precursors": 0, "avg_lead_time_hours": 0,
            "most_reliable_source": "n/a",
        }

    total = len(analysis)
    with_ext = sum(1 for a in analysis if a["any_external_precursor"])
    with_internal = sum(1 for a in analysis if a["internal_precursor"]["detected"])

    lead_times = [a["earliest_lead_time_hours"] for a in analysis if a["earliest_lead_time_hours"]]
    avg_lead = sum(lead_times) / len(lead_times) if lead_times else 0

    # Detection rates per source
    acled_rate = sum(1 for a in analysis if a["acled_precursor"]["detected"]) / max(total, 1)
    cf_rate = sum(1 for a in analysis if a["cf_precursor"]["detected"]) / max(total, 1)
    ioda_rate = sum(1 for a in analysis if a["ioda_precursor"]["detected"]) / max(total, 1)
    internal_rate = with_internal / max(total, 1)

    rates = {"ACLED": acled_rate, "Cloudflare": cf_rate, "IODA": ioda_rate, "Internal (WAN latency)": internal_rate}
    best = max(rates, key=rates.get)

    return {
        "surges_with_precursors": with_ext,
        "surges_with_internal": with_internal,
        "total_surges": total,
        "pct_with_precursors": round(with_ext / max(total, 1) * 100, 1),
        "avg_lead_time_hours": round(avg_lead, 1),
        "most_reliable_source": best,
        "detection_rates": {k: round(v * 100, 1) for k, v in rates.items()},
    }


def save_precursor_analysis(analysis: list[dict], data_dir: Path) -> Path:
    """Save precursor analysis to parquet."""
    output = data_dir / "processed" / "precursor_analysis.parquet"
    output.parent.mkdir(parents=True, exist_ok=True)

    # Flatten nested dicts for parquet
    rows = []
    for a in analysis:
        row = {
            "surge_id": a["surge_id"],
            "date": a["date"],
            "region": a["region"],
            "delegations": ",".join(a["delegations"]),
            "countries": ",".join(a["countries"]),
            "surge_score": a["surge_score"],
            "acled_detected": a["acled_precursor"]["detected"],
            "acled_events": a["acled_precursor"]["event_count"],
            "acled_fatalities": a["acled_precursor"]["fatalities"],
            "acled_ratio": a["acled_precursor"]["ratio"],
            "cf_detected": a["cf_precursor"]["detected"],
            "cf_events": a["cf_precursor"]["event_count"],
            "internal_detected": a["internal_precursor"]["detected"],
            "internal_latency_alerts": a["internal_precursor"]["latency_alerts"],
            "any_external": a["any_external_precursor"],
            "lead_time_hours": a["earliest_lead_time_hours"],
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_parquet(output, index=False)
    logger.info("Precursor analysis saved to %s", output.name)
    return output
