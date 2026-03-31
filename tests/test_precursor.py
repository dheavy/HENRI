"""Tests for precursor analysis and forward alerting."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from snow_analyse.precursor import (
    analyse_precursors,
    compute_precursor_stats,
    save_precursor_analysis,
    _check_acled_for_countries,
    _check_internal,
)
from henri.forward_alert import check_forward_alerts


class TestAcledPrecursor:
    def test_detects_spike(self):
        surge_start = datetime(2026, 2, 15, tzinfo=timezone.utc)
        country_map = {"SYR": "Syria"}
        # 30 baseline events over 30 days, 20 in 7-day window = 4.7x spike
        dates_baseline = [str((surge_start - timedelta(days=d)).date()) for d in range(8, 38)]
        dates_window = [str((surge_start - timedelta(days=d)).date()) for d in range(1, 8)] * 3
        acled_df = pd.DataFrame({
            "event_date": dates_baseline + dates_window,
            "country": ["Syria"] * (30 + 21),
            "fatalities": [1] * (30 + 21),
        })
        result = _check_acled_for_countries(surge_start, country_map, acled_df)
        assert result["detected"] is True
        assert result["ratio"] >= 2.0

    def test_no_spike(self):
        surge_start = datetime(2026, 2, 15, tzinfo=timezone.utc)
        country_map = {"SYR": "Syria"}
        # Flat rate: 1 per day
        dates = [str((surge_start - timedelta(days=d)).date()) for d in range(1, 38)]
        acled_df = pd.DataFrame({
            "event_date": dates,
            "country": ["Syria"] * 37,
            "fatalities": [0] * 37,
        })
        result = _check_acled_for_countries(surge_start, country_map, acled_df)
        assert result["detected"] is False

    def test_empty_acled(self):
        result = _check_acled_for_countries(
            datetime(2026, 2, 15, tzinfo=timezone.utc),
            {"SYR": "Syria"},
            pd.DataFrame(),
        )
        assert result["detected"] is False


class TestInternalPrecursor:
    def test_detects_latency_before_sitedown(self):
        surge_start = datetime(2026, 2, 15, 12, 0, tzinfo=timezone.utc)
        incidents = pd.DataFrame({
            "opened_dt": [surge_start - timedelta(hours=6)],
            "parent_code": ["JUB"],
            "alert_category": ["wan_degraded"],
        })
        result = _check_internal(surge_start, ["JUB"], incidents)
        assert result["detected"] is True
        assert result["latency_alerts"] == 1
        assert 5 < result["lead_time_hours"] < 7

    def test_no_latency(self):
        surge_start = datetime(2026, 2, 15, 12, 0, tzinfo=timezone.utc)
        incidents = pd.DataFrame({
            "opened_dt": [surge_start - timedelta(hours=6)],
            "parent_code": ["JUB"],
            "alert_category": ["server"],
        })
        result = _check_internal(surge_start, ["JUB"], incidents)
        assert result["detected"] is False


class TestAnalysePrecursors:
    def test_with_real_data(self):
        """Integration test against fixture data."""
        data_dir = Path("data")
        if not (data_dir / "processed" / "incidents_all.parquet").exists():
            pytest.skip("No processed data")
        registry = json.load(open(data_dir / "reference" / "delegations.json"))
        surges = [
            {"region": "AFRICA East", "start_time": datetime(2026, 2, 15, 10, 0, tzinfo=timezone.utc),
             "end_time": datetime(2026, 2, 15, 20, 0, tzinfo=timezone.utc),
             "affected_delegations": ["JUB", "NAI"], "score": 25.0, "preceded_by_latency": False},
        ]
        results = analyse_precursors(surges, registry, data_dir)
        assert len(results) == 1
        assert "acled_precursor" in results[0]
        assert "internal_precursor" in results[0]

    def test_empty_surges(self):
        assert analyse_precursors([], {}, Path("data")) == []


class TestPrecursorStats:
    def test_basic_stats(self):
        analysis = [
            {"any_external_precursor": True, "internal_precursor": {"detected": True},
             "earliest_lead_time_hours": 48, "acled_precursor": {"detected": True},
             "cf_precursor": {"detected": False}, "ioda_precursor": {"detected": False}},
            {"any_external_precursor": False, "internal_precursor": {"detected": False},
             "earliest_lead_time_hours": None, "acled_precursor": {"detected": False},
             "cf_precursor": {"detected": False}, "ioda_precursor": {"detected": False}},
        ]
        stats = compute_precursor_stats(analysis)
        assert stats["surges_with_precursors"] == 1
        assert stats["total_surges"] == 2
        assert stats["pct_with_precursors"] == 50.0
        assert stats["avg_lead_time_hours"] == 48.0

    def test_empty(self):
        stats = compute_precursor_stats([])
        assert stats["total_surges"] == 0


class TestSavePrecursorAnalysis:
    def test_saves_parquet(self, tmp_path):
        analysis = [{
            "surge_id": 0, "date": "2026-02-15", "region": "AFRICA East",
            "delegations": ["JUB"], "countries": ["South Sudan"], "surge_score": 25.0,
            "acled_precursor": {"detected": False, "event_count": 0, "fatalities": 0, "ratio": 0},
            "cf_precursor": {"detected": False, "event_count": 0},
            "internal_precursor": {"detected": False, "latency_alerts": 0},
            "any_external_precursor": False, "earliest_lead_time_hours": None,
        }]
        path = save_precursor_analysis(analysis, tmp_path)
        assert path.exists()
        df = pd.read_parquet(path)
        assert len(df) == 1


class TestForwardAlerts:
    def test_detects_spike(self, tmp_path):
        """Country with 3x normal activity triggers alert."""
        today = "2026-03-27"
        baseline_dates = [str(pd.Timestamp(today) - timedelta(days=d))[:10] for d in range(3, 33)]
        spike_dates = [today, str(pd.Timestamp(today) - timedelta(days=1))[:10]] * 15
        acled_df = pd.DataFrame({
            "event_date": baseline_dates + spike_dates,
            "country": ["Syria"] * (30 + 30),
            "fatalities": [0] * 60,
        })
        processed = tmp_path / "processed"
        processed.mkdir()
        acled_df.to_parquet(processed / "acled_events.parquet")
        registry = {"DAM": {"country": "Syria", "country_iso3": "SYR", "region": "NAME"}}
        warnings = check_forward_alerts(tmp_path, registry)
        assert len(warnings) >= 1
        assert warnings[0]["country"] == "Syria"
        assert "DAM" in warnings[0]["delegations_at_risk"]

    def test_no_data(self, tmp_path):
        assert check_forward_alerts(tmp_path, {}) == []

    def test_stable_country_no_alert(self, tmp_path):
        """Flat activity should not trigger."""
        dates = [str(pd.Timestamp("2026-03-27") - timedelta(days=d))[:10] for d in range(33)]
        acled_df = pd.DataFrame({
            "event_date": dates,
            "country": ["Iraq"] * 33,
            "fatalities": [0] * 33,
        })
        processed = tmp_path / "processed"
        processed.mkdir()
        acled_df.to_parquet(processed / "acled_events.parquet")
        registry = {"BAG": {"country": "Iraq", "country_iso3": "IRQ", "region": "NAME"}}
        assert check_forward_alerts(tmp_path, registry) == []
