"""Integration tests — run parsing and enrichment against deterministic test fixtures.

These tests use small, hand-crafted CSVs in tests/fixtures/ that never change.
They validate the same pipeline logic (parsing, enrichment, registry, locations)
as the real fixtures but without coupling to production data row counts.

The real fixtures in data/fixtures/ are living data updated via the web UI.
They should NOT be asserted against with exact counts.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

# ── Test fixtures (deterministic, committed, never updated by the app) ───────

TEST_FIXTURES = Path(__file__).resolve().parent / "fixtures"
TEST_INCIDENTS = TEST_FIXTURES / "incidents_test.csv"
TEST_LOCATIONS = TEST_FIXTURES / "locations_test.csv"

# ── Also keep a smoke test against real fixtures if present ──────────────────

REAL_FIXTURES = Path(__file__).resolve().parent.parent / "data" / "fixtures"
REAL_INCIDENTS = REAL_FIXTURES / "incidents_sample.csv"


@pytest.fixture(scope="module")
def test_data_dir(tmp_path_factory) -> Path:
    """Create a temp data_dir with tests/fixtures/ symlinked as fixtures/."""
    d = tmp_path_factory.mktemp("test_data")
    fixtures_dest = d / "fixtures"
    # Copy test CSVs into the expected structure
    import shutil
    shutil.copytree(TEST_FIXTURES, fixtures_dest)
    return d


@pytest.fixture(scope="module")
def parsed_df(test_data_dir: Path) -> pd.DataFrame:
    """Load and parse deterministic test incidents via the public API."""
    from snow_parse.parser import load_and_parse
    df = load_and_parse(test_data_dir)
    assert not df.empty
    return df


@pytest.fixture(scope="module")
def enriched_df(parsed_df: pd.DataFrame) -> pd.DataFrame:
    from snow_parse.prometheus_parser import enrich_prometheus
    from snow_parse.human_parser import enrich_human
    df = enrich_prometheus(parsed_df)
    df = enrich_human(df)
    return df


# ── Parsing ──────────────────────────────────────────────────────────────────

class TestParsing:
    def test_loads_known_row_count(self, parsed_df: pd.DataFrame):
        # 13 rows in CSV, 1 duplicate sys_id → 12 unique
        assert len(parsed_df) == 12

    def test_deduplicates_on_sys_id(self, parsed_df: pd.DataFrame):
        assert parsed_df["sys_id"].is_unique

    def test_has_required_columns(self, parsed_df: pd.DataFrame):
        required = {"sys_id", "number", "short_description", "is_prometheus", "opened_dt"}
        assert required.issubset(set(parsed_df.columns))

    def test_timestamps_parsed(self, parsed_df: pd.DataFrame):
        non_null = parsed_df["opened_dt"].notna().sum()
        assert non_null == 12  # All rows have timestamps

    def test_classifies_prometheus_vs_human(self, parsed_df: pd.DataFrame):
        prom = parsed_df[parsed_df["is_prometheus"]]
        human = parsed_df[~parsed_df["is_prometheus"]]
        # 9 Prometheus (⚠ prefix), 3 human
        assert len(prom) == 9
        assert len(human) == 3


# ── Prometheus enrichment ────────────────────────────────────────────────────

class TestPrometheusEnrichment:
    def test_delegation_codes_extracted(self, enriched_df: pd.DataFrame):
        prom = enriched_df[enriched_df["is_prometheus"]]
        codes = prom["delegation_code"].dropna().unique()
        assert set(codes) == {"ADE", "ABJ", "ADD", "DAM", "GVA", "COL"}

    def test_alert_names_extracted(self, enriched_df: pd.DataFrame):
        prom = enriched_df[enriched_df["is_prometheus"]]
        with_alert = prom["alert_name"].notna().sum()
        assert with_alert == len(prom)  # All Prometheus tickets get an alert name

    def test_known_alert_categories(self, enriched_df: pd.DataFrame):
        categories = set(enriched_df["alert_category"].dropna().unique())
        assert "site_down" in categories  # FortigateSiteDown
        assert "other" in categories       # ServerDown, HighCpuUsage, HighMemoryUsage

    def test_hostnames_extracted(self, enriched_df: pd.DataFrame):
        prom = enriched_df[enriched_df["is_prometheus"]]
        hostnames = prom["hostname"].dropna().unique()
        assert "fw-ade-01.ade.icrc.priv" in hostnames
        assert "fw-gva-01.gva.icrc.priv" in hostnames


# ── Human ticket enrichment ──────────────────────────────────────────────────

class TestHumanEnrichment:
    def test_human_tickets_have_keywords(self, enriched_df: pd.DataFrame):
        human = enriched_df[~enriched_df["is_prometheus"]]
        # "Network outage", "Internet connectivity", "VPN tunnel" should all match
        with_kw = human[human["matched_keywords"] != "[]"]
        assert len(with_kw) == 3

    def test_network_related_flag(self, enriched_df: pd.DataFrame):
        net = enriched_df[enriched_df["is_network_related"]]
        # All FortigateSiteDown + human network tickets
        assert len(net) > 0
        prom_net = net[net["is_prometheus"]]
        human_net = net[~net["is_prometheus"]]
        assert len(prom_net) > 0
        assert len(human_net) > 0


# ── Location normalisation ───────────────────────────────────────────────────

class TestLocationNormalisation:
    def test_normalise_locations(self, tmp_path: Path):
        from snow_parse.location_normaliser import normalise_locations
        output = tmp_path / "locations_clean.csv"
        df = normalise_locations(TEST_LOCATIONS, output)
        assert len(df) == 8
        assert "country_clean" in df.columns
        assert "country_iso3" in df.columns
        assert "missing_gps" in df.columns
        assert output.exists()

    def test_country_dedup(self, tmp_path: Path):
        from snow_parse.location_normaliser import normalise_locations
        output = tmp_path / "locations_clean.csv"
        df = normalise_locations(TEST_LOCATIONS, output)
        clean = df["country_clean"].dropna()
        # Pipe-separated duplicates like "Côte D'Ivoire | Cote d'Ivoire" should be resolved
        assert not clean.str.contains(r"\|").any()

    def test_iso3_resolved(self, tmp_path: Path):
        from snow_parse.location_normaliser import normalise_locations
        output = tmp_path / "locations_clean.csv"
        df = normalise_locations(TEST_LOCATIONS, output)
        iso3_map = dict(zip(df["city"], df["country_iso3"]))
        assert iso3_map.get("Aden") == "YEM"
        assert iso3_map.get("Addis Ababa") == "ETH"
        assert iso3_map.get("Geneva") == "CHE"

    def test_missing_gps_flagged(self, tmp_path: Path):
        from snow_parse.location_normaliser import normalise_locations
        output = tmp_path / "locations_clean.csv"
        df = normalise_locations(TEST_LOCATIONS, output)
        nairobi = df[df["city"] == "Nairobi"]
        assert len(nairobi) == 1
        assert bool(nairobi.iloc[0]["missing_gps"]) is True


# ── Delegation registry ──────────────────────────────────────────────────────

class TestDelegationRegistry:
    def test_registry_from_test_fixtures(self, enriched_df: pd.DataFrame):
        from snow_parse.delegation_registry import build_registry
        registry = build_registry(enriched_df, pd.DataFrame())
        # Test data has: ADE, ABJ, ADD, DAM, COL (field) + GVA/TI (HQ)
        assert len(registry) >= 5
        assert "ADE" in registry
        assert "ABJ" in registry
        assert "ADD" in registry

    def test_all_entries_have_assignment_group(self, enriched_df: pd.DataFrame):
        from snow_parse.delegation_registry import build_registry
        registry = build_registry(enriched_df, pd.DataFrame())
        for code, entry in registry.items():
            assert entry["smt_assignmentgroup"] is not None

    def test_hq_detection(self, enriched_df: pd.DataFrame):
        from snow_parse.delegation_registry import build_registry
        registry = build_registry(enriched_df, pd.DataFrame())
        # GVA ticket has .gva.icrc.priv hostname → HQ detection
        # TI NETWORK SUPPORT → HQ assignment group
        # Whether GVA appears depends on HQ filtering logic
        field_codes = {c for c, e in registry.items() if e.get("region") != "HQ"}
        assert "ADE" in field_codes
        assert "DAM" in field_codes


# ── Smoke test against real fixtures (if present) ───────────────────────────

class TestRealFixtureSmoke:
    """Lightweight smoke test against real production fixtures.

    Only asserts structural invariants (columns exist, non-empty, basic ratios).
    Never asserts exact row counts — those change with every ServiceNow export.
    """

    @pytest.mark.skipif(not REAL_INCIDENTS.exists(), reason="Real fixtures not available")
    def test_real_fixtures_parse(self):
        from snow_parse.parser import load_and_parse
        df = load_and_parse(REAL_FIXTURES.parent)
        assert not df.empty
        assert "sys_id" in df.columns
        assert "is_prometheus" in df.columns
        # Structural invariant: majority are Prometheus-generated
        prom_pct = df["is_prometheus"].sum() / len(df) * 100
        assert 60 < prom_pct < 90

    @pytest.mark.skipif(not REAL_INCIDENTS.exists(), reason="Real fixtures not available")
    def test_real_delegation_registry(self):
        from snow_parse.parser import load_and_parse
        from snow_parse.prometheus_parser import enrich_prometheus
        from snow_parse.human_parser import enrich_human
        from snow_parse.delegation_registry import build_registry
        df = load_and_parse(REAL_FIXTURES.parent)
        df = enrich_prometheus(df)
        df = enrich_human(df)
        registry = build_registry(df, pd.DataFrame())
        # Structural: at least 100 delegations, no empty assignment groups
        assert len(registry) >= 100
        for code, entry in registry.items():
            assert entry["smt_assignmentgroup"] is not None
