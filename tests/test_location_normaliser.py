"""Tests for snow_parse.location_normaliser — country cleaning and ISO mapping."""

import pytest

from snow_parse.location_normaliser import _clean_country, _iso3_lookup


class TestCleanCountry:
    @pytest.mark.parametrize("raw, expected", [
        ("Mali | Mali", "Mali"),
        ("South Sudan | Soudan du Sud", "South Sudan"),
        ("CAMEROON", "Cameroon"),
        ("Cameroon | Cameroun", "Cameroon"),
        ("Armenia | Arménie", "Armenia"),
        ("Côte d'Ivoire | Côte d'Ivoire", "Côte D'Ivoire"),
        ("Burkina Faso | Burkina Faso", "Burkina Faso"),
        ("", None),
        (None, None),
        (42, None),
    ])
    def test_clean_country(self, raw, expected):
        assert _clean_country(raw) == expected


class TestIso3Lookup:
    @pytest.mark.parametrize("country, expected", [
        ("Mali", "MLI"),
        ("South Sudan", "SSD"),
        ("Cameroon", "CMR"),
        ("Armenia", "ARM"),
        ("Afghanistan", "AFG"),
        ("Switzerland", "CHE"),
        (None, None),
        ("", None),
    ])
    def test_known_countries(self, country, expected):
        assert _iso3_lookup(country) == expected

    def test_alias_drc(self):
        assert _iso3_lookup("Democratic Republic Of The Congo") == "COD"

    def test_alias_cote_divoire(self):
        assert _iso3_lookup("Côte D'Ivoire") == "CIV"

    def test_unknown_returns_none(self):
        assert _iso3_lookup("Pinlaung Township") is None
