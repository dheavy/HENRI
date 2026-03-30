"""Parse IODA internet outage summary and match to ICRC delegation countries."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pycountry

logger = logging.getLogger(__name__)


def _alpha2_to_alpha3(code: str) -> str | None:
    """Convert an ISO 3166-1 alpha-2 code to alpha-3.

    Returns None if the code is not recognised.
    """
    try:
        return pycountry.countries.get(alpha_2=code).alpha_3
    except (AttributeError, LookupError):
        return None


def load_ioda(
    fixture_path: Path,
    registry: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Load IODA summary data and match to ICRC countries.

    Parameters
    ----------
    fixture_path:
        Path to ``ioda_summary_7d.json``.
    registry:
        Delegation registry keyed by delegation code.

    Returns
    -------
    list of dicts with keys:
        country, country_iso3, outage_score, event_count, bgp_score, rank
    """
    if not fixture_path.exists():
        logger.warning("IODA fixture not found at %s", fixture_path)
        return []

    with open(fixture_path) as f:
        raw = json.load(f)

    entries = raw.get("data", [])
    if not entries:
        return []

    # Build iso3 -> country name lookup from registry
    iso3_to_country: dict[str, str] = {}
    for entry in registry.values():
        iso3 = entry.get("country_iso3")
        country = entry.get("country")
        if iso3 and country:
            iso3_to_country[iso3] = country

    results = []
    for item in entries:
        entity = item.get("entity", {})
        alpha2 = entity.get("code")
        if not alpha2 or entity.get("type") != "country":
            continue

        alpha3 = _alpha2_to_alpha3(alpha2)
        if not alpha3 or alpha3 not in iso3_to_country:
            continue

        scores = item.get("scores", {})
        results.append({
            "country": iso3_to_country[alpha3],
            "country_iso3": alpha3,
            "outage_score": scores.get("overall", 0),
            "event_count": item.get("event_cnt", 0),
            "bgp_score": scores.get("bgp.median", 0),
        })

    # Rank by outage_score descending
    results.sort(key=lambda r: r["outage_score"], reverse=True)
    for i, r in enumerate(results, 1):
        r["rank"] = i

    logger.info("IODA: %d ICRC countries matched", len(results))
    return results
