"""Build a delegation-code registry from ServiceNow incidents and location data."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import pycountry
from thefuzz import fuzz, process as fuzz_process

logger = logging.getLogger(__name__)

# Pattern: "<CODE> ICT L2 Support"
_ASSIGNMENT_RE = re.compile(r"^([A-Z]{2,5})\s+ICT\s+L2\s+Support$", re.IGNORECASE)


def _extract_codes_from_groups(incidents_df: pd.DataFrame) -> dict[str, str]:
    """Return {code: assignment_group} from assignment_group column."""
    if "assignment_group" not in incidents_df.columns:
        logger.warning("No 'assignment_group' column in incidents DataFrame")
        return {}
    codes: dict[str, str] = {}
    for group in incidents_df["assignment_group"].dropna().unique():
        m = _ASSIGNMENT_RE.match(str(group).strip())
        if m:
            code = m.group(1).upper()
            codes[code] = str(group).strip()
    logger.info("Extracted %d delegation codes from assignment groups", len(codes))
    return codes


def _iso3_for_country(country_name: Optional[str]) -> Optional[str]:
    """Resolve a country name to ISO 3166-1 alpha-3."""
    if not country_name:
        return None
    try:
        return pycountry.countries.lookup(country_name).alpha_3
    except LookupError:
        pass
    try:
        results = pycountry.countries.search_fuzzy(country_name)
        if results:
            return results[0].alpha_3
    except LookupError:
        pass
    return None


def _fuzzy_match_city(
    city: str, candidates: list[str], threshold: int = 70
) -> Optional[str]:
    """Return the best fuzzy match for *city* among *candidates*, or None."""
    if not city or not candidates:
        return None
    result = fuzz_process.extractOne(city, candidates, scorer=fuzz.token_sort_ratio)
    if result and result[1] >= threshold:
        return result[0]
    return None


def build_registry(
    incidents_df: pd.DataFrame,
    locations_df: pd.DataFrame,
    grafana_available: bool = False,
) -> dict[str, dict[str, Any]]:
    """Build a delegation registry keyed by delegation code.

    Each entry contains:
    - ``name``: delegation code (same as key)
    - ``region``: region from locations (if matched), else None
    - ``country``: country name
    - ``country_iso3``: ISO 3166-1 alpha-3
    - ``smt_assignmentgroup``: the ServiceNow assignment group string
    - ``latitude``: float or None
    - ``longitude``: float or None
    - ``source``: ``"servicenow_only"`` when Grafana is not available
    """
    code_to_group = _extract_codes_from_groups(incidents_df)
    if not code_to_group:
        return {}

    # Build a city→row lookup from locations
    city_col = "city" if "city" in locations_df.columns else None
    city_candidates: list[str] = []
    city_to_rows: dict[str, pd.Series] = {}
    if city_col:
        for _, loc_row in locations_df.iterrows():
            city_val = loc_row.get(city_col)
            if isinstance(city_val, str) and city_val.strip():
                clean = city_val.strip()
                city_candidates.append(clean)
                city_to_rows[clean] = loc_row

    registry: dict[str, dict[str, Any]] = {}
    for code, group in code_to_group.items():
        entry: dict[str, Any] = {
            "name": code,
            "region": None,
            "country": None,
            "country_iso3": None,
            "smt_assignmentgroup": group,
            "latitude": None,
            "longitude": None,
            "source": "servicenow_only" if not grafana_available else "servicenow+grafana",
        }

        # Try fuzzy city match using the code as a proxy for city name
        matched_city = _fuzzy_match_city(code, city_candidates)
        if matched_city and matched_city in city_to_rows:
            loc = city_to_rows[matched_city]
            entry["region"] = loc.get("region") if "region" in loc.index else None
            country = loc.get("country_clean") if "country_clean" in loc.index else loc.get("country")
            if isinstance(country, str):
                entry["country"] = country
                entry["country_iso3"] = _iso3_for_country(country)
            lat = loc.get("latitude")
            lon = loc.get("longitude")
            if pd.notna(lat):
                entry["latitude"] = float(lat)
            if pd.notna(lon):
                entry["longitude"] = float(lon)

        registry[code] = entry

    logger.info("Built registry with %d delegation(s)", len(registry))
    return registry
