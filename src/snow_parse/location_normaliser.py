"""Clean and normalise the cmn_location CSV — deduplicate countries, map to ISO 3166-1 alpha-3."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import csv

import pandas as pd
import pycountry

logger = logging.getLogger(__name__)

# Manual overrides for country names pycountry can't fuzzy-match
_COUNTRY_ALIASES: dict[str, str] = {
    "Democratic Republic Of The Congo": "COD",
    "Republic Of The Congo": "COG",
    "Cote D'Ivoire": "CIV",
    "Côte D'Ivoire": "CIV",
    "Eswatini (Swaziland)": "SWZ",
    "Republic Of Korea": "KOR",
    "Lao People'S Democratic Republic": "LAO",
}


def _clean_country(raw: object) -> Optional[str]:
    """Normalise a country string.

    Handles patterns like ``"Mali | Mali"``, ``"South Sudan | Soudan du Sud"``,
    and all-caps entries like ``"CAMEROON"``.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    # Split on ' | ' and take the first part
    first = raw.split("|")[0].strip()
    if not first:
        return None
    # Title-case (handles CAMEROON → Cameroon, MALI → Mali, etc.)
    return first.title()


def _iso3_lookup(country_name: Optional[str]) -> Optional[str]:
    """Return ISO 3166-1 alpha-3 code for *country_name*, with fuzzy fallback."""
    if not country_name or not isinstance(country_name, str):
        return None
    # Check manual overrides first
    if country_name in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[country_name]
    # Exact lookup
    try:
        result = pycountry.countries.lookup(country_name)
        return result.alpha_3
    except LookupError:
        pass
    # Fuzzy search
    try:
        results = pycountry.countries.search_fuzzy(country_name)
        if results:
            return results[0].alpha_3
    except LookupError:
        pass
    logger.warning("Could not resolve country to ISO alpha-3: %s", country_name)
    return None


def normalise_locations(csv_path: Path, output_path: Path) -> pd.DataFrame:
    """Read the cmn_location CSV at *csv_path*, normalise it, write to *output_path*,
    and return the resulting :class:`~pandas.DataFrame`.

    Steps:
    1. Deduplicate / clean country names.
    2. Map to ISO 3166-1 alpha-3 (with fuzzy fallback).
    3. Flag entries that have city + country but no GPS coordinates.
    """
    try:
        df = pd.read_csv(csv_path, encoding="utf-8")
    except UnicodeDecodeError:
        df = pd.read_csv(csv_path, encoding="latin-1")

    # Clean country names
    if "country" in df.columns:
        df["country_clean"] = df["country"].apply(_clean_country)
    else:
        logger.warning("No 'country' column found — skipping country cleaning")
        df["country_clean"] = None

    # ISO alpha-3 lookup
    df["country_iso3"] = df["country_clean"].apply(_iso3_lookup)

    # Flag rows missing GPS but having city + country
    has_city = df.get("city", pd.Series(dtype=str)).notna() & (
        df.get("city", pd.Series(dtype=str)).astype(str).str.strip() != ""
    )
    has_country = df["country_clean"].notna()
    # Convert lat/lon to numeric, coercing empty strings to NaN
    if "latitude" in df.columns:
        df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    if "longitude" in df.columns:
        df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    has_lat = df.get("latitude", pd.Series(dtype=float)).notna()
    has_lon = df.get("longitude", pd.Series(dtype=float)).notna()
    df["missing_gps"] = has_city & has_country & (~has_lat | ~has_lon)

    missing_count = df["missing_gps"].sum()
    if missing_count:
        logger.info("%d location(s) have city+country but no GPS coordinates", missing_count)

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, quoting=csv.QUOTE_ALL)
    logger.info("Normalised locations written to %s", output_path)

    return df
