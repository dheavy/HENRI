"""ACLED conflict event data — live API pull and fixture loading.

Live API flow:
1. POST https://acleddata.com/oauth/token → bearer token
2. GET  https://acleddata.com/api/acled/read?country=<name>&limit=5000
        &event_date=<start>|<end>&event_date_where=BETWEEN

Paginated by country to stay within 5000-row API limit.
Results saved to data/processed/acled_events.parquet.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://acleddata.com/oauth/token"
_API_URL = "https://acleddata.com/api/acled/read"


def _get_icrc_countries(registry: dict[str, dict[str, Any]]) -> dict[str, tuple[str, str]]:
    """Return {country_name_lower: (country_name, iso3)} for ICRC field delegations."""
    countries: dict[str, tuple[str, str]] = {}
    for entry in registry.values():
        country = entry.get("country")
        iso3 = entry.get("country_iso3")
        region = entry.get("region", "")
        # Only field regions — exclude HQ
        if country and iso3 and region and region != "HQ":
            countries[country.lower()] = (country, iso3)
    return countries


def _authenticate() -> str | None:
    """Obtain an OAuth bearer token from ACLED.

    Requires ACLED_EMAIL and ACLED_KEY environment variables.
    """
    email = os.getenv("ACLED_EMAIL", "")
    key = os.getenv("ACLED_KEY", "")
    if not email or not key:
        logger.warning("ACLED_EMAIL and ACLED_KEY not set — cannot authenticate")
        return None

    try:
        resp = httpx.post(
            _TOKEN_URL,
            data={"email": email, "key": key},
            timeout=15.0,
        )
        resp.raise_for_status()
        token = resp.json().get("access_token")
        if token:
            logger.info("ACLED: authenticated successfully")
            return token
        logger.warning("ACLED: no access_token in response")
        return None
    except Exception as e:
        logger.debug("ACLED auth error: %s", e)
        logger.warning("ACLED: authentication failed")
        return None


def fetch_acled_live(
    registry: dict[str, dict[str, Any]],
    days: int = 90,
    output_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Pull ACLED events for all ICRC countries over the last *days* days.

    Paginates by country (5000 per call). Saves to parquet if *output_path* given.
    Returns the raw event list, or [] if auth fails / API unavailable.
    """
    token = _authenticate()
    if not token:
        return []

    icrc_countries = _get_icrc_countries(registry)
    if not icrc_countries:
        logger.warning("No ICRC field countries found in registry")
        return []

    end_date = date.today()
    start_date = end_date - timedelta(days=days)
    date_range = f"{start_date}|{end_date}"

    all_events: list[dict] = []
    headers = {"Authorization": f"Bearer {token}"}

    with httpx.Client(timeout=30.0) as client:
        for country_lower, (country_name, _) in sorted(icrc_countries.items()):
            time.sleep(1.0)  # Rate limit: max 1 req/s
            try:
                resp = client.get(
                    _API_URL,
                    headers=headers,
                    params={
                        "country": country_name,
                        "limit": 5000,
                        "event_date": date_range,
                        "event_date_where": "BETWEEN",
                    },
                )
                if resp.status_code == 429:
                    logger.warning("ACLED: rate limited (429); backing off 60s")
                    time.sleep(60)
                    continue
                if resp.status_code in (401, 403):
                    logger.warning("ACLED: auth rejected (%d); aborting pull", resp.status_code)
                    return []
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, dict):
                    continue
                events = data.get("data", [])
                if not isinstance(events, list):
                    continue
                all_events.extend(events)
                if events:
                    logger.debug("ACLED: %s → %d events", country_name, len(events))
            except httpx.HTTPStatusError as e:
                logger.debug("ACLED HTTP error for %s: %d", country_name, e.response.status_code)
            except httpx.RequestError as e:
                logger.debug("ACLED network error for %s: %s", country_name, e)
                logger.warning("ACLED: network error fetching %s", country_name)

    logger.info("ACLED live: %d events across %d countries", len(all_events), len(icrc_countries))

    if output_path and all_events:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(all_events)
        df.to_parquet(output_path, index=False)
        logger.info("ACLED events saved to %s", output_path)

    return all_events


