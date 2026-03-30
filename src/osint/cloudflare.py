"""Parse Cloudflare Radar verified outage data and match to ICRC countries."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pycountry

logger = logging.getLogger(__name__)


def _alpha2_to_alpha3(code: str) -> str | None:
    """Convert ISO alpha-2 to alpha-3, returning None on failure."""
    try:
        return pycountry.countries.get(alpha_2=code).alpha_3
    except (AttributeError, LookupError):
        return None


def load_cloudflare(
    fixture_path: Path,
    registry: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Load Cloudflare Radar outage data and match to ICRC countries.

    Parameters
    ----------
    fixture_path:
        Path to ``cf_outages_90d.json``.
    registry:
        Delegation registry keyed by delegation code.

    Returns
    -------
    list of dicts with keys:
        country, country_iso3, outage_count,
        events: [{type, scope, start, end}]
    """
    if not fixture_path.exists():
        logger.warning("Cloudflare fixture not found at %s", fixture_path)
        return []

    with open(fixture_path) as f:
        raw = json.load(f)

    annotations = raw.get("result", {}).get("annotations", [])
    if not annotations:
        return []

    # Build iso3 -> country name lookup from registry
    iso3_to_country: dict[str, str] = {}
    for entry in registry.values():
        iso3 = entry.get("country_iso3")
        country = entry.get("country")
        if iso3 and country:
            iso3_to_country[iso3] = country

    # Group events by country
    country_events: dict[str, list[dict[str, Any]]] = {}
    country_names: dict[str, str] = {}

    for ann in annotations:
        locations = ann.get("locations", [])
        for loc_code in locations:
            alpha3 = _alpha2_to_alpha3(loc_code)
            if not alpha3 or alpha3 not in iso3_to_country:
                continue

            country_names[alpha3] = iso3_to_country[alpha3]
            country_events.setdefault(alpha3, []).append({
                "type": ann.get("eventType", "UNKNOWN"),
                "scope": ann.get("scope"),
                "start": ann.get("startDate"),
                "end": ann.get("endDate"),
            })

    results = []
    for alpha3, events in country_events.items():
        results.append({
            "country": country_names[alpha3],
            "country_iso3": alpha3,
            "outage_count": len(events),
            "events": events,
        })

    results.sort(key=lambda r: r["outage_count"], reverse=True)
    logger.info("Cloudflare: %d ICRC countries with outages", len(results))
    return results
