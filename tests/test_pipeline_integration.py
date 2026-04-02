"""Integration tests — run the full pipeline against fixture data."""

import json
from pathlib import Path

import pandas as pd
import pytest

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "data" / "fixtures"
INCIDENTS_CSV = FIXTURES_DIR / "incidents_sample.csv"
LOCATIONS_CSV = FIXTURES_DIR / "locations.csv"


@pytest.fixture(scope="module")
def parsed_df() -> pd.DataFrame:
    """Load and parse fixture incidents (cached across tests in this module)."""
    from snow_parse.parser import load_and_parse
    data_dir = FIXTURES_DIR.parent  # data/
    df = load_and_parse(data_dir)
    assert not df.empty, "Failed to load fixture data"
    return df


@pytest.fixture(scope="module")
def enriched_df(parsed_df: pd.DataFrame) -> pd.DataFrame:
    """Enrich with Prometheus and human parsers."""
    from snow_parse.prometheus_parser import enrich_prometheus
    from snow_parse.human_parser import enrich_human
    df = enrich_prometheus(parsed_df)
    df = enrich_human(df)
    return df


class TestFixtureLoading:
    @pytest.mark.skipif(not INCIDENTS_CSV.exists(), reason="Fixture data not available")
    def test_loads_50k_incidents(self, parsed_df: pd.DataFrame):
        assert len(parsed_df) == 52_345

    @pytest.mark.skipif(not INCIDENTS_CSV.exists(), reason="Fixture data not available")
    def test_has_required_columns(self, parsed_df: pd.DataFrame):
        required = {"sys_id", "number", "short_description", "is_prometheus", "opened_dt"}
        assert required.issubset(set(parsed_df.columns))

    @pytest.mark.skipif(not INCIDENTS_CSV.exists(), reason="Fixture data not available")
    def test_timestamps_parsed(self, parsed_df: pd.DataFrame):
        # Most opened_dt should be non-null
        non_null = parsed_df["opened_dt"].notna().sum()
        assert non_null > 51_000  # Allow some nulls


class TestPrometheusEnrichment:
    @pytest.mark.skipif(not INCIDENTS_CSV.exists(), reason="Fixture data not available")
    def test_74_percent_prometheus(self, enriched_df: pd.DataFrame):
        prom_pct = enriched_df["is_prometheus"].sum() / len(enriched_df) * 100
        assert 70 < prom_pct < 80  # ~74%

    @pytest.mark.skipif(not INCIDENTS_CSV.exists(), reason="Fixture data not available")
    def test_delegation_codes_extracted(self, enriched_df: pd.DataFrame):
        prom = enriched_df[enriched_df["is_prometheus"]]
        with_code = prom["delegation_code"].notna().sum()
        # Most Prometheus tickets should get a code
        assert with_code / len(prom) > 0.5

    @pytest.mark.skipif(not INCIDENTS_CSV.exists(), reason="Fixture data not available")
    def test_alert_names_extracted(self, enriched_df: pd.DataFrame):
        prom = enriched_df[enriched_df["is_prometheus"]]
        with_alert = prom["alert_name"].notna().sum()
        assert with_alert / len(prom) > 0.9

    @pytest.mark.skipif(not INCIDENTS_CSV.exists(), reason="Fixture data not available")
    def test_known_categories_present(self, enriched_df: pd.DataFrame):
        categories = enriched_df["alert_category"].unique()
        assert "site_down" in categories
        assert "server" in categories
        assert "other" in categories


class TestHumanEnrichment:
    @pytest.mark.skipif(not INCIDENTS_CSV.exists(), reason="Fixture data not available")
    def test_human_tickets_have_keywords(self, enriched_df: pd.DataFrame):
        human = enriched_df[~enriched_df["is_prometheus"]]
        with_kw = human[human["matched_keywords"] != "[]"]
        # Some human tickets should match network keywords
        assert len(with_kw) > 100

    @pytest.mark.skipif(not INCIDENTS_CSV.exists(), reason="Fixture data not available")
    def test_network_related_combines_both(self, enriched_df: pd.DataFrame):
        net = enriched_df[enriched_df["is_network_related"]]
        # Should have both Prometheus and human tickets
        prom_net = net[net["is_prometheus"]]
        human_net = net[~net["is_prometheus"]]
        assert len(prom_net) > 0
        assert len(human_net) > 0


class TestLocationNormalisation:
    @pytest.mark.skipif(not LOCATIONS_CSV.exists(), reason="Fixture data not available")
    def test_normalise_locations(self, tmp_path: Path):
        from snow_parse.location_normaliser import normalise_locations
        output = tmp_path / "locations_clean.csv"
        df = normalise_locations(LOCATIONS_CSV, output)
        assert len(df) == 2265
        assert "country_clean" in df.columns
        assert "country_iso3" in df.columns
        assert "missing_gps" in df.columns
        assert output.exists()

    @pytest.mark.skipif(not LOCATIONS_CSV.exists(), reason="Fixture data not available")
    def test_country_dedup(self, tmp_path: Path):
        from snow_parse.location_normaliser import normalise_locations
        output = tmp_path / "locations_clean.csv"
        df = normalise_locations(LOCATIONS_CSV, output)
        # No " | " should remain in cleaned country names
        clean = df["country_clean"].dropna()
        assert not clean.str.contains(r"\|").any()


class TestDelegationRegistry:
    @pytest.mark.skipif(not INCIDENTS_CSV.exists(), reason="Fixture data not available")
    def test_registry_from_fixtures(self, enriched_df: pd.DataFrame):
        from snow_parse.delegation_registry import build_registry
        registry = build_registry(enriched_df, pd.DataFrame())
        assert len(registry) == 203  # Known count from fixture data
        # All entries should have assignment group
        for code, entry in registry.items():
            assert entry["smt_assignmentgroup"] is not None
            assert entry["source"] == "servicenow_only"
