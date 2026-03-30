"""Tests for grafana_client.registry_builder — parsing and registry construction."""

import json
from pathlib import Path

import pytest

from grafana_client.registry_builder import (
    _parse_grafana_results,
    _sites_to_registry,
    build_registry_from_fixture,
)

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "data" / "fixtures" / "grafana_registry.json"


class TestParseGrafanaResults:
    def test_standard_response(self):
        data = {
            "data": {
                "result": [
                    {"metric": {"location_site": "JUB", "region": "AFRICA East",
                                "smt_assignmentgroup": "JUB ICT L2 SUPPORT"}, "value": [1, "1"]},
                    {"metric": {"location_site": "WJUB", "region": "AFRICA East",
                                "smt_assignmentgroup": "JUB ICT L2 SUPPORT"}, "value": [1, "1"]},
                ]
            }
        }
        sites = _parse_grafana_results(data)
        assert len(sites) == 2
        assert sites[0]["location_site"] == "JUB"
        assert sites[0]["region"] == "AFRICA East"

    def test_empty_response(self):
        assert _parse_grafana_results({"data": {"result": []}}) == []
        assert _parse_grafana_results({}) == []

    def test_missing_location_site_skipped(self):
        data = {"data": {"result": [
            {"metric": {"region": "HQ"}, "value": [1, "1"]},
        ]}}
        assert _parse_grafana_results(data) == []


class TestSitesToRegistry:
    def test_parent_and_subsite(self):
        sites = [
            {"location_site": "JUB", "region": "AFRICA East", "smt_assignmentgroup": "JUB ICT L2 SUPPORT"},
            {"location_site": "WJUB", "region": "AFRICA East", "smt_assignmentgroup": "JUB ICT L2 SUPPORT"},
            {"location_site": "RJUB", "region": "AFRICA East", "smt_assignmentgroup": "JUB ICT L2 SUPPORT"},
        ]
        registry, subsite_map = _sites_to_registry(sites)
        # One parent delegation
        assert "JUB" in registry
        assert registry["JUB"]["region"] == "AFRICA East"
        assert registry["JUB"]["source"] == "grafana_fortigate_labels"
        assert set(registry["JUB"]["sub_sites"]) == {"RJUB", "WJUB"}
        # Subsite mapping
        assert subsite_map["WJUB"] == "JUB"
        assert subsite_map["RJUB"] == "JUB"
        assert subsite_map["JUB"] == "JUB"

    def test_multiple_regions(self):
        sites = [
            {"location_site": "JUB", "region": "AFRICA East", "smt_assignmentgroup": "JUB ICT L2 SUPPORT"},
            {"location_site": "BAG", "region": "NAME", "smt_assignmentgroup": "BAG ICT L2 SUPPORT"},
        ]
        registry, _ = _sites_to_registry(sites)
        assert registry["JUB"]["region"] == "AFRICA East"
        assert registry["BAG"]["region"] == "NAME"

    def test_empty_input(self):
        registry, subsite_map = _sites_to_registry([])
        assert registry == {}
        assert subsite_map == {}


class TestBuildRegistryFromFixture:
    @pytest.mark.skipif(not FIXTURE_PATH.exists(), reason="Grafana fixture not available")
    def test_loads_real_fixture(self):
        registry, subsite_map = build_registry_from_fixture(FIXTURE_PATH)
        assert len(registry) >= 100  # 109 parent delegations expected
        assert len(subsite_map) >= 300  # 316+ site codes

        # All entries should have region
        with_region = sum(1 for v in registry.values() if v.get("region"))
        assert with_region == len(registry)

        # All entries should have source = grafana
        assert all(v["source"] == "grafana_fortigate_labels" for v in registry.values())

        # Check known sites
        assert "JUB" in registry or "GVA" in registry

    @pytest.mark.skipif(not FIXTURE_PATH.exists(), reason="Grafana fixture not available")
    def test_seven_regions(self):
        registry, _ = build_registry_from_fixture(FIXTURE_PATH)
        regions = {v["region"] for v in registry.values() if v.get("region")}
        expected = {"AFRICA East", "AFRICA West", "AMERICAS", "ASIA", "EURASIA", "HQ", "NAME"}
        assert regions == expected

    def test_nonexistent_fixture(self, tmp_path):
        fake = tmp_path / "nope.json"
        with pytest.raises(FileNotFoundError):
            build_registry_from_fixture(fake)
