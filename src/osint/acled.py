"""Parse ACLED conflict event data and filter to ICRC delegation countries."""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_acled(
    fixture_path: Path,
    registry: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Load ACLED data and compute per-country conflict summaries.

    Parameters
    ----------
    fixture_path:
        Path to ``acled_sample.json``.
    registry:
        Delegation registry keyed by delegation code.  Each entry must have
        ``country`` and ``country_iso3`` fields.

    Returns
    -------
    list of dicts with keys:
        country, country_iso3, events_30d, fatalities_30d, trend,
        top_event_types
    """
    if not fixture_path.exists():
        logger.warning("ACLED fixture not found at %s", fixture_path)
        return []

    with open(fixture_path) as f:
        raw = json.load(f)

    events = raw.get("data", [])
    if not events:
        return []

    # Build set of ICRC country names (lowercase) -> (country, iso3)
    icrc_countries: dict[str, tuple[str, str]] = {}
    for entry in registry.values():
        country = entry.get("country")
        iso3 = entry.get("country_iso3")
        if country and iso3:
            icrc_countries[country.lower()] = (country, iso3)

    if not icrc_countries:
        logger.warning("No countries with ISO3 codes found in registry")
        return []

    # Filter events to ICRC countries
    filtered: list[dict[str, Any]] = []
    for ev in events:
        c = (ev.get("country") or "").lower()
        if c in icrc_countries:
            filtered.append(ev)

    if not filtered:
        logger.info("No ACLED events match ICRC delegation countries")
        return []

    # Find the max event_date to define the 30-day window
    dates = []
    for ev in filtered:
        try:
            dates.append(datetime.strptime(ev["event_date"], "%Y-%m-%d").date())
        except (ValueError, KeyError):
            pass

    if not dates:
        return []

    max_date = max(dates)
    cutoff_30 = max_date - timedelta(days=30)
    cutoff_15 = max_date - timedelta(days=15)

    # Group events by country within the 30-day window
    country_events: dict[str, list[dict]] = {}
    for ev in filtered:
        try:
            d = datetime.strptime(ev["event_date"], "%Y-%m-%d").date()
        except (ValueError, KeyError):
            continue
        if d < cutoff_30:
            continue
        c = ev["country"].lower()
        country_events.setdefault(c, []).append({"date": d, "event": ev})

    results = []
    for country_lower, items in country_events.items():
        country_name, iso3 = icrc_countries[country_lower]

        events_30d = len(items)
        fatalities_30d = sum(
            int(item["event"].get("fatalities", 0) or 0) for item in items
        )

        # Trend: last 15 days vs prior 15 days
        recent = sum(1 for item in items if item["date"] > cutoff_15)
        prior = sum(1 for item in items if item["date"] <= cutoff_15)

        if recent > prior * 1.2:
            trend = "increasing"
        elif recent < prior * 0.8:
            trend = "decreasing"
        else:
            trend = "stable"

        # Top event types
        type_counts = Counter(
            item["event"].get("event_type", "Unknown") for item in items
        )
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
    logger.info("ACLED: %d ICRC countries with conflict data", len(results))
    return results
