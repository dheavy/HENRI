"""Tests for grafana_client.bandwidth — aggregated query approach."""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from grafana_client.bandwidth import (
    _PROMQL_IN,
    _PROMQL_OUT,
    _aggregate_daily,
    _parse_direction,
    pull_bandwidth,
)
from grafana_client.client import GrafanaClient


# ── Fixtures ──────────────────────────────────────────────────────────


def _make_matrix_response(sites: list[str], n_points: int = 168) -> dict:
    """Build a Prometheus matrix JSON response for testing.

    Returns a dict mimicking the Prometheus /api/v1/query_range response
    with ``n_points`` hourly samples per site.
    """
    base_ts = 1700000000.0
    result = []
    for site in sites:
        values = [
            [base_ts + i * 3600, str(float(1_000_000 + i * 1000 + hash(site) % 10000))]
            for i in range(n_points)
        ]
        result.append({
            "metric": {"location_site": site},
            "values": values,
        })
    return {"data": {"result": result}}


def _mock_client(sites: list[str] | None = None, available: bool = True) -> GrafanaClient:
    """Create a GrafanaClient mock that returns realistic matrix data."""
    client = MagicMock(spec=GrafanaClient)
    client.is_available = available

    if not available or not sites:
        client.query_range.return_value = pd.DataFrame()
        return client

    real_client = GrafanaClient("https://example.com", "tok", "1")
    in_resp = _make_matrix_response(sites)
    out_resp = _make_matrix_response(sites)

    def fake_query_range(promql, start, end, step="1h"):
        if "ifHCInOctets" in promql:
            return real_client._parse_matrix(in_resp)
        if "ifHCOutOctets" in promql:
            return real_client._parse_matrix(out_resp)
        return pd.DataFrame()

    client.query_range.side_effect = fake_query_range
    return client


# ── Test query construction ───────────────────────────────────────────


class TestQueryConstruction:
    """Verify the hardcoded PromQL queries are correct."""

    def test_in_query_uses_sum_by_location_site(self):
        assert "sum by (location_site)" in _PROMQL_IN
        assert "ifHCInOctets" in _PROMQL_IN
        assert "* 8" in _PROMQL_IN

    def test_out_query_uses_sum_by_location_site(self):
        assert "sum by (location_site)" in _PROMQL_OUT
        assert "ifHCOutOctets" in _PROMQL_OUT
        assert "* 8" in _PROMQL_OUT

    def test_queries_are_hardcoded(self):
        """Ensure no f-string interpolation or user input in queries."""
        assert "{" not in _PROMQL_IN.replace("[1h]", "")
        assert "{" not in _PROMQL_OUT.replace("[1h]", "")


# ── Test DataFrame parsing ────────────────────────────────────────────


class TestParseDirection:
    def test_parses_matrix_into_timeseries(self):
        client = GrafanaClient("https://example.com", "tok", "1")
        raw_resp = _make_matrix_response(["JUB", "ABE"], n_points=5)
        df_raw = client._parse_matrix(raw_resp)

        result = _parse_direction(df_raw, "in")

        assert set(result.columns) == {"site", "direction", "timestamp", "bps"}
        assert len(result) == 10  # 2 sites * 5 points
        assert (result["direction"] == "in").all()
        assert set(result["site"].unique()) == {"JUB", "ABE"}

    def test_empty_input_returns_empty(self):
        result = _parse_direction(pd.DataFrame(), "in")
        assert result.empty
        assert list(result.columns) == ["site", "direction", "timestamp", "bps"]


# ── Test daily aggregation ────────────────────────────────────────────


