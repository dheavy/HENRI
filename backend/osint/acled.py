"""ACLED conflict event data — live API pull and fixture loading.

Live API flow:
1. POST https://acleddata.com/oauth/token (grant_type=password) → bearer token
2. GET  https://acleddata.com/api/acled/read?country=<name>&limit=5000
        &event_date=<start>|<end>&event_date_where=BETWEEN

Token refresh: access_token expires in 24h; refresh via grant_type=refresh_token
(refresh_token valid 14 days). Cached to data/.acled_token.json.

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
_CLIENT_ID = "acled"


def _get_icrc_countries(registry: dict[str, dict[str, Any]]) -> dict[str, tuple[str, str]]:
    """Return {iso3: (display_country_name, iso3)} for ICRC field delegations.

    Keyed by ISO3 because country names are unreliable: ACLED uses
    "Cote d'Ivoire" while the registry has both "Côte D'Ivoire" and
    "Cote d'Ivoire" for the same delegation; "Democratic Republic of
    Congo" vs "République Démocratique Du Congo"; etc. Lowercase string
    matching dropped ~80% of countries in production.
    """
    countries: dict[str, tuple[str, str]] = {}
    for entry in registry.values():
        country = entry.get("country")
        iso3 = entry.get("country_iso3")
        region = entry.get("region", "")
        if country and iso3 and region and region != "HQ":
            # First-write wins: keeps the first display name we see for
            # each ISO3, which is fine since name is just for the UI.
            countries.setdefault(iso3, (country, iso3))
    return countries


class _AcledTokenManager:
    """Manage ACLED OAuth tokens with caching and automatic refresh.

    Tokens are cached to ``<data_dir>/.acled_token.json`` (chmod 0o600).
    The access_token expires in 24 h; the refresh_token in 14 days.
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        self._cache_path = (data_dir or Path("data")) / ".acled_token.json"
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at: float = 0.0
        self._load_cache()

    def _load_cache(self) -> None:
        if not self._cache_path.exists():
            return
        try:
            with open(self._cache_path) as f:
                cached = json.load(f)
            self._access_token = cached.get("access_token")
            self._refresh_token = cached.get("refresh_token")
            self._expires_at = cached.get("expires_at", 0.0)
        except (json.JSONDecodeError, OSError):
            logger.debug("Could not load ACLED token cache")

    def _save_cache(self) -> None:
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(json.dumps({
                "access_token": self._access_token,
                "refresh_token": self._refresh_token,
                "expires_at": self._expires_at,
            }))
            self._cache_path.chmod(0o600)
        except OSError:
            logger.debug("Could not save ACLED token cache")

    def _parse_token_response(self, data: dict) -> bool:
        token = data.get("access_token")
        if not token:
            return False
        self._access_token = token
        self._refresh_token = data.get("refresh_token", self._refresh_token)
        expires_in = int(data.get("expires_in", 86400))
        # Expire 5 minutes early to avoid edge cases
        self._expires_at = time.time() + expires_in - 300
        self._save_cache()
        return True

    def _password_grant(self) -> bool:
        """Authenticate with username/password (initial login)."""
        email = os.getenv("ACLED_EMAIL", "")
        password = os.getenv("ACLED_PASSWORD", "")
        if not email or not password:
            logger.warning("ACLED_EMAIL and ACLED_PASSWORD not set")
            return False
        try:
            resp = httpx.post(
                _TOKEN_URL,
                data={
                    "username": email,
                    "password": password,
                    "grant_type": "password",
                    "client_id": _CLIENT_ID,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15.0,
            )
            if resp.status_code in (401, 403):
                logger.warning("ACLED: credentials rejected (%d)", resp.status_code)
                return False
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict):
                return False
            if self._parse_token_response(data):
                logger.info("ACLED: authenticated via password grant")
                return True
            logger.warning("ACLED: no access_token in response")
            return False
        except httpx.RequestError as e:
            logger.debug("ACLED auth network error: %s", e)
            logger.warning("ACLED: authentication failed (network)")
            return False
        except httpx.HTTPStatusError:
            logger.warning("ACLED: authentication failed")
            return False

    def _refresh_grant(self) -> bool:
        """Refresh the access token using the stored refresh_token."""
        if not self._refresh_token:
            return False
        try:
            resp = httpx.post(
                _TOKEN_URL,
                data={
                    "refresh_token": self._refresh_token,
                    "grant_type": "refresh_token",
                    "client_id": _CLIENT_ID,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=15.0,
            )
            if resp.status_code in (401, 403):
                logger.info("ACLED: refresh token expired; re-authenticating")
                self._refresh_token = None
                return False
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict):
                return False
            if self._parse_token_response(data):
                logger.info("ACLED: token refreshed successfully")
                return True
            return False
        except (httpx.RequestError, httpx.HTTPStatusError):
            logger.debug("ACLED: refresh grant failed")
            return False

    def get_token(self) -> str | None:
        """Return a valid access token, refreshing or re-authenticating as needed."""
        # 1. Cached token still valid?
        if self._access_token and time.time() < self._expires_at:
            return self._access_token

        # 2. Try refresh
        if self._refresh_token and self._refresh_grant():
            return self._access_token

        # 3. Full password grant
        if self._password_grant():
            return self._access_token

        return None


