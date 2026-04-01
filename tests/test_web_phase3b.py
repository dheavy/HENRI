"""Tests for Phase 3b — delegations, alerts, db, scheduler."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from henri.web.app import app
from henri.web.db import (
    init_db, get_conn, upsert_risk_scores, get_sparkline,
    insert_alert, get_active_alerts, get_alert_history,
    start_pipeline_run, finish_pipeline_run, get_last_pipeline_run,
    _get_db_path,
)

client = TestClient(app)


# ── Delegations API ──────────────────────────────────────────────────

class TestDelegationsAPI:
    def test_list_all(self):
        r = client.get("/api/v1/delegations")
        assert r.status_code == 200
        assert r.json()["total"] > 0
        d = r.json()["delegations"][0]
        assert "site_code" in d
        assert "region" in d
        assert "incident_count_30d" in d

    def test_filter_by_region(self):
        r = client.get("/api/v1/delegations?region=ASIA")
        delegations = r.json()["delegations"]
        assert all(d["region"] == "ASIA" for d in delegations)

    def test_search(self):
        r = client.get("/api/v1/delegations?search=kab")
        assert r.json()["total"] >= 1
        assert any("KAB" in d["site_code"] for d in r.json()["delegations"])

    def test_detail(self):
        r = client.get("/api/v1/delegations/BAG")
        assert r.status_code == 200
        assert r.json()["site_code"] == "BAG"

    def test_detail_not_found(self):
        r = client.get("/api/v1/delegations/ZZZZZ")
        assert r.status_code == 404

    def test_detail_invalid_code(self):
        r = client.get("/api/v1/delegations/../../etc")
        assert r.status_code == 404


# ── Alerts API ────────────────────────────────────────────────────────

class TestAlertsAPI:
    def test_active_alerts(self):
        r = client.get("/api/v1/alerts")
        assert r.status_code == 200
        assert "alerts" in r.json()

    def test_alert_history(self):
        r = client.get("/api/v1/alerts/history")
        assert r.status_code == 200

    def test_history_with_date_filter(self):
        r = client.get("/api/v1/alerts/history?from=2026-01-01&until=2026-04-01")
        assert r.status_code == 200


# ── Database ──────────────────────────────────────────────────────────

class TestDatabase:
    def test_init_creates_tables(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        import henri.web.db as db_mod
        db_mod._DB_PATH = None  # Reset cached path
        init_db()
        assert (tmp_path / "henri.db").exists()
        db_mod._DB_PATH = None

    def test_risk_score_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        import henri.web.db as db_mod
        db_mod._DB_PATH = None
        init_db()

        cards = [{"country_iso3": "SYR", "combined_risk": 75.0, "acled_events": 500,
                  "acled_fatalities": 100, "ioda_score": 10, "cf_outages": 2, "snow_sitedown": 15}]
        count = upsert_risk_scores("2026-04-01", cards)
        assert count == 1

        sparkline = get_sparkline("SY")
        assert sparkline == [75.0]
        db_mod._DB_PATH = None

    def test_alert_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        import henri.web.db as db_mod
        db_mod._DB_PATH = None
        init_db()

        aid = insert_alert("precursor", "warning", "Test alert", "SY", ["DAM", "ALE"])
        assert aid > 0

        active = get_active_alerts()
        assert len(active) == 1
        assert active[0]["message"] == "Test alert"
        assert active[0]["delegations"] == ["DAM", "ALE"]
        db_mod._DB_PATH = None

    def test_pipeline_run_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        import henri.web.db as db_mod
        db_mod._DB_PATH = None
        init_db()

        run_id = start_pipeline_run()
        assert run_id > 0
        finish_pipeline_run(run_id, "ok", sources={"snow": "ok"}, report_path="/tmp/report.html")

        last = get_last_pipeline_run()
        assert last is not None
        assert last["status"] == "ok"
        db_mod._DB_PATH = None


# ── Scheduler ─────────────────────────────────────────────────────────

class TestScheduler:
    def test_start_and_stop(self):
        from henri.web.scheduler import start_scheduler, stop_scheduler
        sched = start_scheduler()
        assert sched.running
        jobs = sched.get_jobs()
        assert len(jobs) == 2
        job_ids = {j.id for j in jobs}
        assert "full_pipeline" in job_ids
        assert "osint_quick" in job_ids
        stop_scheduler()
