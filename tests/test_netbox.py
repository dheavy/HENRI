"""Tests for netbox_client — client, site_matcher, circuit_enrichment."""

from pathlib import Path

import pytest

from netbox_client.client import NetBoxClient
from netbox_client.site_matcher import match_sites, load_sites_from_fixture
from netbox_client.circuit_enrichment import (
    _extract_site_from_cid,
    _format_rate,
    _detect_rate_unit,
    enrich_circuits,
    load_circuits_from_fixture,
)

FIXTURES = Path(__file__).resolve().parent.parent / "data" / "fixtures"


# ── Client ────────────────────────────────────────────────────────────

class TestNetBoxClient:
    def test_not_available_without_config(self):
        c = NetBoxClient("", "")
        assert not c.is_available

    def test_available_with_config(self):
        c = NetBoxClient("https://nb.example.com", "token123")
        assert c.is_available

    def test_get_all_returns_empty_when_unconfigured(self):
        c = NetBoxClient("", "")
        assert c.get_all("/api/dcim/sites/") == []


# ── CID parsing ──────────────────────────────────────────────────────

class TestExtractSiteFromCid:
    @pytest.mark.parametrize("cid, expected", [
        ("ADDISP4", "ADD"),
        ("ALJISP1", "ALJ"),
        ("BUKISP5", "BUK"),
        ("RLUH4ISP03", "RLUH4"),
        ("RGOM01ISP4", "RGOM01"),
        ("WJUB7ISP3", "WJUB7"),
        ("RRAD11ISP1", "RRAD11"),
        ("WSAN14ISP3", "WSAN14"),
        ("RSADISP3", "RSAD"),
        ("OP2ISP1", "OP2"),
        ("MEKISP5", "MEK"),
    ])
    def test_standard_cids(self, cid, expected):
        assert _extract_site_from_cid(cid) == expected

    @pytest.mark.parametrize("cid", [
        "002", "1", "Castor ISP", "V0288948-3502",
        "APP-xxx", "APX-0104307349", "BIS-1", "ISP2",
    ])
    def test_freeform_cids_return_none(self, cid):
        assert _extract_site_from_cid(cid) is None


# ── Rate formatting ──────────────────────────────────────────────────

class TestFormatRate:
    @pytest.mark.parametrize("kbps, expected", [
        (10000, "10 Mbps"),
        (100000, "100 Mbps"),
        (1024000, "1.0 Gbps"),
        (204800, "205 Mbps"),
        (500, "500 kbps"),
        (None, "—"),
        (0, "—"),
    ])
    def test_format_rate(self, kbps, expected):
        assert _format_rate(kbps) == expected


class TestDetectRateUnit:
    def test_kbps_values(self):
        assert _detect_rate_unit([10000, 100000, 50000]) == "kbps"

    def test_bps_values(self):
        assert _detect_rate_unit([10_000_000, 100_000_000, 50_000_000]) == "bps"

    def test_empty(self):
        assert _detect_rate_unit([]) == "kbps"


# ── Site matching ────────────────────────────────────────────────────

class TestSiteMatcher:
    def test_case_insensitive_match(self):
        sites = [
            {"slug": "bag", "name": "BAG"},
            {"slug": "dam", "name": "DAM"},
            {"slug": "unknown_test", "name": "test"},
        ]
        grafana_codes = {"BAG", "DAM", "JUB"}
        matched = match_sites(sites, grafana_codes)
        assert "BAG" in matched
        assert "DAM" in matched
        assert len(matched) == 2

    def test_empty_inputs(self):
        assert match_sites([], set()) == {}
        assert match_sites([], {"JUB"}) == {}


# ── Circuit enrichment ───────────────────────────────────────────────

class TestEnrichCircuits:
    def test_basic_enrichment(self):
        circuits = [
            {
                "cid": "ADDISP4",
                "provider": {"name": "Ethio Telecom"},
                "type": {"value": "internet"},
                "commit_rate": 50000,
                "tenant": {"name": "AFRICA East"},
                "status": {"value": "active"},
                "description": "Primary link",
            },
        ]
        result = enrich_circuits(circuits, {"ADD": "ADD"})
        assert len(result) == 1
        assert result[0]["site_code"] == "ADD"
        assert result[0]["parent_code"] == "ADD"
        assert result[0]["provider"] == "Ethio Telecom"
        assert result[0]["commit_rate_kbps"] == 50000
        assert result[0]["commit_rate_fmt"] == "50 Mbps"

    def test_subsite_resolution(self):
        circuits = [{"cid": "WJUB7ISP3", "provider": {"name": "ISP"}, "type": None,
                     "commit_rate": None, "tenant": None, "status": None, "description": ""}]
        result = enrich_circuits(circuits, {"WJUB7": "JUB"})
        assert result[0]["site_code"] == "WJUB7"
        assert result[0]["parent_code"] == "JUB"

    def test_freeform_cid_no_site(self):
        circuits = [{"cid": "002", "provider": {"name": "ISP"}, "type": None,
                     "commit_rate": 10000000, "tenant": None, "status": None, "description": ""}]
        result = enrich_circuits(circuits)
        assert result[0]["site_code"] is None
        assert result[0]["parent_code"] is None


# ── Fixture loading ──────────────────────────────────────────────────

class TestFixtureLoading:
    @pytest.mark.skipif(not (FIXTURES / "netbox_sites.json").exists(), reason="Fixture not available")
    def test_load_sites(self):
        sites = load_sites_from_fixture(FIXTURES / "netbox_sites.json")
        assert len(sites) == 46

    @pytest.mark.skipif(not (FIXTURES / "netbox_circuits.json").exists(), reason="Fixture not available")
    def test_load_circuits(self):
        circuits = load_circuits_from_fixture(FIXTURES / "netbox_circuits.json")
        assert len(circuits) == 64

    @pytest.mark.skipif(not (FIXTURES / "netbox_circuits.json").exists(), reason="Fixture not available")
    def test_enrich_real_circuits(self):
        circuits = load_circuits_from_fixture(FIXTURES / "netbox_circuits.json")
        result = enrich_circuits(circuits)
        with_site = sum(1 for r in result if r["site_code"])
        with_rate = sum(1 for r in result if r["commit_rate_kbps"])
        assert with_site >= 50  # ~53 expected
        assert with_rate >= 20  # ~25 expected
