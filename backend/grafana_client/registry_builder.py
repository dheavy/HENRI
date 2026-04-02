"""Build the delegation registry from Grafana FortiGate labels.

This is the **primary** source for the registry — far more complete
than ServiceNow parsing alone.  It provides location_site → region
and location_site → parent (via smt_assignmentgroup) mappings for
~300+ sites.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd

from .client import GrafanaClient

logger = logging.getLogger(__name__)

FORTIGATE_LABELS_QUERY = (
    'group by (location_site, region, smt_assignmentgroup) (up{job="fortigate"})'
)

_ASSIGNMENT_RE = re.compile(r"^([A-Z]{2,5})\s+ICT\s+L2\s+SUPPORT$", re.IGNORECASE)


def _parse_grafana_results(data: dict) -> list[dict[str, str]]:
    """Extract site records from a Prometheus vector response.

    Works with both a live API response and a saved fixture file.
    """
    results = data.get("data", {}).get("result", [])
    sites: list[dict[str, str]] = []
    for r in results:
        metric = r.get("metric", {})
        site_code = metric.get("location_site", "").strip().upper()
        if not site_code:
            continue
        sites.append({
            "location_site": site_code,
            "region": metric.get("region", ""),
            "smt_assignmentgroup": metric.get("smt_assignmentgroup", ""),
        })
    return sites


def _sites_to_registry(sites: list[dict[str, str]]) -> tuple[
    dict[str, dict[str, Any]],  # registry keyed by parent code
    dict[str, str],             # subsite map {site → parent}
]:
    """Convert raw site records into a parent-keyed registry and subsite map.

    Each site's ``smt_assignmentgroup`` (e.g. ``YAO ICT L2 SUPPORT``)
    gives the parent delegation code.  The ``location_site`` is either
    the parent itself or a sub-site.
    """
    # Build parent → region and parent → assignment group from sites
    parent_region: dict[str, str] = {}
    parent_group: dict[str, str] = {}
    subsite_map: dict[str, str] = {}
    parent_subsites: dict[str, list[str]] = {}

    for site in sites:
        code = site["location_site"]
        region = site["region"]
        ag = site["smt_assignmentgroup"]

        m = _ASSIGNMENT_RE.match(ag.strip()) if ag else None
        parent = m.group(1).upper() if m else code

        subsite_map[code] = parent
        subsite_map[parent] = parent  # identity

        if region and (parent not in parent_region or not parent_region[parent]):
            parent_region[parent] = region
        if ag and parent not in parent_group:
            parent_group[parent] = ag

        if code != parent:
            parent_subsites.setdefault(parent, []).append(code)

    # Build registry keyed by parent delegation code
    registry: dict[str, dict[str, Any]] = {}
    for parent in sorted(set(subsite_map.values())):
        registry[parent] = {
            "name": parent,
            "region": parent_region.get(parent),
            "country": None,
            "country_iso3": None,
            "smt_assignmentgroup": parent_group.get(parent),
            "latitude": None,
            "longitude": None,
            "source": "grafana_fortigate_labels",
            "sub_sites": sorted(parent_subsites.get(parent, [])),
        }

    logger.info(
        "Grafana registry: %d parent delegations, %d total sites, %d sub-sites",
        len(registry),
        len(subsite_map),
        sum(1 for k, v in subsite_map.items() if k != v),
    )
    return registry, subsite_map


def build_registry_from_grafana(client: GrafanaClient) -> tuple[
    dict[str, dict[str, Any]], dict[str, str]
]:
    """Query Grafana live and build the registry.

    Returns ``(registry, subsite_map)`` or ``({}, {})`` if unavailable.
    """
    if not client.is_available:
        logger.warning("Grafana not configured — returning empty registry")
        return {}, {}

    logger.info("Querying Grafana for FortiGate site labels")
    df = client.query_instant(FORTIGATE_LABELS_QUERY)
    if df.empty:
        logger.warning("No results from FortiGate labels query")
        return {}, {}

    # Convert DataFrame rows back to the metric-dict format
    sites = [
        {
            "location_site": row.get("location_site", ""),
            "region": row.get("region", ""),
            "smt_assignmentgroup": row.get("smt_assignmentgroup", ""),
        }
        for _, row in df.iterrows()
    ]
    return _sites_to_registry(sites)


def build_registry_from_fixture(fixture_path: Path) -> tuple[
    dict[str, dict[str, Any]], dict[str, str]
]:
    """Load a saved Grafana query response and build the registry.

    Use this when the fixture file exists at ``data/fixtures/grafana_registry.json``
    to avoid hitting the live API.
    """
    logger.info("Loading Grafana registry from fixture: %s", fixture_path.name)
    with open(fixture_path) as f:
        data = json.load(f)
    sites = _parse_grafana_results(data)
    if not sites:
        logger.warning("Fixture contained no site data")
        return {}, {}
    return _sites_to_registry(sites)
