"""Tests for the henri orchestrator — run_all, delta alerting, report generation."""

import json
import os
import time
from datetime import date
from pathlib import Path

import pytest

from henri.delta import compute_deltas, save_risk_scores, _identify_changed_signals


# ── Delta alerting ────────────────────────────────────────────────────

class TestComputeDeltas:
    def test_no_previous_scores(self, tmp_path):
        """First run — no previous file means no deltas."""
        current = [{"country": "Syria", "country_iso3": "SYR", "combined_risk": 75.0}]
        assert compute_deltas(current, tmp_path) == []

    def test_escalation(self, tmp_path):
        """Score jump > +15 triggers ESCALATION."""
        prev = {"_generated_at": "2026-03-30T00:00:00Z", "cards": [
            {"country": "Syria", "country_iso3": "SYR", "combined_risk": 50.0,
             "acled_events": 100, "acled_fatalities": 20, "ioda_score": 10,
             "cf_outages": 0, "snow_sitedown": 5},
        ]}
        (tmp_path / "processed").mkdir()
        (tmp_path / "processed" / "risk_scores.json").write_text(json.dumps(prev))

        current = [{"country": "Syria", "country_iso3": "SYR", "combined_risk": 72.0,
                     "acled_events": 500, "acled_fatalities": 100, "ioda_score": 10,
                     "cf_outages": 0, "snow_sitedown": 5}]
        deltas = compute_deltas(current, tmp_path)
        assert len(deltas) == 1
        assert deltas[0]["alert_type"] == "ESCALATION"
        assert deltas[0]["delta"] == 22.0

    def test_deescalation(self, tmp_path):
        """Score drop < -15 triggers DE-ESCALATION."""
        prev = {"cards": [
            {"country": "Yemen", "country_iso3": "YEM", "combined_risk": 80.0,
             "acled_events": 500, "acled_fatalities": 200, "ioda_score": 50,
             "cf_outages": 3, "snow_sitedown": 10},
        ]}
        (tmp_path / "processed").mkdir()
        (tmp_path / "processed" / "risk_scores.json").write_text(json.dumps(prev))

        current = [{"country": "Yemen", "country_iso3": "YEM", "combined_risk": 60.0,
                     "acled_events": 100, "acled_fatalities": 20, "ioda_score": 10,
                     "cf_outages": 0, "snow_sitedown": 2}]
        deltas = compute_deltas(current, tmp_path)
        assert len(deltas) == 1
        assert deltas[0]["alert_type"] == "DE-ESCALATION"
        assert deltas[0]["delta"] == -20.0

    def test_within_threshold(self, tmp_path):
        """Score change < 15 produces no alert."""
        prev = {"cards": [
            {"country": "Iraq", "country_iso3": "IRQ", "combined_risk": 60.0,
             "acled_events": 100, "acled_fatalities": 20, "ioda_score": 10,
             "cf_outages": 0, "snow_sitedown": 5},
        ]}
        (tmp_path / "processed").mkdir()
        (tmp_path / "processed" / "risk_scores.json").write_text(json.dumps(prev))

        current = [{"country": "Iraq", "country_iso3": "IRQ", "combined_risk": 65.0,
                     "acled_events": 110, "acled_fatalities": 22, "ioda_score": 12,
                     "cf_outages": 0, "snow_sitedown": 5}]
        assert compute_deltas(current, tmp_path) == []

    def test_corrupted_previous_file(self, tmp_path):
        """Corrupted JSON returns empty deltas, doesn't crash."""
        (tmp_path / "processed").mkdir()
        (tmp_path / "processed" / "risk_scores.json").write_text("not json{{{")
        current = [{"country": "Syria", "country_iso3": "SYR", "combined_risk": 75.0}]
        assert compute_deltas(current, tmp_path) == []


class TestSaveRiskScores:
    def test_saves_and_loads(self, tmp_path):
        scores = [{"country": "Syria", "country_iso3": "SYR", "combined_risk": 75.0}]
        path = save_risk_scores(scores, tmp_path)
        assert path.exists()
        data = json.loads(path.read_text())
        assert "_generated_at" in data
        assert len(data["cards"]) == 1
        assert data["cards"][0]["combined_risk"] == 75.0

    def test_atomic_write(self, tmp_path):
        """No partial files on crash — uses temp + rename."""
        scores = [{"country": "X", "country_iso3": "XXX", "combined_risk": 0}]
        save_risk_scores(scores, tmp_path)
        # No .tmp files should remain
        assert not list((tmp_path / "processed").glob("*.tmp"))


