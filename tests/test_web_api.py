"""Tests for the HENRI web API endpoints."""

import pytest
from fastapi.testclient import TestClient

from henri.web.app import app

client = TestClient(app)


class TestHealth:
    def test_health_check(self):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestDashboard:
    def test_returns_structure(self):
        r = client.get("/api/v1/dashboard")
        assert r.status_code == 200
        data = r.json()
        assert "risk_summary" in data
        assert "pipeline_status" in data
        assert "alerts" in data
        assert "risk_cards" in data

    def test_risk_summary_tiers(self):
        r = client.get("/api/v1/dashboard")
        summary = r.json()["risk_summary"]
        assert all(k in summary for k in ("high", "medium", "low", "minimal"))
        assert sum(summary.values()) > 0


class TestCountries:
    def test_list_countries(self):
        r = client.get("/api/v1/countries")
        assert r.status_code == 200
        countries = r.json()["countries"]
        assert len(countries) > 0
        # Each has required fields
        c = countries[0]
        assert "iso2" in c
        assert "name" in c
        assert "risk_score" in c
        assert "risk_tier" in c

    def test_sort_by_name(self):
        r = client.get("/api/v1/countries?sort=name&order=asc")
        countries = r.json()["countries"]
        names = [c["name"] for c in countries]
        assert names == sorted(names)

    def test_filter_by_tier(self):
        r = client.get("/api/v1/countries?tier=high")
        countries = r.json()["countries"]
        assert all(c["risk_tier"] == "high" for c in countries)

    def test_country_detail(self):
        r = client.get("/api/v1/countries/IQ")
        assert r.status_code == 200
        data = r.json()
        assert data["country"]["name"] == "Iraq"
        assert "acled_timeline" in data
        assert "servicenow_incidents" in data

    def test_country_not_found(self):
        r = client.get("/api/v1/countries/XX")
        assert r.status_code == 404

    def test_invalid_sort_rejected(self):
        r = client.get("/api/v1/countries?sort=invalid_field")
        assert r.status_code == 422


class TestSurges:
    def test_list_surges(self):
        r = client.get("/api/v1/surges")
        assert r.status_code == 200
        data = r.json()
        assert "surges" in data
        assert "stats" in data

    def test_filter_by_region(self):
        r = client.get("/api/v1/surges?region=ASIA")
        surges = r.json()["surges"]
        if surges:
            assert all(s["region"] == "ASIA" for s in surges)

    def test_limit(self):
        r = client.get("/api/v1/surges?limit=5")
        surges = r.json()["surges"]
        assert len(surges) <= 5

    def test_surge_detail(self):
        r = client.get("/api/v1/surges/0")
        assert r.status_code == 200


class TestSPA:
    def test_root_without_frontend(self):
        """Without built frontend, root returns API info."""
        r = client.get("/")
        assert r.status_code == 200

    def test_api_docs(self):
        r = client.get("/api/docs")
        assert r.status_code == 200
