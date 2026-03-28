"""Tests for snow_analyse.timeseries — aggregation and anomaly detection."""

from datetime import datetime, timezone

import pandas as pd
import pytest

from snow_analyse.timeseries import aggregate_incidents, detect_anomalies


def _make_incidents(n: int = 100, delegation: str = "JUB", region: str = "AFRICA East") -> pd.DataFrame:
    """Create a synthetic incident DataFrame for testing."""
    dates = pd.date_range("2025-11-01", periods=n, freq="6h", tz="UTC")
    return pd.DataFrame({
        "opened_dt": dates,
        "is_prometheus": [True] * n,
        "delegation_code": [delegation] * n,
        "alert_category": ["site_down"] * (n // 2) + ["server"] * (n - n // 2),
        "region": [region] * n,
    })


class TestAggregateIncidents:
    def test_region_monthly(self):
        df = _make_incidents(100)
        agg = aggregate_incidents(df)
        assert "region_monthly" in agg
        rm = agg["region_monthly"]
        assert not rm.empty
        assert "AFRICA East" in rm["region"].values

    def test_delegation_monthly(self):
        df = _make_incidents(100)
        agg = aggregate_incidents(df)
        assert "delegation_monthly" in agg
        dm = agg["delegation_monthly"]
        assert "JUB" in dm["delegation_code"].values

    def test_category_monthly(self):
        df = _make_incidents(100)
        agg = aggregate_incidents(df)
        assert "category_monthly" in agg
        cm = agg["category_monthly"]
        assert "site_down" in cm["alert_category"].values

    def test_empty_dataframe(self):
        df = pd.DataFrame({
            "opened_dt": pd.Series(dtype="datetime64[ns, UTC]"),
            "is_prometheus": pd.Series(dtype=bool),
            "delegation_code": pd.Series(dtype=str),
            "alert_category": pd.Series(dtype=str),
            "region": pd.Series(dtype=str),
        })
        agg = aggregate_incidents(df)
        assert agg.get("delegation_monthly") is not None

    def test_multiple_regions(self):
        df1 = _make_incidents(50, delegation="JUB", region="AFRICA East")
        df2 = _make_incidents(50, delegation="ABJ", region="AFRICA West")
        df = pd.concat([df1, df2], ignore_index=True)
        agg = aggregate_incidents(df)
        rm = agg["region_monthly"]
        assert set(rm["region"].unique()) == {"AFRICA East", "AFRICA West"}


class TestDetectAnomalies:
    def test_detects_spike(self):
        # 6 steady months (~30/month) then one massive month
        all_dates = []
        for m in range(1, 7):
            dates = pd.date_range(f"2025-{m:02d}-01", periods=30, freq="D", tz="UTC")
            all_dates.extend(dates)
        # Month 7: 300 incidents (10x spike)
        spike = pd.date_range("2025-07-01", periods=30, freq="D", tz="UTC")
        for d in spike:
            all_dates.extend([d] * 10)

        df = pd.DataFrame({
            "opened_dt": all_dates,
            "delegation_code": ["JUB"] * len(all_dates),
        })
        anomalies = detect_anomalies(df, "delegation_code")
        # July should be flagged (300 vs ~30 baseline for other months)
        assert not anomalies.empty
        anomaly_months = anomalies["month"].astype(str).tolist()
        assert any("2025-07" in m for m in anomaly_months)

    def test_no_anomalies_on_steady_data(self):
        dates = pd.date_range("2025-11-01", periods=120, freq="D", tz="UTC")
        df = pd.DataFrame({
            "opened_dt": dates,
            "delegation_code": ["JUB"] * 120,
        })
        anomalies = detect_anomalies(df, "delegation_code")
        # With exactly 1 per day, std ≈ 0, no anomalies (or minimal)
        # Each month has ~30 incidents, all equal, so mean=30, std=~small
        assert len(anomalies) == 0 or anomalies["is_anomaly"].sum() == 0
