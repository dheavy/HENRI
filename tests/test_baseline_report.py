"""Tests for snow_analyse.baseline_report — report generation and data preparation."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from snow_analyse.baseline_report import (
    _safe_json,
    _build_summary,
    _build_top_delegations,
    _build_sitedown_heatmap,
    _build_category_chart_data,
    _build_keyword_breakdown,
)


class TestSafeJson:
    def test_basic_dict(self):
        result = _safe_json({"key": "value", "num": 42})
        parsed = json.loads(result)
        assert parsed["key"] == "value"
        assert parsed["num"] == 42

    def test_period_serialization(self):
        period = pd.Period("2026-01", freq="M")
        result = _safe_json({"month": period})
        parsed = json.loads(result)
        assert parsed["month"] == "2026-01"

    def test_numpy_int(self):
        import numpy as np
        result = _safe_json({"count": np.int64(42)})
        parsed = json.loads(result)
        assert parsed["count"] == 42

    def test_script_tag_escaped(self):
        # Must escape </script> to prevent XSS
        result = _safe_json({"text": "</script><script>alert(1)</script>"})
        assert "</script>" not in result
        assert r"<\/script>" in result
        # But still valid JSON when unescaped
        parsed = json.loads(result.replace(r"<\/", "</"))
        assert "alert(1)" in parsed["text"]


class TestBuildSummary:
    def test_basic_summary(self):
        df = pd.DataFrame({
            "is_prometheus": [True, True, False, False, False],
            "is_network_related": [True, False, True, False, False],
        })
        summary = _build_summary(df)
        assert summary["total_tickets"] == 5
        assert summary["automated_count"] == 2
        assert summary["automated_pct"] == 40.0
        assert summary["human_count"] == 3
        assert summary["network_count"] == 2

    def test_empty_df(self):
        df = pd.DataFrame({"is_prometheus": [], "is_network_related": []})
        summary = _build_summary(df)
        assert summary["total_tickets"] == 0
        assert summary["automated_pct"] == 0


class TestBuildTopDelegations:
    def test_top_delegations(self):
        df = pd.DataFrame({
            "is_prometheus": [True] * 10,
            "delegation_code": ["JUB"] * 5 + ["ABE"] * 3 + ["GVA"] * 2,
            "alert_name": ["FortigateSiteDown"] * 5 + ["WindowsServerDown"] * 3 + ["FemTargetDown"] * 2,
        })
        top = _build_top_delegations(df, top_n=2)
        assert len(top) == 2
        assert top[0]["delegation_code"] == "JUB"
        assert top[0]["total_count"] == 5
        assert top[0]["dominant_alert"] == "FortigateSiteDown"

    def test_empty_df(self):
        df = pd.DataFrame({
            "is_prometheus": [False],
            "delegation_code": [None],
            "alert_name": [None],
        })
        assert _build_top_delegations(df) == []


class TestBuildSitedownHeatmap:
    def test_heatmap_structure(self):
        df = pd.DataFrame({
            "alert_name": ["FortigateSiteDown"] * 4,
            "delegation_code": ["JUB", "JUB", "ABE", "ABE"],
            "opened_dt": pd.to_datetime([
                "2026-01-10", "2026-01-15", "2026-01-12", "2026-02-05"
            ], utc=True),
        })
        hm = _build_sitedown_heatmap(df)
        assert "JUB" in hm["delegations"]
        assert "ABE" in hm["delegations"]
        assert len(hm["months"]) >= 1
        assert hm["max_count"] >= 1
        # Matrix dimensions match
        assert len(hm["matrix"]) == len(hm["delegations"])
        assert all(len(row) == len(hm["months"]) for row in hm["matrix"])

    def test_empty_heatmap(self):
        df = pd.DataFrame({
            "alert_name": ["WindowsServerDown"],
            "delegation_code": ["JUB"],
            "opened_dt": pd.to_datetime(["2026-01-10"], utc=True),
        })
        hm = _build_sitedown_heatmap(df)
        assert hm["delegations"] == []


class TestBuildCategoryChart:
    def test_category_distribution(self):
        df = pd.DataFrame({
            "is_prometheus": [True] * 5,
            "alert_category": ["site_down", "site_down", "server", "server", "server"],
        })
        chart = _build_category_chart_data(df)
        assert "server" in chart["labels"]
        assert "site_down" in chart["labels"]
        assert sum(chart["data"]) == 5

    def test_empty(self):
        df = pd.DataFrame({"is_prometheus": [False], "alert_category": [None]})
        chart = _build_category_chart_data(df)
        assert chart["labels"] == []


class TestBuildKeywordBreakdown:
    def test_keyword_counts(self):
        df = pd.DataFrame({
            "is_prometheus": [False, False, False],
            "matched_keywords": ['["vpn", "slow"]', '["vpn"]', '["internet"]'],
            "region": ["AFRICA East", "AFRICA East", "AFRICA West"],
        })
        breakdown = _build_keyword_breakdown(df)
        assert len(breakdown) > 0
        # vpn should appear twice in AFRICA East
        vpn_east = [r for r in breakdown if r["keyword"] == "vpn" and r["region"] == "AFRICA East"]
        assert len(vpn_east) == 1
        assert vpn_east[0]["count"] == 2

    def test_invalid_json_handled(self):
        df = pd.DataFrame({
            "is_prometheus": [False],
            "matched_keywords": ["not valid json"],
            "region": ["Unknown"],
        })
        breakdown = _build_keyword_breakdown(df)
        assert breakdown == []