def _summarise_events(
    events: list[dict],
    icrc_countries: dict[str, tuple[str, str]],
) -> list[dict[str, Any]]:
    """Compute per-country conflict summaries from a list of ACLED events."""
    if not events:
        return []

    dates = []
    for ev in events:
        try:
            dates.append(datetime.strptime(ev["event_date"], "%Y-%m-%d").date())
        except (ValueError, KeyError):
            pass
    if not dates:
        return []

    max_date = max(dates)
    cutoff_30 = max_date - timedelta(days=30)
    cutoff_15 = max_date - timedelta(days=15)

    country_events: dict[str, list[dict]] = {}
    for ev in events:
        try:
            d = datetime.strptime(ev["event_date"], "%Y-%m-%d").date()
        except (ValueError, KeyError):
            continue
        if d < cutoff_30:
            continue
        c = (ev.get("country") or "").lower()
        if c in icrc_countries:
            country_events.setdefault(c, []).append({"date": d, "event": ev})

    results = []
    for country_lower, items in country_events.items():
        country_name, iso3 = icrc_countries[country_lower]
        events_30d = len(items)
        fatalities_30d = sum(int(item["event"].get("fatalities", 0) or 0) for item in items)

        recent = sum(1 for item in items if item["date"] > cutoff_15)
        prior = sum(1 for item in items if item["date"] <= cutoff_15)
        if recent > prior * 1.2:
            trend = "increasing"
        elif recent < prior * 0.8:
            trend = "decreasing"
        else:
            trend = "stable"

        type_counts = Counter(item["event"].get("event_type", "Unknown") for item in items)
        top_event_types = [t for t, _ in type_counts.most_common(5)]

        results.append({
            "country": country_name,
            "country_iso3": iso3,
            "events_30d": events_30d,
            "fatalities_30d": fatalities_30d,
            "trend": trend,
            "top_event_types": top_event_types,
        })

    results.sort(key=lambda r: r["events_30d"], reverse=True)
    return results


def load_acled(
    fixture_path: Path,
    registry: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Load ACLED data from fixture and compute per-country summaries."""
    if not fixture_path.exists():
        logger.warning("ACLED fixture not found at %s", fixture_path.name)
        return []

    with open(fixture_path) as f:
        raw = json.load(f)

    events = raw.get("data", [])
    icrc_countries = _get_icrc_countries(registry)
    if not icrc_countries:
        # Fall back to all countries in registry
        for entry in registry.values():
            c = entry.get("country")
            iso3 = entry.get("country_iso3")
            if c and iso3:
                icrc_countries[c.lower()] = (c, iso3)

    result = _summarise_events(events, icrc_countries)
    logger.info("ACLED: %d ICRC countries with conflict data", len(result))
    return result


def load_or_fetch_acled(
    data_dir: Path,
    registry: dict[str, dict[str, Any]],
    *,
    use_fixtures: bool = False,
) -> list[dict[str, Any]]:
    """Load ACLED data — live API if credentials exist, else fixture fallback.

    When *use_fixtures* is True, always use the fixture file.
    """
    icrc_countries = _get_icrc_countries(registry)
    if not icrc_countries:
        for entry in registry.values():
            c = entry.get("country")
            iso3 = entry.get("country_iso3")
            if c and iso3:
                icrc_countries[c.lower()] = (c, iso3)

    if not use_fixtures and os.getenv("ACLED_EMAIL") and os.getenv("ACLED_KEY"):
        # Try live parquet first (from a previous pull)
        parquet_path = data_dir / "processed" / "acled_events.parquet"
        if parquet_path.exists():
            logger.info("Loading ACLED from processed parquet")
            df = pd.read_parquet(parquet_path)
            events = df.to_dict("records")
            return _summarise_events(events, icrc_countries)

        # Live pull
        events = fetch_acled_live(
            registry, days=90,
            output_path=data_dir / "processed" / "acled_events.parquet",
        )
        if events:
            return _summarise_events(events, icrc_countries)
        logger.warning("ACLED live pull returned no data; falling back to fixture")

    # Fixture fallback
    fixture = data_dir / "fixtures" / "acled_sample.json"
    return load_acled(fixture, registry)
