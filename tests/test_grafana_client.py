"""Tests for grafana_client — client degradation, parsing, rate limiting."""

import time

import pandas as pd
import pytest

from grafana_client.client import GrafanaClient


class TestGrafanaClientAvailability:
    def test_not_available_without_config(self):
        client = GrafanaClient("", "", "1")
        assert client.is_available is False

    def test_not_available_without_token(self):
        client = GrafanaClient("https://grafana.example.com", "", "1")
        assert client.is_available is False

    def test_available_with_config(self):
        client = GrafanaClient("https://grafana.example.com", "token123", "1")
        assert client.is_available is True


class TestGracefulDegradation:
    """All query methods must return empty results when unconfigured."""

    def setup_method(self):
        self.client = GrafanaClient("", "", "1")

    def test_query_instant_returns_empty(self):
        result = self.client.query_instant("up")
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_query_range_returns_empty(self):
        result = self.client.query_range("up", 0, 1)
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_get_datasources_returns_empty(self):
        assert self.client.get_datasources() == []

    def test_search_dashboards_returns_empty(self):
        assert self.client.search_dashboards() == []

    def test_get_dashboard_returns_empty(self):
        assert self.client.get_dashboard("abc") == {}


class TestResponseParsing:
    def setup_method(self):
        self.client = GrafanaClient("https://example.com", "token", "1")

    def test_parse_vector(self):
        data = {
            "data": {
                "result": [
                    {"metric": {"location_site": "JUB"}, "value": [1700000000, "1"]},
                    {"metric": {"location_site": "ABE"}, "value": [1700000000, "0"]},
                ]
            }
        }
        df = self.client._parse_vector(data)
        assert len(df) == 2
        assert "location_site" in df.columns
        assert "value" in df.columns
        assert df[df["location_site"] == "JUB"]["value"].iloc[0] == 1.0

    def test_parse_matrix(self):
        data = {
            "data": {
                "result": [
                    {
                        "metric": {"location_site": "JUB"},
                        "values": [[1700000000, "100"], [1700003600, "200"]],
                    }
                ]
            }
        }
        df = self.client._parse_matrix(data)
        assert len(df) == 2
        assert df["value"].tolist() == [100.0, 200.0]

    def test_parse_empty_vector(self):
        df = self.client._parse_vector({"data": {"result": []}})
        assert df.empty

    def test_parse_empty_matrix(self):
        df = self.client._parse_matrix({"data": {"result": []}})
        assert df.empty

    def test_parse_missing_data(self):
        df = self.client._parse_vector({})
        assert df.empty


class TestBandwidthValidation:
    """Test PromQL label validation in bandwidth module."""

    def test_safe_label_regex(self):
        from grafana_client.bandwidth import _SAFE_LABEL_RE
        assert _SAFE_LABEL_RE.match("JUB")
        assert _SAFE_LABEL_RE.match("ABE_Starlink_05")
        assert _SAFE_LABEL_RE.match("GVA HQ")
        assert not _SAFE_LABEL_RE.match('JUB"})')
        assert not _SAFE_LABEL_RE.match("JUB\nmalicious")
        assert not _SAFE_LABEL_RE.match("")
