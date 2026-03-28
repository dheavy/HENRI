"""Tests for snow_parse.parser — CSV loading, dedup, timestamp parsing."""

from datetime import datetime, timezone

import pandas as pd
import pytest

from snow_parse.parser import _parse_ts, _classify


class TestParseTimestamp:
    def test_standard_format(self):
        result = _parse_ts("26.03.2026 19:21:07")
        assert result == datetime(2026, 3, 26, 19, 21, 7, tzinfo=timezone.utc)

    def test_leading_zeros(self):
        result = _parse_ts("01.01.2025 00:00:00")
        assert result == datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    def test_empty_string(self):
        assert _parse_ts("") is None

    def test_none_value(self):
        assert _parse_ts(None) is None

    def test_whitespace(self):
        assert _parse_ts("   ") is None

    def test_wrong_format(self):
        assert _parse_ts("2026-03-26 19:21:07") is None

    def test_non_string(self):
        assert _parse_ts(42) is None
        assert _parse_ts(3.14) is None


class TestClassify:
    def test_prometheus_ticket(self):
        assert _classify("? Prometheus - KADFGT - FortigateSiteDown") == "prometheus_automated"

    def test_human_ticket(self):
        assert _classify("Cannot connect to VPN") == "human_filed"

    def test_empty(self):
        assert _classify("") == "human_filed"

    def test_none(self):
        assert _classify(None) == "human_filed"

    def test_prometheus_substring(self):
        # Must contain "Prometheus" exactly
        assert _classify("Something about Prometheus alerts") == "prometheus_automated"
