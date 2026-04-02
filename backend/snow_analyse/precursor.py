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
    """ACLED check with spike-onset lead time calculation.

    1. Get events in affected countries for the 7-day lookback window
    2. Compute daily baseline (30-day mean + 2σ threshold)
    3. Find the ONSET of the spike — first day exceeding the threshold
    4. Lead time = surge_start - spike_onset
    """
    empty = {"detected": False, "event_count": 0, "fatalities": 0,
             "baseline_avg": 0, "ratio": 0, "lead_time_hours": 0,
             "spike_onset": None}

    if acled_df.empty or not country_iso3_to_name:
        return empty

    target_names = {n.lower() for n in country_iso3_to_name.values()}
    relevant = acled_df[acled_df["country"].str.lower().isin(target_names)]

    if relevant.empty:
        return empty

    surge_date = surge_start.date()
    w_start = surge_date - timedelta(days=7)
    b_start = surge_date - timedelta(days=37)

    w_start_s, w_end_s = str(w_start), str(surge_date)
    b_start_s = str(b_start)

    # 7-day window events
    window = relevant[(relevant["event_date"] >= w_start_s) & (relevant["event_date"] < w_end_s)]
    # 30-day baseline (before the window)
    baseline = relevant[(relevant["event_date"] >= b_start_s) & (relevant["event_date"] < w_start_s)]

    wc = len(window)
    if wc < 3:
        return empty

    # Daily baseline stats
    if not baseline.empty:
        daily_baseline = baseline.groupby("event_date").size()
        baseline_mean = daily_baseline.mean()
        baseline_std = daily_baseline.std() if len(daily_baseline) > 1 else 0
    else:
        baseline_mean = 0
        baseline_std = 0

    threshold = baseline_mean + 2 * max(baseline_std, baseline_mean * 0.5)
    daily_avg = baseline_mean
    avg_7d = daily_avg * 7

    fatalities = int(window["fatalities"].fillna(0).astype(int).sum()) if "fatalities" in window.columns else 0

    # Find spike onset: first day in the window where daily count > threshold
    daily_window = window.groupby("event_date").size().sort_index()
    spike_onset = None
    exceeded_at_start = False

    for day_str, count in daily_window.items():
        if count > max(threshold, 1):
            spike_onset = day_str
            break

    # Also check the 7-day aggregate ratio as a secondary signal
    ratio = wc / max(avg_7d, 1)

    # Detection: either a daily spike exceeded threshold OR aggregate ratio >= 2
    detected = spike_onset is not None or (ratio >= 2.0 and wc >= 3)
    if not detected:
        return empty

    # Check if spike was already ongoing at window start
    if spike_onset == str(w_start):
        # Check the day before the window
        day_before = str(w_start - timedelta(days=1))
        pre_window = relevant[relevant["event_date"] == day_before]
        if len(pre_window) > max(threshold, 1):
            exceeded_at_start = True

    # Calculate lead time
    if spike_onset:
        from datetime import date as date_type
        onset_date = date_type.fromisoformat(str(spike_onset)[:10])
        lead_td = surge_start - datetime.combine(onset_date, datetime.min.time(), tzinfo=timezone.utc)
        lead_hours = lead_td.total_seconds() / 3600
        if exceeded_at_start:
            lead_hours = max(lead_hours, 168.0)  # >168h, spike predates window
    else:
        lead_hours = 0

    return {
        "detected": True,
        "event_count": int(wc),
        "fatalities": fatalities,
        "baseline_avg": round(avg_7d, 1),
        "ratio": round(ratio, 1),
        "lead_time_hours": round(lead_hours, 1),
        "spike_onset": spike_onset,
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


def _load_cf_historical(data_dir: Path) -> list[dict]:
    """Load Cloudflare outage annotations covering the full incident date range.

    Tries the live API first (with ``dateRange=180d`` to cover Nov 2025+),
    falls back to the fixture file.
    """
    import os
    token = os.getenv("CF_API_TOKEN", "")
    if token:
        try:
            import httpx
            resp = httpx.get(
                "https://api.cloudflare.com/client/v4/radar/annotations/outages",
                headers={"Authorization": f"Bearer {token}"},
                params={"dateRange": "180d", "limit": 1000},
                timeout=20.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict):
                    anns = data.get("result", {}).get("annotations", [])
                    if anns:
                        logger.info("CF historical: %d annotations (180d)", len(anns))
                        return anns
        except Exception as e:
            logger.debug("CF historical fetch failed: %s", e)

    # Fallback to fixture
    cf_path = data_dir / "fixtures" / "cf_outages_90d.json"
    if cf_path.exists():
        with open(cf_path) as f:
            return json.load(f).get("result", {}).get("annotations", [])
    return []


def _load_ioda_historical(
    data_dir: Path,
    registry: dict[str, dict[str, Any]],
) -> dict[str, list[dict]]:
    """Load IODA alerts for ICRC countries covering the incident date range.

    Returns ``{iso3: [alert_dicts]}`` keyed by country alpha-3.
    Uses epoch timestamps to query the alerts endpoint.
    """
    import os
    import time as _time

    # Determine the date range from incidents
    incidents_path = data_dir / "processed" / "incidents_all.parquet"
    if not incidents_path.exists():
        return {}
    try:
        df = pd.read_parquet(incidents_path, columns=["opened_dt"])
        min_dt = df["opened_dt"].min()
        max_dt = df["opened_dt"].max()
        if pd.isna(min_dt) or pd.isna(max_dt):
            return {}
        from_ts = int(min_dt.timestamp())
        until_ts = int(max_dt.timestamp())
    except Exception:
        return {}

    # Get unique ICRC country alpha-2 codes
    import pycountry
    iso3_set: set[str] = set()
    for entry in registry.values():
        iso3 = entry.get("country_iso3")
        if iso3:
            iso3_set.add(iso3)

    # Query IODA alerts for each country (rate limited)
    alerts_by_iso3: dict[str, list[dict]] = {}
    try:
        import httpx
        with httpx.Client(timeout=15.0) as client:
            for iso3 in sorted(iso3_set):
                try:
                    c = pycountry.countries.get(alpha_3=iso3)
                    if not c:
                        continue
                    alpha2 = c.alpha_2
                except (AttributeError, LookupError):
                    continue

                _time.sleep(0.5)  # Rate limit
                try:
                    resp = client.get(
                        f"https://api.ioda.inetintel.cc.gatech.edu/v2/outages/alerts",
                        params={
                            "from": str(from_ts),
                            "until": str(until_ts),
                            "entityType": "country",
                            "entityCode": alpha2,
                        },
                    )
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    if not isinstance(data, dict):
                        continue
                    entries = data.get("data", [])
                    if isinstance(entries, list) and entries:
                        alerts_by_iso3[iso3] = entries
                except Exception:
                    continue
    except Exception as e:
        logger.debug("IODA historical fetch failed: %s", e)

    total = sum(len(v) for v in alerts_by_iso3.values())
    if total:
        logger.info("IODA historical: %d alerts across %d countries", total, len(alerts_by_iso3))
    return alerts_by_iso3


def _check_ioda(
    surge_start: datetime,
    country_iso3: set[str],
    ioda_alerts_by_iso3: dict[str, list[dict]],
) -> dict[str, Any]:
    """Check IODA alerts for affected countries in 48h before surge."""
    if not ioda_alerts_by_iso3 or not country_iso3:
        return {"detected": False, "score": 0, "alert_count": 0}

    lookback = surge_start - timedelta(hours=48)
    lookback_ts = lookback.timestamp()
    surge_ts = surge_start.timestamp()

    matching = 0
    for iso3 in country_iso3:
        alerts = ioda_alerts_by_iso3.get(iso3, [])
        for alert in alerts:
            # IODA alert has 'time' (epoch) or 'from'/'until'
            alert_time = alert.get("time") or alert.get("from")
            if alert_time is None:
                continue
            try:
                t = float(alert_time)
            except (ValueError, TypeError):
                continue
            if lookback_ts <= t <= surge_ts:
                matching += 1

    return {
        "detected": matching > 0,
        "score": 0,
        "alert_count": matching,
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

    # Load Cloudflare data — try live API for full date range, fall back to fixture
    cf_annotations: list[dict] = []
    cf_annotations = _load_cf_historical(data_dir)

    # Load IODA historical alerts (live API, covers surge date range)
    ioda_alerts_by_iso3: dict[str, list[dict]] = {}
    ioda_alerts_by_iso3 = _load_ioda_historical(data_dir, registry)

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

        # IODA: check historical alerts for affected countries in 48h before surge
        ioda_result = _check_ioda(start_time, country_iso3, ioda_alerts_by_iso3)

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
            "acled_spike_onset": a["acled_precursor"].get("spike_onset"),
            "ioda_detected": a.get("ioda_precursor", {}).get("detected", False),
            "ioda_alerts": a.get("ioda_precursor", {}).get("alert_count", 0),
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
