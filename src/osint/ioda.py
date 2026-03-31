"""IODA internet outage data — live API pull and fixture loading.

Live API (no auth required):
- Summary: GET https://api.ioda.inetintel.cc.gatech.edu/v2/outages/summary
           ?from=-7d&until=now
- Alerts:  GET https://api.ioda.inetintel.cc.gatech.edu/v2/outages/alerts
           ?from=-7d&until=now&entityType=country&entityCode=<alpha2>
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx
import pycountry

logger = logging.getLogger(__name__)

_IODA_BASE = "https://api.ioda.inetintel.cc.gatech.edu/v2"


def _alpha2_to_alpha3(code: str) -> str | None:
    """Convert an ISO 3166-1 alpha-2 code to alpha-3."""
    try:
        return pycountry.countries.get(alpha_2=code).alpha_3
    except (AttributeError, LookupError):
        return None


def _alpha3_to_alpha2(code: str) -> str | None:
    """Convert an ISO 3166-1 alpha-3 code to alpha-2."""
    try:
        return pycountry.countries.get(alpha_3=code).alpha_2
    except (AttributeError, LookupError):
        return None


def _get_icrc_iso3(registry: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Return {iso3: country_name} for ICRC field delegations."""
    iso3_to_name: dict[str, str] = {}
    for entry in registry.values():
        iso3 = entry.get("country_iso3")
        country = entry.get("country")
        if iso3 and country:
            iso3_to_name[iso3] = country
    return iso3_to_name


def _parse_summary(data: dict, iso3_to_country: dict[str, str]) -> list[dict[str, Any]]:
    """Parse IODA summary response into per-country records."""
    entries = data.get("data", [])
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
    results.sort(key=lambda r: r["outage_score"], reverse=True)
    for i, r in enumerate(results, 1):
        r["rank"] = i
    return results


def fetch_ioda_live(
    registry: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Fetch IODA outage summary from the live API (no auth required)."""
    iso3_to_country = _get_icrc_iso3(registry)
    if not iso3_to_country:
        return []

    import time
    now = int(time.time())
    week_ago = now - 7 * 86400

    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(
                f"{_IODA_BASE}/outages/summary",
                params={"from": str(week_ago), "until": str(now)},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.debug("IODA API error: %s", e)
        logger.warning("IODA: live fetch failed")
        return []

    results = _parse_summary(data, iso3_to_country)
    logger.info("IODA live: %d ICRC countries matched", len(results))
    return results


def load_ioda(
    fixture_path: Path,
    registry: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Load IODA summary data from fixture."""
    if not fixture_path.exists():
        logger.warning("IODA fixture not found at %s", fixture_path.name)
        return []
    with open(fixture_path) as f:
        data = json.load(f)
    iso3_to_country = _get_icrc_iso3(registry)
    results = _parse_summary(data, iso3_to_country)
    logger.info("IODA: %d ICRC countries matched", len(results))
    return results


def load_or_fetch_ioda(
    data_dir: Path,
    registry: dict[str, dict[str, Any]],
    *,
    use_fixtures: bool = False,
) -> list[dict[str, Any]]:
    """Load IODA data — live API first (no auth needed), fixture fallback."""
    if not use_fixtures:
        results = fetch_ioda_live(registry)
        if results:
            return results
        logger.warning("IODA live unavailable; falling back to fixture")

    fixture = data_dir / "fixtures" / "ioda_summary_7d.json"
    return load_ioda(fixture, registry)
