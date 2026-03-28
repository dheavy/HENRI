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

# Curated mapping of well-known ICRC delegation codes to city/country.
# These are public information from ICRC's operational presence.
_KNOWN_DELEGATIONS: dict[str, tuple[str, str]] = {
    # AFRICA East
    "JUB": ("Juba", "South Sudan"), "NAI": ("Nairobi", "Kenya"),
    "ADD": ("Addis Ababa", "Ethiopia"), "KHA": ("Khartoum", "Sudan"),
    "MOG": ("Mogadishu", "Somalia"), "DAR": ("Dar es Salaam", "Tanzania"),
    "YEI": ("Yei", "South Sudan"), "WAU": ("Wau", "South Sudan"),
    "MAL": ("Malakal", "South Sudan"), "BOR": ("Bor", "South Sudan"),
    "BNG": ("Bangui", "Central African Republic"),
    "DJI": ("Djibouti", "Djibouti"), "ASM": ("Asmara", "Eritrea"),
    "KAM": ("Kampala", "Uganda"), "KIG": ("Kigali", "Rwanda"),
    "BUJ": ("Bujumbura", "Burundi"), "LIL": ("Lilongwe", "Malawi"),
    "HAR": ("Harare", "Zimbabwe"), "MAP": ("Maputo", "Mozambique"),
    "LUS": ("Lusaka", "Zambia"), "PRE": ("Pretoria", "South Africa"),
    # AFRICA West
    "ABJ": ("Abidjan", "Cote d'Ivoire"), "ABU": ("Abuja", "Nigeria"),
    "DAK": ("Dakar", "Senegal"), "ACC": ("Accra", "Ghana"),
    "BAM": ("Bamako", "Mali"), "GAO": ("Gao", "Mali"),
    "TOM": ("Timbuktu", "Mali"), "NIA": ("Niamey", "Niger"),
    "NDA": ("N'Djamena", "Chad"), "YAO": ("Yaounde", "Cameroon"),
    "MAR": ("Maroua", "Cameroon"), "CON": ("Conakry", "Guinea"),
    "MON": ("Monrovia", "Liberia"), "FRE": ("Freetown", "Sierra Leone"),
    "OUG": ("Ouagadougou", "Burkina Faso"), "LON": ("London", "United Kingdom"),
    # NAME (Near and Middle East)
    "BAG": ("Baghdad", "Iraq"), "ERB": ("Erbil", "Iraq"),
    "BAS": ("Basra", "Iraq"), "BEY": ("Beirut", "Lebanon"),
    "DAM": ("Damascus", "Syria"), "ALE": ("Aleppo", "Syria"),
    "AMM": ("Amman", "Jordan"), "TEH": ("Tehran", "Iran"),
    "SAN": ("Sana'a", "Yemen"), "ADE": ("Aden", "Yemen"),
    "TEL": ("Tel Aviv", "Israel"), "GAZ": ("Gaza", "Palestine"),
    "KUW": ("Kuwait City", "Kuwait"),
    # EURASIA
    "MOS": ("Moscow", "Russia"), "KYI": ("Kyiv", "Ukraine"),
    "DOI": ("Donetsk", "Ukraine"), "TBI": ("Tbilisi", "Georgia"),
    "BAK": ("Baku", "Azerbaijan"), "BIS": ("Bishkek", "Kyrgyzstan"),
    "TAS": ("Tashkent", "Uzbekistan"), "DUS": ("Dushanbe", "Tajikistan"),
    # ASIA
    "DEL": ("New Delhi", "India"), "ISL": ("Islamabad", "Pakistan"),
    "KAB": ("Kabul", "Afghanistan"), "COL": ("Colombo", "Sri Lanka"),
    "DHK": ("Dhaka", "Bangladesh"), "BAN": ("Bangkok", "Thailand"),
    "MAN": ("Manila", "Philippines"), "JAK": ("Jakarta", "Indonesia"),
    "YAN": ("Yangon", "Myanmar"), "PEK": ("Beijing", "China"),
    "SUV": ("Suva", "Fiji"), "DIL": ("Dili", "Timor-Leste"),
    "KUA": ("Kuala Lumpur", "Malaysia"),
    # AMERICAS
    "BOG": ("Bogota", "Colombia"), "LIM": ("Lima", "Peru"),
    "MEX": ("Mexico City", "Mexico"), "BRA": ("Brasilia", "Brazil"),
    "CAR": ("Caracas", "Venezuela"), "WAS": ("Washington", "United States"),
    "GUA": ("Guatemala City", "Guatemala"), "MAN": ("Managua", "Nicaragua"),
    "TEG": ("Tegucigalpa", "Honduras"),
    # HQ
    "GVA": ("Geneva", "Switzerland"),
}

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


def _match_code_to_location(
    code: str,
    city_to_rows: dict[str, list[pd.Series]],
    city_candidates: list[str],
) -> Optional[pd.Series]:
    """Match a delegation code to a location row.

    Strategy (in priority order):
    1. Prefix match: code is a case-insensitive prefix of a city name
       (JUB→Juba, ABE→Abeche, NAI→Nairobi, ADD→Addis Ababa)
    2. Fuzzy match with low threshold (catches partial matches)
    """
    if not city_candidates:
        return None

    code_lower = code.lower()

    # Strategy 1: prefix match — most ICRC codes are city abbreviations
    for city in city_candidates:
        if city.lower().startswith(code_lower):
            rows = city_to_rows.get(city, [])
            if rows:
                # Prefer rows with GPS data
                for r in rows:
                    if pd.notna(r.get("latitude")) and pd.notna(r.get("longitude")):
                        return r
                return rows[0]

    # Strategy 2: fuzzy match (only for longer codes where fuzzy is reliable)
    if len(code) >= 4:
        result = fuzz_process.extractOne(code, city_candidates, scorer=fuzz.partial_ratio)
        if result and result[1] >= 85:
            rows = city_to_rows.get(result[0], [])
            if rows:
                return rows[0]

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

    # Build a city→rows lookup from locations (multiple locations per city)
    city_candidates: list[str] = []
    city_to_rows: dict[str, list[pd.Series]] = {}
    if "city" in locations_df.columns:
        for _, loc_row in locations_df.iterrows():
            city_val = loc_row.get("city")
            if isinstance(city_val, str) and city_val.strip():
                clean = city_val.strip()
                if clean not in city_to_rows:
                    city_candidates.append(clean)
                    city_to_rows[clean] = []
                city_to_rows[clean].append(loc_row)

    matched_count = 0
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

        # Priority 1: curated delegation lookup
        if code in _KNOWN_DELEGATIONS:
            city_name, country_name = _KNOWN_DELEGATIONS[code]
            entry["name"] = city_name
            entry["country"] = country_name
            entry["country_iso3"] = _iso3_for_country(country_name)
            matched_count += 1

        # Priority 2: match against cmn_location data
        loc = _match_code_to_location(code, city_to_rows, city_candidates)
        if loc is not None:
            if not entry["country"]:
                matched_count += 1
            country = loc.get("country_clean") if "country_clean" in loc.index else loc.get("country")
            if isinstance(country, str) and not entry["country"]:
                entry["country"] = country
                entry["country_iso3"] = _iso3_for_country(country)
            lat = loc.get("latitude")
            lon = loc.get("longitude")
            if pd.notna(lat):
                entry["latitude"] = float(lat)
            if pd.notna(lon):
                entry["longitude"] = float(lon)

        registry[code] = entry

    logger.info(
        "Built registry with %d delegation(s), %d matched to locations",
        len(registry), matched_count,
    )
    return registry