class TestAggregate:
    def _make_ts_df(self, n_hours: int = 48) -> pd.DataFrame:
        """Create a 2-day timeseries for a single site."""
        base_ts = 1700000000.0
        return pd.DataFrame({
            "site": ["TEST"] * n_hours,
            "direction": ["in"] * n_hours,
            "timestamp": [base_ts + i * 3600 for i in range(n_hours)],
            "bps": [float(1_000_000 + i * 10_000) for i in range(n_hours)],
        })

    def test_daily_aggregation_columns(self):
        ts = self._make_ts_df()
        agg = _aggregate_daily(ts)
        assert set(agg.columns) == {"site", "direction", "date", "avg_bps", "peak_bps", "p95_bps"}

    def test_daily_avg_is_reasonable(self):
        ts = self._make_ts_df()
        agg = _aggregate_daily(ts)
        for _, row in agg.iterrows():
            assert row["avg_bps"] > 0
            assert row["peak_bps"] >= row["avg_bps"]
            assert row["p95_bps"] >= row["avg_bps"]

    def test_p95_is_between_avg_and_peak(self):
        ts = self._make_ts_df(n_hours=120)
        agg = _aggregate_daily(ts)
        for _, row in agg.iterrows():
            assert row["avg_bps"] <= row["p95_bps"] <= row["peak_bps"]

    def test_empty_input(self):
        result = _aggregate_daily(pd.DataFrame(columns=["site", "direction", "timestamp", "bps"]))
        assert result.empty

    def test_multiple_sites(self):
        ts1 = self._make_ts_df(48)
        ts2 = ts1.copy()
        ts2["site"] = "OTHER"
        ts_all = pd.concat([ts1, ts2], ignore_index=True)
        agg = _aggregate_daily(ts_all)
        assert set(agg["site"].unique()) == {"TEST", "OTHER"}


# ── Test pull_bandwidth integration ───────────────────────────────────


class TestPullBandwidth:
    def test_returns_empty_when_unavailable(self):
        client = _mock_client(available=False)
        result = pull_bandwidth(client)
        assert result.empty

    def test_aggregated_query_two_calls(self):
        """Should make exactly 2 query_range calls (in + out)."""
        client = _mock_client(["JUB", "ABE"])
        result = pull_bandwidth(client)
        assert client.query_range.call_count == 2

    def test_result_has_correct_columns(self):
        client = _mock_client(["JUB"])
        result = pull_bandwidth(client)
        assert not result.empty
        assert set(result.columns) >= {"site", "direction", "date", "avg_bps", "peak_bps", "p95_bps"}

    def test_both_directions_present(self):
        client = _mock_client(["JUB"])
        result = pull_bandwidth(client)
        assert set(result["direction"].unique()) == {"in", "out"}

    def test_site_filter(self):
        """When sites list is provided, only those sites appear in output."""
        client = _mock_client(["JUB", "ABE", "GVA"])
        result = pull_bandwidth(client, sites=["JUB", "ABE"])
        assert set(result["site"].unique()) == {"JUB", "ABE"}

    def test_no_site_filter_returns_all(self):
        client = _mock_client(["JUB", "ABE", "GVA"])
        result = pull_bandwidth(client, sites=None)
        assert result["site"].nunique() == 3

    def test_saves_parquet(self, tmp_path: Path):
        client = _mock_client(["JUB"])
        out = tmp_path / "bw.parquet"
        result = pull_bandwidth(client, output_path=out)
        assert out.exists()
        loaded = pd.read_parquet(out)
        assert len(loaded) == len(result)

    def test_graceful_on_empty_response(self):
        """When Grafana returns no data, result is empty DataFrame."""
        client = MagicMock(spec=GrafanaClient)
        client.is_available = True
        client.query_range.return_value = pd.DataFrame()
        result = pull_bandwidth(client)
        assert result.empty


# ── Test no credential leakage ────────────────────────────────────────


class TestSecurityAudit:
    def test_promql_queries_are_static(self):
        """PromQL queries contain no dynamic interpolation."""
        assert "location_site=" not in _PROMQL_IN
        assert "location_site=" not in _PROMQL_OUT

    def test_parquet_contains_no_tokens(self, tmp_path: Path):
        client = _mock_client(["JUB"])
        out = tmp_path / "bw.parquet"
        pull_bandwidth(client, output_path=out)
        df = pd.read_parquet(out)
        # No column should contain anything that looks like a token
        for col in df.columns:
            series = df[col]
            # Only check columns that actually contain strings
            if series.dtype == object and len(series) > 0 and isinstance(series.iloc[0], str):
                assert not series.str.contains("Bearer|token|api_key", case=False, na=False).any()