def fetch_acled_live(
    registry: dict[str, dict[str, Any]],
    days: int = 90,
    output_path: Path | None = None,
    data_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Pull ACLED events for all ICRC countries over the last *days* days.

    Uses OAuth password grant with automatic token refresh.
    Paginates by country (5000 per call). Saves to parquet if *output_path* given.
    Returns the raw event list, or [] if auth fails / API unavailable.
    """
    token_mgr = _AcledTokenManager(data_dir)
    token = token_mgr.get_token()
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

    import pycountry as _pc
    with httpx.Client(timeout=30.0) as client:
        for iso3, (country_name, _) in sorted(icrc_countries.items()):
            time.sleep(1.0)  # Rate limit: max 1 req/s
            # Refresh token if needed before each request
            current_token = token_mgr.get_token()
            if not current_token:
                logger.warning("ACLED: token expired and refresh failed; aborting")
                break
            # Query ACLED by numeric ISO 3166-1 instead of country name.
            # Country name matching against ACLED's catalogue is fragile
            # ("Cote d'Ivoire" vs "Côte d'Ivoire", "DR Congo" vs
            # "Democratic Republic of Congo", etc.) and dropped ~80% of
            # countries in production. Numeric ISO is unambiguous.
            try:
                pc_country = _pc.countries.get(alpha_3=iso3)
                iso_num = pc_country.numeric if pc_country else None
            except (AttributeError, LookupError):
                iso_num = None
            if not iso_num:
                logger.debug("ACLED: no numeric ISO for %s; skipping", iso3)
                continue
            try:
                resp = client.get(
                    _API_URL,
                    headers={"Authorization": f"Bearer {current_token}"},
                    params={
                        "iso": iso_num,
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
                    # Token may have been invalidated server-side; try refresh once
                    token_mgr._expires_at = 0  # Force refresh
                    refreshed = token_mgr.get_token()
                    if not refreshed:
                        logger.warning("ACLED: auth rejected and refresh failed; aborting")
                        return []
                    continue  # Retry this country on next iteration
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

    # Map ACLED's numeric ISO 3166-1 code → alpha-3 once, lazily, to keep
    # the per-event loop a hash lookup.
    import pycountry as _pc
    iso_num_to_alpha3: dict[str, str] = {}

    def _resolve_iso3(ev: dict) -> str | None:
        """ACLED events ship `iso` (numeric) and `country` (name).
        Prefer numeric ISO; fall back to fuzzy name match for legacy
        events that lack `iso` (rare in current API responses).
        """
        iso_num = ev.get("iso")
        if iso_num is not None and iso_num != "":
            # Coerce robustly: parquet round-trips can turn an int column
            # into numpy.float64 (e.g. 566.0) if any row had a NaN. Naive
            # str(566.0).zfill(3) gives "566.0" → pycountry lookup fails →
            # 0 events match → silent empty result → fallback to fixture.
            try:
                key = str(int(float(iso_num))).zfill(3)
            except (TypeError, ValueError):
                return None
            cached = iso_num_to_alpha3.get(key)
            if cached is not None:
                return cached or None
            try:
                c = _pc.countries.get(numeric=key)
                alpha3 = c.alpha_3 if c else ""
            except (AttributeError, LookupError, KeyError):
                alpha3 = ""
            iso_num_to_alpha3[key] = alpha3
            return alpha3 or None
        # Fallback: fuzzy name lookup. pycountry handles most diacritic
        # and apostrophe variants ("Cote d'Ivoire" → CIV).
        name = ev.get("country")
        if not name:
            return None
        try:
            matches = _pc.countries.search_fuzzy(name)
            return matches[0].alpha_3 if matches else None
        except LookupError:
            return None

    country_events: dict[str, list[dict]] = {}
    for ev in events:
        try:
            d = datetime.strptime(ev["event_date"], "%Y-%m-%d").date()
        except (ValueError, KeyError):
            continue
        if d < cutoff_30:
            continue
        iso3 = _resolve_iso3(ev)
        if iso3 and iso3 in icrc_countries:
            country_events.setdefault(iso3, []).append({"date": d, "event": ev})

    results = []
    for iso3, items in country_events.items():
        country_name, iso3 = icrc_countries[iso3]
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
    """Load ACLED data — live parquet → live API → fixture fallback.

    Priority:
    1. If *use_fixtures*: use fixture file only
    2. Processed parquet from a previous live pull (always checked)
    3. Live API pull (requires ACLED_EMAIL + ACLED_PASSWORD)
    4. Fixture file as last resort
    """
    if use_fixtures:
        fixture = data_dir / "fixtures" / "acled_sample.json"
        return load_acled(fixture, registry)

    icrc_countries = _get_icrc_countries(registry)
    if not icrc_countries:
        for entry in registry.values():
            c = entry.get("country")
            iso3 = entry.get("country_iso3")
            if c and iso3:
                icrc_countries[c.lower()] = (c, iso3)

    # 1. Try processed parquet from a previous pull (regardless of creds)
    parquet_path = data_dir / "processed" / "acled_events.parquet"
    if parquet_path.exists():
        logger.info("Loading ACLED from processed parquet")
        df = pd.read_parquet(parquet_path)
        events = df.to_dict("records")
        result = _summarise_events(events, icrc_countries)
        if result:
            return result

    # 2. Live API pull (requires credentials)
    if os.getenv("ACLED_EMAIL") and os.getenv("ACLED_PASSWORD"):
        events = fetch_acled_live(
            registry, days=90,
            output_path=parquet_path,
            data_dir=data_dir,
        )
        if events:
            return _summarise_events(events, icrc_countries)
        logger.warning("ACLED live pull returned no data")

    # 3. Fixture fallback
    logger.info("Falling back to ACLED fixture")
    fixture = data_dir / "fixtures" / "acled_sample.json"
    return load_acled(fixture, registry)
