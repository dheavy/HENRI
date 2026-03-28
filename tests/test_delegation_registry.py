"""Tests for snow_parse.delegation_registry — code extraction, fuzzy matching, registry building."""

import pandas as pd
import pytest

from snow_parse.delegation_registry import _extract_codes_from_groups, _iso3_for_country, build_registry


class TestExtractCodesFromGroups:
    def test_standard_pattern(self):
        df = pd.DataFrame({"assignment_group": [
            "JUB ICT L2 Support",
            "ABE ICT L2 Support",
            "GVA ICT L2 Support",
        ]})
        codes = _extract_codes_from_groups(df)
        assert "JUB" in codes
        assert "ABE" in codes
        assert "GVA" in codes
        assert codes["JUB"] == "JUB ICT L2 Support"

    def test_non_matching_groups_ignored(self):
        df = pd.DataFrame({"assignment_group": [
            "TI DIWP Collaboration Productivity",
            "TI External Support",
            "ABE ICT L2 Support",
        ]})
        codes = _extract_codes_from_groups(df)
        assert len(codes) == 1
        assert "ABE" in codes

    def test_case_insensitivity(self):
        df = pd.DataFrame({"assignment_group": ["jub ict l2 support"]})
        codes = _extract_codes_from_groups(df)
        assert "JUB" in codes

    def test_missing_column(self):
        df = pd.DataFrame({"other_col": ["data"]})
        codes = _extract_codes_from_groups(df)
        assert codes == {}

    def test_nan_values(self):
        df = pd.DataFrame({"assignment_group": [None, float("nan"), "ABE ICT L2 Support"]})
        codes = _extract_codes_from_groups(df)
        assert len(codes) == 1

    def test_deduplication(self):
        df = pd.DataFrame({"assignment_group": [
            "JUB ICT L2 Support",
            "JUB ICT L2 Support",
            "JUB ICT L2 Support",
        ]})
        codes = _extract_codes_from_groups(df)
        assert len(codes) == 1

    def test_two_to_five_char_codes(self):
        df = pd.DataFrame({"assignment_group": [
            "AB ICT L2 Support",     # 2 chars — valid
            "ABCDE ICT L2 Support",  # 5 chars — valid
        ]})
        codes = _extract_codes_from_groups(df)
        assert "AB" in codes
        assert "ABCDE" in codes


class TestIso3ForCountry:
    def test_known_country(self):
        assert _iso3_for_country("South Sudan") == "SSD"

    def test_none(self):
        assert _iso3_for_country(None) is None

    def test_empty(self):
        assert _iso3_for_country("") is None

    def test_fuzzy_match(self):
        # pycountry should fuzzy-match common names
        result = _iso3_for_country("Congo")
        assert result is not None  # Could be COG or COD


class TestBuildRegistry:
    def test_basic_registry(self):
        incidents_df = pd.DataFrame({"assignment_group": [
            "JUB ICT L2 Support",
            "ABE ICT L2 Support",
        ]})
        locations_df = pd.DataFrame({
            "city": ["Juba", "Abeche"],
            "country_clean": ["South Sudan", "Chad"],
            "latitude": [4.85, 13.83],
            "longitude": [31.61, 20.83],
        })
        registry = build_registry(incidents_df, locations_df)
        assert "JUB" in registry
        assert "ABE" in registry
        assert registry["JUB"]["smt_assignmentgroup"] == "JUB ICT L2 Support"
        assert registry["JUB"]["source"] == "servicenow_only"

    def test_empty_incidents(self):
        incidents_df = pd.DataFrame({"assignment_group": []})
        locations_df = pd.DataFrame()
        registry = build_registry(incidents_df, locations_df)
        assert registry == {}

    def test_no_assignment_group_column(self):
        incidents_df = pd.DataFrame({"other": ["data"]})
        locations_df = pd.DataFrame()
        registry = build_registry(incidents_df, locations_df)
        assert registry == {}

    def test_grafana_source_flag(self):
        incidents_df = pd.DataFrame({"assignment_group": ["JUB ICT L2 Support"]})
        locations_df = pd.DataFrame()
        registry = build_registry(incidents_df, locations_df, grafana_available=True)
        assert registry["JUB"]["source"] == "servicenow+grafana"
