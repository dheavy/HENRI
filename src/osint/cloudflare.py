"""Cloudflare Radar outage and BGP event data — live API pull and fixture loading.

Live API (requires CF_API_TOKEN):
- Outages:    GET /client/v4/radar/annotations/outages?dateRange=90d
- BGP hijacks: GET /client/v4/radar/bgp/hijacks/events?dateRange=90d
- BGP leaks:   GET /client/v4/radar/bgp/leaks/events?dateRange=90d
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx
import pycountry

logger = logging.getLogger(__name__)

_CF_BASE = "https://api.cloudflare.com/client/v4"


def _alpha2_to_alpha3(code: str) -> str | None:
    """Convert ISO alpha-2 to alpha-3, returning None on failure."""
    try:
        return pycountry.countries.get(alpha_2=code).alpha_3
    except (AttributeError, LookupError):
        return None


def _get_icrc_iso3(registry: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Return {iso3: country_name} for ICRC delegations."""
    iso3_to_name: dict[str, str] = {}
    for entry in registry.values():
        iso3 = entry.get("country_iso3")
        country = entry.get("country")
        if iso3 and country:
            iso3_to_name[iso3] = country
    return iso3_to_name


def _parse_annotations(
    annotations: list[dict],
    iso3_to_country: dict[str, str],
) -> list[dict[str, Any]]:
    """Group Cloudflare annotations by ICRC country."""
    country_events: dict[str, list[dict[str, Any]]] = {}
    country_names: dict[str, str] = {}

    for ann in annotations:
        for loc_code in ann.get("locations", []):
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
    return results


def fetch_cloudflare_live(
    registry: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Fetch Cloudflare Radar outage annotations from the live API.

    Requires CF_API_TOKEN environment variable.
    """
    token = os.getenv("CF_API_TOKEN", "")
    if not token:
        logger.warning("CF_API_TOKEN not set — cannot fetch Cloudflare data")
        return []

    iso3_to_country = _get_icrc_iso3(registry)
    if not iso3_to_country:
        return []

    all_annotations: list[dict] = []
    headers = {"Authorization": f"Bearer {token}"}

    with httpx.Client(timeout=20.0) as client:
        # Outage annotations
        try:
            resp = client.get(
                f"{_CF_BASE}/radar/annotations/outages",
                headers=headers,
                params={"dateRange": "90d", "limit": 500},
            )
            resp.raise_for_status()
            data = resp.json()
            anns = data.get("result", {}).get("annotations", [])
            all_annotations.extend(anns)
            logger.debug("CF outages: %d annotations", len(anns))
        except Exception as e:
            logger.debug("CF outage fetch error: %s", e)
            logger.warning("Cloudflare: outage fetch failed")

        # BGP hijacks
        try:
            resp = client.get(
                f"{_CF_BASE}/radar/bgp/hijacks/events",
                headers=headers,
                params={"dateRange": "90d", "per_page": 100},
            )
            resp.raise_for_status()
            data = resp.json()
            for event in data.get("result", {}).get("asn_events", []):
                # Convert BGP hijack to annotation-like format
                all_annotations.append({
                    "eventType": "BGP_HIJACK",
                    "locations": [cc for cc in event.get("country_codes", [])],
                    "startDate": event.get("detected_ts"),
                    "endDate": event.get("finished_ts"),
                    "scope": f"AS{event.get('victim_asn', '?')}",
                })
        except Exception as e:
            logger.debug("CF BGP hijack fetch error: %s", e)

        # BGP leaks
        try:
            resp = client.get(
                f"{_CF_BASE}/radar/bgp/leaks/events",
                headers=headers,
                params={"dateRange": "90d", "per_page": 100},
            )
            resp.raise_for_status()
            data = resp.json()
            for event in data.get("result", {}).get("asn_events", []):
                all_annotations.append({
                    "eventType": "BGP_LEAK",
                    "locations": [cc for cc in event.get("country_codes", [])],
                    "startDate": event.get("detected_ts"),
                    "endDate": event.get("finished_ts"),
                    "scope": f"AS{event.get('leaker_asn', '?')}",
                })
        except Exception as e:
            logger.debug("CF BGP leak fetch error: %s", e)

    results = _parse_annotations(all_annotations, iso3_to_country)
    logger.info("Cloudflare live: %d ICRC countries with events", len(results))
    return results


def load_cloudflare(
    fixture_path: Path,
    registry: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Load Cloudflare data from fixture."""
    if not fixture_path.exists():
        logger.warning("Cloudflare fixture not found at %s", fixture_path.name)
        return []
    with open(fixture_path) as f:
        raw = json.load(f)
    annotations = raw.get("result", {}).get("annotations", [])
    iso3_to_country = _get_icrc_iso3(registry)
    results = _parse_annotations(annotations, iso3_to_country)
    logger.info("Cloudflare: %d ICRC countries with outages", len(results))
    return results


def load_or_fetch_cloudflare(
    data_dir: Path,
    registry: dict[str, dict[str, Any]],
    *,
    use_fixtures: bool = False,
) -> list[dict[str, Any]]:
    """Load Cloudflare data — live API if token exists, fixture fallback."""
    if not use_fixtures and os.getenv("CF_API_TOKEN"):
        results = fetch_cloudflare_live(registry)
        if results:
            return results
        logger.warning("Cloudflare live unavailable; falling back to fixture")

    fixture = data_dir / "fixtures" / "cf_outages_90d.json"
    return load_cloudflare(fixture, registry)