class TestIdentifyChangedSignals:
    def test_significant_change(self):
        prev = {"acled_events": 100, "ioda_score": 10, "cf_outages": 0, "snow_sitedown": 5, "acled_fatalities": 20}
        curr = {"acled_events": 500, "ioda_score": 10, "cf_outages": 0, "snow_sitedown": 5, "acled_fatalities": 20}
        changed = _identify_changed_signals(prev, curr)
        assert "acled_events" in changed
        assert "ioda_score" not in changed

    def test_no_change(self):
        prev = curr = {"acled_events": 100, "ioda_score": 10, "cf_outages": 0, "snow_sitedown": 5, "acled_fatalities": 20}
        assert _identify_changed_signals(prev, curr) == []


# ── Pipeline ──────────────────────────────────────────────────────────

class TestRunPipeline:
    def test_dry_mode(self):
        from henri.run_all import run_pipeline
        result = run_pipeline(dry=True)
        assert result["steps_run"] == []
        assert result["steps_failed"] == []

    def test_fixtures_mode(self):
        """Full pipeline with fixtures — should complete without errors."""
        from henri.run_all import run_pipeline
        result = run_pipeline(fixtures=True)
        assert "snow_parse" in result["steps_run"]
        assert "osint" in result["steps_run"]
        assert "reports" in result["steps_run"]
        assert len(result["report_paths"]) >= 1

    def test_source_filter(self):
        """--source osint should skip snow and grafana."""
        from henri.run_all import run_pipeline
        result = run_pipeline(fixtures=True, sources={"osint"})
        assert "snow_parse" not in result["steps_run"]
        assert "grafana" not in result["steps_run"]
        assert "osint" in result["steps_run"]

    def test_timestamped_filenames(self):
        """Reports should have timestamped names."""
        from henri.run_all import run_pipeline
        result = run_pipeline(fixtures=True)
        today = date.today().isoformat()
        assert any(today in p for p in result["report_paths"])


class TestReportGeneration:
    def test_backwards_compatible(self):
        """Existing generate_report call without deltas still works."""
        from snow_analyse.baseline_report import generate_report
        path = generate_report(Path("data"), field_only=False, use_fixtures=True)
        assert path.exists()
        assert "baseline_report.html" in path.name

    def test_with_deltas(self):
        """Report with delta alerts renders the section."""
        from snow_analyse.baseline_report import generate_report
        deltas = [{
            "country": "TestLand", "country_iso3": "TST",
            "previous_score": 40.0, "current_score": 60.0,
            "delta": 20.0, "alert_type": "ESCALATION",
            "signals_changed": ["acled_events"],
        }]
        path = generate_report(
            Path("data"), field_only=False, use_fixtures=True,
            deltas=deltas, output_name="test_deltas.html",
        )
        html = path.read_text()
        assert "Significant Changes" in html
        assert "ESCALATION" in html
        assert "TestLand" in html
        path.unlink()

    def test_custom_output_name(self):
        """output_name parameter controls the filename."""
        from snow_analyse.baseline_report import generate_report
        path = generate_report(
            Path("data"), use_fixtures=True, output_name="custom_test.html",
        )
        assert path.name == "custom_test.html"
        path.unlink()


# ── Cleanup ───────────────────────────────────────────────────────────

class TestCleanup:
    def test_removes_old_files(self, tmp_path):
        from henri.run_all import _step_cleanup
        raw = tmp_path / "raw"
        raw.mkdir()
        old = raw / "old.csv"
        old.write_text("data")
        # Set mtime to 60 days ago
        old_time = time.time() - 60 * 86400
        os.utime(old, (old_time, old_time))
        new = raw / "new.csv"
        new.write_text("data")
        _step_cleanup(tmp_path, max_age_days=30)
        assert not old.exists()
        assert new.exists()
