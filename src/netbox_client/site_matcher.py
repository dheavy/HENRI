"""Match NetBox site slugs to Grafana location_site codes.

NetBox slugs are lowercase (``abi``, ``bag``, ``dam``).
Grafana location_site codes are uppercase (``ABI``, ``BAG``, ``DAM``).
Matching is case-insensitive on the slug/code.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def match_sites(
    netbox_sites: list[dict],
    grafana_codes: set[str],
) -> dict[str, dict[str, Any]]:
    """Match NetBox sites to Grafana location_site codes.

    Returns ``{GRAFANA_CODE: netbox_site_record}`` for each match.
    Matching is done by uppercasing the NetBox slug and checking
    membership in *grafana_codes*.
    """
    matched: dict[str, dict[str, Any]] = {}
    unmatched_nb: list[str] = []

    for site in netbox_sites:
        slug = site.get("slug", "").strip()
        name = site.get("name", "").strip()
        # Try slug → uppercase first, then name → uppercase
        code = slug.upper()
        if code in grafana_codes:
            matched[code] = site
        elif name.upper() in grafana_codes:
            matched[name.upper()] = site
        else:
            unmatched_nb.append(slug)

    logger.info(
        "NetBox site matching: %d matched, %d unmatched NetBox sites",
        len(matched), len(unmatched_nb),
    )
    if unmatched_nb:
        logger.debug("Unmatched NetBox slugs: %s", unmatched_nb[:20])

    return matched


def load_sites_from_fixture(fixture_path: Path) -> list[dict]:
    """Load NetBox sites from a saved fixture file."""
    with open(fixture_path) as f:
        data = json.load(f)
    return data.get("results", [])


def build_site_map(
    netbox_fixture: Path,
    grafana_codes: set[str],
) -> dict[str, dict[str, Any]]:
    """Convenience: load fixture and match against Grafana codes."""
    sites = load_sites_from_fixture(netbox_fixture)
    return match_sites(sites, grafana_codes)
