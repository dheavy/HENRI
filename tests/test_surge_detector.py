"""Tests for snow_analyse.surge_detector — regional cluster detection."""

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from snow_analyse.surge_detector import detect_surges


def _make_site_down_events(
    delegations: list[str],
    base_time: datetime,
    offset_hours: list[float],
) -> pd.DataFrame:
    """Create FortigateSiteDown events for given delegations at offsets from base_time."""
    rows = []
    for deleg, offset in zip(delegations, offset_hours):
        rows.append({
            "alert_name": "FortigateSiteDown",
            "alert_category": "site_down",
            "delegation_code": deleg,
            "opened_dt": base_time + timedelta(hours=offset),
            "is_prometheus": True,
        })
    return pd.DataFrame(rows)


class TestDetectSurges:
    def test_detects_multi_delegation_cluster(self):
        registry = {
            "JUB": {"region": "AFRICA East"},
            "NAI": {"region": "AFRICA East"},
            "ADD": {"region": "AFRICA East"},
        }
        base = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
        df = _make_site_down_events(
            ["JUB", "NAI", "ADD"],
            base,
            [0, 2, 5],  # all within 48h window
        )
        surges = detect_surges(df, registry, window_hours=48)
        assert len(surges) >= 1
        surge = surges[0]
        assert surge["region"] == "AFRICA East"
        assert len(surge["affected_delegations"]) == 3
        assert "JUB" in surge["affected_delegations"]

    def test_no_surge_single_delegation(self):
        registry = {"JUB": {"region": "AFRICA East"}}
        base = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
        df = _make_site_down_events(["JUB"], base, [0])
        surges = detect_surges(df, registry)
        assert surges == []

    def test_no_surge_different_regions(self):
        registry = {
            "JUB": {"region": "AFRICA East"},
            "ABJ": {"region": "AFRICA West"},
        }
        base = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
        df = _make_site_down_events(["JUB", "ABJ"], base, [0, 1])
        surges = detect_surges(df, registry)
        # Each region only has 1 delegation, so no surge
        assert surges == []

    def test_events_outside_window_not_clustered(self):
        registry = {
            "JUB": {"region": "AFRICA East"},
            "NAI": {"region": "AFRICA East"},
        }
        base = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
        df = _make_site_down_events(
            ["JUB", "NAI"],
            base,
            [0, 100],  # 100 hours apart → outside 48h window
        )
        surges = detect_surges(df, registry, window_hours=48)
        assert surges == []

    def test_preceded_by_latency_flag(self):
        registry = {
            "JUB": {"region": "AFRICA East"},
            "NAI": {"region": "AFRICA East"},
        }
        base = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
        # Site down events
        site_down = _make_site_down_events(["JUB", "NAI"], base, [0, 1])
        # WAN latency event 12 hours before
        latency = pd.DataFrame([{
            "alert_name": "FortigateWanLatencyDeviation",
            "alert_category": "wan_degraded",
            "delegation_code": "JUB",
            "opened_dt": base - timedelta(hours=12),
            "is_prometheus": True,
        }])
        df = pd.concat([site_down, latency], ignore_index=True)
        surges = detect_surges(df, registry)
        assert len(surges) >= 1
        assert surges[0]["preceded_by_latency"] is True

    def test_empty_dataframe(self):
        surges = detect_surges(pd.DataFrame(), {})
        assert surges == []

    def test_score_increases_with_more_delegations(self):
        registry = {
            "JUB": {"region": "AFRICA East"},
            "NAI": {"region": "AFRICA East"},
            "ADD": {"region": "AFRICA East"},
            "DAR": {"region": "AFRICA East"},
        }
        base = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
        df_2 = _make_site_down_events(["JUB", "NAI"], base, [0, 1])
        df_4 = _make_site_down_events(["JUB", "NAI", "ADD", "DAR"], base, [0, 1, 2, 3])

        surges_2 = detect_surges(df_2, registry)
        surges_4 = detect_surges(df_4, registry)

        assert surges_4[0]["score"] > surges_2[0]["score"]
