"""Combine OSINT signals into per-country risk cards.

Only includes countries where ICRC has **field** delegations
(AFRICA East, AFRICA West, AMERICAS, ASIA, EURASIA, NAME).
HQ countries and countries without delegations are excluded.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .acled import load_or_fetch_acled
from .ioda import load_or_fetch_ioda
from .cloudflare import load_or_fetch_cloudflare

logger = logging.getLogger(__name__)

_FIELD_REGIONS = {"AFRICA East", "AFRICA West", "AMERICAS", "ASIA", "EURASIA", "NAME"}

# Only exclude countries that map exclusively to HQ region
_EXCLUDED_COUNTRIES = {"CHE"}

# Signal weights for the combined risk score
WEIGHTS = {
    "acled_events": 0.30,
    "acled_fatalities": 0.20,
    "ioda_outage": 0.20,
    "cf_outages": 0.15,
    "snow_sitedown": 0.15,
}


def _percentile_rank(values: list[float]) -> list[float]:
    """Convert raw values to 0-100 percentile ranks.

    Ties receive the same rank.  Zero-length input returns an empty list.
    """
    if not values:
        return []
    arr = np.array(values, dtype=float)
    if arr.max() == 0:
        return [0.0] * len(values)
    n = len(arr)
    ranks = np.zeros(n)
    for i, v in enumerate(arr):
        ranks[i] = np.sum(arr < v) / max(n - 1, 1) * 100
    return ranks.tolist()


def _get_field_countries(registry: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Return {iso3: country_name} for ICRC field delegations only.

    Excludes HQ region and HQ-adjacent countries (UK, France, US, etc.)
    whose domestic OSINT data is noise for field network intelligence.
    """
    result: dict[str, str] = {}
    for entry in registry.values():
        iso3 = entry.get("country_iso3")
        country = entry.get("country")
        region = entry.get("region", "")
        if iso3 and country and region in _FIELD_REGIONS and iso3 not in _EXCLUDED_COUNTRIES:
            result[iso3] = country
    return result


def _load_snow_sitedown_counts(
    data_dir: Path,
    registry: dict[str, dict[str, Any]],
) -> dict[str, int]:
    """Count FortigateSiteDown incidents per country from processed parquet.

    Returns {country_iso3: count}.
    """
    parquet_path = data_dir / "processed" / "incidents_all.parquet"
    if not parquet_path.exists():
        return {}

    try:
        df = pd.read_parquet(parquet_path)
    except Exception as exc:
        logger.warning("Failed to load incidents parquet: %s", exc)
        return {}

    if "alert_name" not in df.columns:
        return {}

    sd = df[df["alert_name"] == "FortigateSiteDown"].copy()
    if sd.empty:
        return {}

    code_col = "parent_code" if "parent_code" in sd.columns else "delegation_code"
    if code_col not in sd.columns:
        return {}

    iso3_counts: dict[str, int] = {}
    for code, count in sd[code_col].value_counts().items():
        code_str = str(code).upper() if pd.notna(code) else ""
        entry = registry.get(code_str, {})
        iso3 = entry.get("country_iso3")
        if iso3:
            iso3_counts[iso3] = iso3_counts.get(iso3, 0) + int(count)

    return iso3_counts


def compute_risk_cards(
    data_dir: Path,
    registry: dict[str, dict[str, Any]],
    *,
    use_fixtures: bool = False,
) -> list[dict[str, Any]]:
    """Compute combined risk cards for ICRC field delegation countries.

    Parameters
    ----------
    data_dir:
        Root data directory containing ``fixtures/`` and ``processed/``.
    registry:
        Delegation registry keyed by delegation code.
    use_fixtures:
        If True, always use fixture files instead of live API calls.

    Returns
    -------
    list of risk cards sorted by combined risk score descending.
    Each source that fails gracefully contributes 0 for its signals.
    """
    # Only field countries — no fallback to all countries
    field_countries = _get_field_countries(registry)
    if not field_countries:
        logger.warning("No field delegation countries found in registry")
        return []

    # Load each OSINT source — each degrades gracefully
    acled_data = load_or_fetch_acled(data_dir, registry, use_fixtures=use_fixtures)
    ioda_data = load_or_fetch_ioda(data_dir, registry, use_fixtures=use_fixtures)
    cf_data = load_or_fetch_cloudflare(data_dir, registry, use_fixtures=use_fixtures)
    snow_counts = _load_snow_sitedown_counts(data_dir, registry)

    # Index OSINT data by iso3
    acled_by_iso3 = {r["country_iso3"]: r for r in acled_data}
    ioda_by_iso3 = {r["country_iso3"]: r for r in ioda_data}
    cf_by_iso3 = {r["country_iso3"]: r for r in cf_data}

    # Build raw signal vectors — only for field countries
    iso3_list = sorted(field_countries.keys())
    raw_signals: dict[str, list[float]] = {
        "acled_events": [],
        "acled_fatalities": [],
        "ioda_outage": [],
        "cf_outages": [],
        "snow_sitedown": [],
    }

    for iso3 in iso3_list:
        acled = acled_by_iso3.get(iso3, {})
        ioda = ioda_by_iso3.get(iso3, {})
        cf = cf_by_iso3.get(iso3, {})
        raw_signals["acled_events"].append(float(acled.get("events_30d", 0)))
        raw_signals["acled_fatalities"].append(float(acled.get("fatalities_30d", 0)))
        raw_signals["ioda_outage"].append(float(ioda.get("outage_score", 0)))
        raw_signals["cf_outages"].append(float(cf.get("outage_count", 0)))
        raw_signals["snow_sitedown"].append(float(snow_counts.get(iso3, 0)))

    # Normalize each signal to percentile rank (0-100)
    normalized: dict[str, list[float]] = {}
    for key, values in raw_signals.items():
        normalized[key] = _percentile_rank(values)

    # Track which sources have data
    has_acled = bool(acled_data)
    has_ioda = bool(ioda_data)
    has_cf = bool(cf_data)

    # Compute weighted combined score
    cards = []
    for i, iso3 in enumerate(iso3_list):
        score = sum(WEIGHTS[key] * normalized[key][i] for key in WEIGHTS)
        acled = acled_by_iso3.get(iso3, {})
        ioda = ioda_by_iso3.get(iso3, {})
        cf = cf_by_iso3.get(iso3, {})

        cards.append({
            "country": field_countries[iso3],
            "country_iso3": iso3,
            "acled_events": int(acled.get("events_30d", 0)),
            "acled_fatalities": int(acled.get("fatalities_30d", 0)),
            "acled_trend": acled.get("trend", "n/a"),
            "ioda_score": round(ioda.get("outage_score", 0), 1),
            "cf_outages": int(cf.get("outage_count", 0)),
            "snow_sitedown": snow_counts.get(iso3, 0),
            "combined_risk": round(score, 1),
            # Data availability flags
            "acled_available": has_acled,
            "ioda_available": has_ioda,
            "cf_available": has_cf,
        })

    cards.sort(key=lambda c: c["combined_risk"], reverse=True)
    logger.info("Risk scorer: %d field country cards computed", len(cards))
    return cards
