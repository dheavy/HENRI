"""Tests for snow_parse.human_parser — multilingual keyword matching."""

import json

import pandas as pd
import pytest

from snow_parse.human_parser import enrich_human, _match_keywords


class TestMatchKeywords:
    def test_english_keywords(self):
        assert "vpn" in _match_keywords("Cannot connect to VPN")
        assert "internet" in _match_keywords("No internet access")
        assert "firewall" in _match_keywords("Firewall blocking traffic")

    def test_french_keywords(self):
        hits = _match_keywords("Problème de connexion réseau")
        assert "problème de connexion" in hits
        assert "connexion" in hits
        assert "réseau" in hits

    def test_spanish_keywords(self):
        hits = _match_keywords("Problemas con internet en la oficina")
        assert "problemas con internet" in hits
        assert "internet" in hits

    def test_case_insensitive(self):
        assert "wifi" in _match_keywords("WiFi not working")
        assert "dns" in _match_keywords("DNS resolution fails")

    def test_forti_matches(self):
        assert "forti" in _match_keywords("FortiClient disconnected")
        assert "forti" in _match_keywords("Not connected to Forti Client")

    def test_no_match(self):
        assert _match_keywords("Printer paper jam") == []
        assert _match_keywords("Password reset request") == []

    def test_non_string_input(self):
        assert _match_keywords(None) == []
        assert _match_keywords(42) == []


class TestEnrichHuman:
    def test_human_ticket_flagged_network(self):
        df = pd.DataFrame({
            "short_description": ["VPN connection failed"],
            "is_prometheus": [False],
        })
        result = enrich_human(df)
        assert bool(result["is_network_related"].iloc[0]) is True
        keywords = json.loads(result["matched_keywords"].iloc[0])
        assert "vpn" in keywords

    def test_human_ticket_not_network(self):
        df = pd.DataFrame({
            "short_description": ["Printer not working"],
            "is_prometheus": [False],
        })
        result = enrich_human(df)
        assert bool(result["is_network_related"].iloc[0]) is False
        assert json.loads(result["matched_keywords"].iloc[0]) == []

    def test_prometheus_ticket_preserves_flag(self):
        df = pd.DataFrame({
            "short_description": ["? Prometheus - KADFGT - FortigateSiteDown"],
            "is_prometheus": [True],
            "is_network_related": [True],
        })
        result = enrich_human(df)
        # Should preserve the True from prometheus enrichment
        assert bool(result["is_network_related"].iloc[0]) is True

    def test_keywords_stored_as_json(self):
        df = pd.DataFrame({
            "short_description": ["slow internet connexion"],
            "is_prometheus": [False],
        })
        result = enrich_human(df)
        # Must be valid JSON, not Python repr
        parsed = json.loads(result["matched_keywords"].iloc[0])
        assert isinstance(parsed, list)
        assert "slow" in parsed
