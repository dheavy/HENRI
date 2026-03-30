"""Tests for the OSINT correlation package."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from osint.acled import load_acled
from osint.ioda import load_ioda, _alpha2_to_alpha3
from osint.cloudflare import load_cloudflare
from osint.risk_scorer import compute_risk_cards, _percentile_rank

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_FIXTURES = _PROJECT_ROOT / "data" / "fixtures"
_REFERENCE = _PROJECT_ROOT / "data" / "reference"


@pytest.fixture()
def registry() -> dict:
    """Load the delegation registry from reference data."""
    path = _REFERENCE / "delegations.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    # Minimal fallback for CI without fixtures
    return {
        "ABU": {
            "name": "Abuja",
            "country": "Nigeria",
            "country_iso3": "NGA",
            "region": "AFRICA West",
        },
        "NAI": {
            "name": "Nairobi",
            "country": "Kenya",
            "country_iso3": "KEN",
            "region": "AFRICA East",
        },
        "BAG": {
            "name": "Baghdad",
            "country": "Iraq",
            "country_iso3": "IRQ",
            "region": "NAME",
        },
    }


@pytest.fixture()
def minimal_registry() -> dict:
    """Small registry for targeted unit tests."""
    return {
        "ABU": {
            "name": "Abuja",
            "country": "Nigeria",
            "country_iso3": "NGA",
            "region": "AFRICA West",
        },
        "NDJ": {
            "name": "N'Djamena",
            "country": "Chad",
            "country_iso3": "TCD",
            "region": "AFRICA West",
        },
        "HAR": {
            "name": "Harare",
            "country": "Zimbabwe",
            "country_iso3": "ZWE",
            "region": "AFRICA East",
        },
    }


# ---------------------------------------------------------------------------
# ACLED tests
# ---------------------------------------------------------------------------


class TestACLED:
    def test_load_filters_to_icrc_countries(self, registry: dict) -> None:
        """ACLED results only contain countries present in the registry."""
        path = _FIXTURES / "acled_sample.json"
        if not path.exists():
            pytest.skip("ACLED fixture not available")

        results = load_acled(path, registry)
        assert len(results) > 0, "Expected at least one ICRC country in ACLED data"

        registry_countries = {
            e["country"]
            for e in registry.values()
            if e.get("country")
        }
        for r in results:
            assert r["country"] in registry_countries

    def test_result_structure(self, registry: dict) -> None:
        """Each ACLED result has the expected keys."""
        path = _FIXTURES / "acled_sample.json"
        if not path.exists():
            pytest.skip("ACLED fixture not available")

        results = load_acled(path, registry)
        if not results:
            pytest.skip("No results returned")

        expected_keys = {
            "country", "country_iso3", "events_30d",
            "fatalities_30d", "trend", "top_event_types",
        }
        for r in results:
            assert expected_keys <= set(r.keys())
            assert r["trend"] in ("increasing", "decreasing", "stable")
            assert isinstance(r["top_event_types"], list)

    def test_missing_fixture_returns_empty(self, registry: dict) -> None:
        results = load_acled(Path("/nonexistent/acled.json"), registry)
        assert results == []

    def test_empty_registry_returns_empty(self) -> None:
        path = _FIXTURES / "acled_sample.json"
        if not path.exists():
            pytest.skip("ACLED fixture not available")
        results = load_acled(path, {})
        assert results == []


# ---------------------------------------------------------------------------
# IODA tests
# ---------------------------------------------------------------------------


class TestIODA:
    def test_alpha2_to_alpha3_known_codes(self) -> None:
        assert _alpha2_to_alpha3("TD") == "TCD"  # Chad
        assert _alpha2_to_alpha3("NG") == "NGA"  # Nigeria
        assert _alpha2_to_alpha3("US") == "USA"

    def test_alpha2_to_alpha3_unknown_code(self) -> None:
        assert _alpha2_to_alpha3("XX") is None
        assert _alpha2_to_alpha3("") is None

    def test_load_matches_icrc_countries(self, registry: dict) -> None:
        path = _FIXTURES / "ioda_summary_7d.json"
        if not path.exists():
            pytest.skip("IODA fixture not available")

        results = load_ioda(path, registry)
        assert len(results) > 0

        # All results should have valid ISO3 codes from the registry
        registry_iso3 = {
            e["country_iso3"]
            for e in registry.values()
            if e.get("country_iso3")
        }
        for r in results:
            assert r["country_iso3"] in registry_iso3

    def test_ranking_order(self, registry: dict) -> None:
        path = _FIXTURES / "ioda_summary_7d.json"
        if not path.exists():
            pytest.skip("IODA fixture not available")

        results = load_ioda(path, registry)
        if len(results) < 2:
            pytest.skip("Not enough results to test ranking")

        # Should be sorted by outage_score descending
        scores = [r["outage_score"] for r in results]
        assert scores == sorted(scores, reverse=True)
        # Rank should be sequential
        assert [r["rank"] for r in results] == list(range(1, len(results) + 1))

    def test_result_structure(self, registry: dict) -> None:
        path = _FIXTURES / "ioda_summary_7d.json"
        if not path.exists():
            pytest.skip("IODA fixture not available")

        results = load_ioda(path, registry)
        if not results:
            pytest.skip("No results returned")

        expected_keys = {
            "country", "country_iso3", "outage_score",
            "event_count", "bgp_score", "rank",
        }
        for r in results:
            assert expected_keys <= set(r.keys())


# ---------------------------------------------------------------------------
# Cloudflare tests
# ---------------------------------------------------------------------------


class TestCloudflare:
    def test_load_parses_events(self, registry: dict) -> None:
        path = _FIXTURES / "cf_outages_90d.json"
        if not path.exists():
            pytest.skip("CF fixture not available")

        results = load_cloudflare(path, registry)
        # May or may not match depending on registry countries
        assert isinstance(results, list)

    def test_event_structure(self, minimal_registry: dict) -> None:
        """Verify the shape of parsed Cloudflare events."""
        path = _FIXTURES / "cf_outages_90d.json"
        if not path.exists():
            pytest.skip("CF fixture not available")

        results = load_cloudflare(path, minimal_registry)
        for r in results:
            assert "country" in r
            assert "country_iso3" in r
            assert "outage_count" in r
            assert isinstance(r["events"], list)
            for ev in r["events"]:
                assert "type" in ev
                assert "start" in ev

    def test_missing_fixture(self, registry: dict) -> None:
        results = load_cloudflare(Path("/nonexistent/cf.json"), registry)
        assert results == []


# ---------------------------------------------------------------------------
# Risk scorer tests
# ---------------------------------------------------------------------------


class TestRiskScorer:
    def test_percentile_rank_basic(self) -> None:
        values = [10, 20, 30, 40, 50]
        ranks = _percentile_rank(values)
        assert len(ranks) == 5
        assert ranks[0] == 0.0  # smallest
        assert ranks[-1] == 100.0  # largest

    def test_percentile_rank_all_zeros(self) -> None:
        ranks = _percentile_rank([0, 0, 0])
        assert ranks == [0.0, 0.0, 0.0]

    def test_percentile_rank_empty(self) -> None:
        assert _percentile_rank([]) == []

    def test_compute_risk_cards(self, registry: dict) -> None:
        """Integration test: compute risk cards from fixture data."""
        data_dir = _PROJECT_ROOT / "data"
        if not (_FIXTURES / "acled_sample.json").exists():
            pytest.skip("OSINT fixtures not available")

        cards = compute_risk_cards(data_dir, registry)
        assert len(cards) > 0

        # Should be sorted by combined_risk descending
        scores = [c["combined_risk"] for c in cards]
        assert scores == sorted(scores, reverse=True)

        # Each card should have the expected keys
        expected_keys = {
            "country", "country_iso3", "acled_events",
            "acled_fatalities", "ioda_score", "cf_outages",
            "snow_sitedown", "combined_risk",
        }
        for card in cards:
            assert expected_keys <= set(card.keys())
            assert 0 <= card["combined_risk"] <= 100

    def test_normalization_bounds(self) -> None:
        """Percentile ranks should be between 0 and 100."""
        import random
        random.seed(42)
        values = [random.uniform(0, 1000) for _ in range(50)]
        ranks = _percentile_rank(values)
        for r in ranks:
            assert 0.0 <= r <= 100.0
