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

# Curated mapping of well-known ICRC delegation codes to (city, country, region).
# Region values match the Prometheus label convention.
_KNOWN_DELEGATIONS: dict[str, tuple[str, str, str]] = {
    # AFRICA East
    "JUB": ("Juba", "South Sudan", "AFRICA East"),
    "NAI": ("Nairobi", "Kenya", "AFRICA East"),
    "ADD": ("Addis Ababa", "Ethiopia", "AFRICA East"),
    "KHA": ("Khartoum", "Sudan", "AFRICA East"),
    "MOG": ("Mogadishu", "Somalia", "AFRICA East"),
    "DAR": ("Dar es Salaam", "Tanzania", "AFRICA East"),
    "YEI": ("Yei", "South Sudan", "AFRICA East"),
    "WAU": ("Wau", "South Sudan", "AFRICA East"),
    "MAL": ("Malakal", "South Sudan", "AFRICA East"),
    "BOR": ("Bor", "South Sudan", "AFRICA East"),
    "BNG": ("Bangui", "Central African Republic", "AFRICA East"),
    "DJI": ("Djibouti", "Djibouti", "AFRICA East"),
    "ASM": ("Asmara", "Eritrea", "AFRICA East"),
    "KAM": ("Kampala", "Uganda", "AFRICA East"),
    "KIG": ("Kigali", "Rwanda", "AFRICA East"),
    "BUJ": ("Bujumbura", "Burundi", "AFRICA East"),
    "LIL": ("Lilongwe", "Malawi", "AFRICA East"),
    "HAR": ("Harare", "Zimbabwe", "AFRICA East"),
    "MAP": ("Maputo", "Mozambique", "AFRICA East"),
    "LUS": ("Lusaka", "Zambia", "AFRICA East"),
    "PRE": ("Pretoria", "South Africa", "AFRICA East"),
    # AFRICA West
    "ABJ": ("Abidjan", "Cote d'Ivoire", "AFRICA West"),
    "ABU": ("Abuja", "Nigeria", "AFRICA West"),
    "DAK": ("Dakar", "Senegal", "AFRICA West"),
    "ACC": ("Accra", "Ghana", "AFRICA West"),
    "BAM": ("Bamako", "Mali", "AFRICA West"),
    "GAO": ("Gao", "Mali", "AFRICA West"),
    "TOM": ("Timbuktu", "Mali", "AFRICA West"),
    "NIA": ("Niamey", "Niger", "AFRICA West"),
    "NDA": ("N'Djamena", "Chad", "AFRICA West"),
    "NDJ": ("N'Djamena", "Chad", "AFRICA West"),
    "YAO": ("Yaounde", "Cameroon", "AFRICA West"),
    "MAR": ("Maroua", "Cameroon", "AFRICA West"),
    "CON": ("Conakry", "Guinea", "AFRICA West"),
    "MON": ("Monrovia", "Liberia", "AFRICA West"),
    "FRE": ("Freetown", "Sierra Leone", "AFRICA West"),
    "OUG": ("Ouagadougou", "Burkina Faso", "AFRICA West"),
    "COT": ("Cotonou", "Benin", "AFRICA West"),
    "KOW": ("Kinshasa", "Democratic Republic of the Congo", "AFRICA West"),
    "LON": ("London", "United Kingdom", "AFRICA West"),
    # NAME (Near and Middle East)
    "BAG": ("Baghdad", "Iraq", "NAME"),
    "ERB": ("Erbil", "Iraq", "NAME"),
    "BAS": ("Basra", "Iraq", "NAME"),
    "BEY": ("Beirut", "Lebanon", "NAME"),
    "DAM": ("Damascus", "Syria", "NAME"),
    "ALE": ("Aleppo", "Syria", "NAME"),
    "AMM": ("Amman", "Jordan", "NAME"),
    "TEH": ("Tehran", "Iran", "NAME"),
    "SAN": ("Sana'a", "Yemen", "NAME"),
    "ADE": ("Aden", "Yemen", "NAME"),
    "TEL": ("Tel Aviv", "Israel", "NAME"),
    "GAZ": ("Gaza", "Palestine", "NAME"),
    "KUW": ("Kuwait City", "Kuwait", "NAME"),
    "SAR": ("Sana'a Regional", "Yemen", "NAME"),
    # EURASIA
    "MOS": ("Moscow", "Russia", "EURASIA"),
    "KYI": ("Kyiv", "Ukraine", "EURASIA"),
    "DOI": ("Donetsk", "Ukraine", "EURASIA"),
    "TBI": ("Tbilisi", "Georgia", "EURASIA"),
    "BAK": ("Baku", "Azerbaijan", "EURASIA"),
    "BIS": ("Bishkek", "Kyrgyzstan", "EURASIA"),
    "TAS": ("Tashkent", "Uzbekistan", "EURASIA"),
    "DUS": ("Dushanbe", "Tajikistan", "EURASIA"),
    "PAR": ("Paris", "France", "EURASIA"),
    # ASIA
    "DEL": ("New Delhi", "India", "ASIA"),
    "ISL": ("Islamabad", "Pakistan", "ASIA"),
    "KAB": ("Kabul", "Afghanistan", "ASIA"),
    "COL": ("Colombo", "Sri Lanka", "ASIA"),
    "DHK": ("Dhaka", "Bangladesh", "ASIA"),
    "BAN": ("Bangkok", "Thailand", "ASIA"),
    "MAN": ("Manila", "Philippines", "ASIA"),
    "JAK": ("Jakarta", "Indonesia", "ASIA"),
    "YAN": ("Yangon", "Myanmar", "ASIA"),
    "PEK": ("Beijing", "China", "ASIA"),
    "SUV": ("Suva", "Fiji", "ASIA"),
    "DIL": ("Dili", "Timor-Leste", "ASIA"),
    "KUA": ("Kuala Lumpur", "Malaysia", "ASIA"),
    # AMERICAS
    "BOG": ("Bogota", "Colombia", "AMERICAS"),
    "LIM": ("Lima", "Peru", "AMERICAS"),
    "MEX": ("Mexico City", "Mexico", "AMERICAS"),
    "BRA": ("Brasilia", "Brazil", "AMERICAS"),
    "CAR": ("Caracas", "Venezuela", "AMERICAS"),
    "WAS": ("Washington", "United States", "AMERICAS"),
    "GUA": ("Guatemala City", "Guatemala", "AMERICAS"),
    "TEG": ("Tegucigalpa", "Honduras", "AMERICAS"),
    # HQ
    "GVA": ("Geneva", "Switzerland", "HQ"),
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


def build_subsite_map(incidents_df: pd.DataFrame) -> dict[str, str]:
    """Build a mapping from sub-site delegation codes to parent delegation codes.

    Uses the ``assignment_group`` field: if a ticket's hostname-derived
    ``delegation_code`` differs from the parent code in its assignment group
    (``<PARENT> ICT L2 Support``), the hostname code is a sub-site of that parent.

    Returns ``{sub_code: parent_code}`` for all observed sub-site codes.
    Also includes identity mappings ``{parent: parent}`` for parent codes.
    """
    subsite_map: dict[str, str] = {}
    if "delegation_code" not in incidents_df.columns or "assignment_group" not in incidents_df.columns:
        return subsite_map

    for _, row in (
        incidents_df[["delegation_code", "assignment_group"]]
        .dropna()
        .drop_duplicates()
        .iterrows()
    ):
        m = _ASSIGNMENT_RE.match(str(row["assignment_group"]).strip())
        if not m:
            continue
        parent = m.group(1).upper()
        child = str(row["delegation_code"]).upper()
        subsite_map[child] = parent
        # Ensure parent maps to itself
        subsite_map[parent] = parent

    logger.info(
        "Built sub-site map: %d codes, %d are sub-sites",
        len(subsite_map),
        sum(1 for k, v in subsite_map.items() if k != v),
    )
    return subsite_map


def build_registry(
    incidents_df: pd.DataFrame,
    locations_df: pd.DataFrame,
    grafana_available: bool = False,
) -> dict[str, dict[str, Any]]:
    """Build a delegation registry keyed by **parent** delegation code.

    Each entry contains:
    - ``name``: city/delegation name
    - ``region``: ICT region (from Grafana, or None)
    - ``country``: country name
    - ``country_iso3``: ISO 3166-1 alpha-3
    - ``smt_assignmentgroup``: the ServiceNow assignment group string
    - ``latitude``: float or None
    - ``longitude``: float or None
    - ``source``: ``"servicenow_only"`` when Grafana is not available
    - ``sub_sites``: list of sub-site codes that map to this parent
    """
    code_to_group = _extract_codes_from_groups(incidents_df)
    if not code_to_group:
        return {}

    # Build sub-site map
    subsite_map = build_subsite_map(incidents_df)

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

    # Collect sub-sites per parent
    parent_subsites: dict[str, list[str]] = {}
    for child, parent in subsite_map.items():
        if child != parent:
            parent_subsites.setdefault(parent, []).append(child)

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
            "sub_sites": sorted(parent_subsites.get(code, [])),
        }

        # Priority 1: curated delegation lookup
        if code in _KNOWN_DELEGATIONS:
            city_name, country_name, region = _KNOWN_DELEGATIONS[code]
            entry["name"] = city_name
            entry["country"] = country_name
            entry["country_iso3"] = _iso3_for_country(country_name)
            entry["region"] = region
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
