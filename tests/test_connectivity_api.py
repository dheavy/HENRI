"""Tests for the connectivity (ETU) API endpoint."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from henri.web.app import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def tmp_data(tmp_path):
    """Set up minimal data directory for connectivity endpoint."""
    processed = tmp_path / "processed"
    processed.mkdir()
    reference = tmp_path / "reference"
    reference.mkdir()

    # Delegation registry
    registry = {
        "JUB": {
            "name": "Juba",
            "region": "AFRICA East",
            "country": "South Sudan",
            "country_iso3": "SSD",
            "smt_assignmentgroup": "JUB ICT L2 SUPPORT",
            "source": "grafana_fortigate_labels",
            "sub_sites": [],
        },
        "BNG": {
            "name": "Bangui",
            "region": "AFRICA West",
            "country": "Central African Republic",
            "country_iso3": "CAF",
            "smt_assignmentgroup": "BNG ICT L2 SUPPORT",
            "source": "grafana_fortigate_labels",
            "sub_sites": ["BNG2"],
        },
        "GVA": {
            "name": "Geneva",
            "region": "HQ",
            "country": "Switzerland",
            "country_iso3": "CHE",
            "smt_assignmentgroup": "GVA ICT L2 SUPPORT",
            "source": "grafana_fortigate_labels",
            "sub_sites": [],
        },
    }
    (reference / "delegations.json").write_text(json.dumps(registry))

    # Circuits
    circuits = [
        {
            "cid": "JUBISP1",
            "site_code": "JUB1",
            "parent_code": "JUB",
            "provider": "MTN",
            "circuit_type": "Internet-Fiber",
            "commit_rate_kbps": 10000,
            "status": "active",
        },
        {
            "cid": "JUBISP2",
            "site_code": "JUB1",
            "parent_code": "JUB",
            "provider": "Zain",
            "circuit_type": "Internet-VSAT",
            "commit_rate_kbps": 2000,
            "status": "active",
        },
    ]
    (reference / "circuits.json").write_text(json.dumps(circuits))

    # Bandwidth
    bw_data = pd.DataFrame([
        {"site": "JUB", "direction": "in", "avg_bps": 5_000_000, "peak_bps": 8_000_000, "p95_bps": 7_000_000},
        {"site": "JUB", "direction": "out", "avg_bps": 3_000_000, "peak_bps": 5_000_000, "p95_bps": 4_000_000},
        {"site": "BNG", "direction": "in", "avg_bps": 1_000_000, "peak_bps": 2_000_000, "p95_bps": 1_500_000},
    ])
    bw_data.to_parquet(processed / "bandwidth_by_site.parquet", index=False)

    # Incidents
    inc_data = pd.DataFrame([
        {"parent_code": "JUB", "alert_name": "FortigateSiteDown"},
        {"parent_code": "JUB", "alert_name": "FortigateSiteDown"},
        {"parent_code": "BNG", "alert_name": "FortigateSiteDown"},
        {"parent_code": "BNG", "alert_name": "OtherAlert"},
    ])
    inc_data.to_parquet(processed / "incidents_all.parquet", index=False)

    # Source status
    (processed / "source_status.json").write_text(json.dumps({}))

    return tmp_path


class TestConnectivityEndpoint:
    def test_returns_sites(self, client, tmp_data):
        with patch.dict(os.environ, {"DATA_DIR": str(tmp_data)}):
            resp = client.get("/api/v1/connectivity")
        assert resp.status_code == 200
        data = resp.json()
        assert "sites" in data
        assert "summary" in data
        assert "coverage" in data

    def test_excludes_hq(self, client, tmp_data):
        with patch.dict(os.environ, {"DATA_DIR": str(tmp_data)}):
            resp = client.get("/api/v1/connectivity")
        data = resp.json()
        site_codes = [s["site_code"] for s in data["sites"]]
        assert "GVA" not in site_codes

    def test_sites_sorted_by_score_ascending(self, client, tmp_data):
        with patch.dict(os.environ, {"DATA_DIR": str(tmp_data)}):
            resp = client.get("/api/v1/connectivity")
        sites = resp.json()["sites"]
        scores = [s["score"] for s in sites]
        assert scores == sorted(scores)

    def test_site_has_required_fields(self, client, tmp_data):
        with patch.dict(os.environ, {"DATA_DIR": str(tmp_data)}):
            resp = client.get("/api/v1/connectivity")
        sites = resp.json()["sites"]
        assert len(sites) > 0
        site = sites[0]
        required = [
            "site_code", "country", "region", "score", "grade",
            "etu_mbps", "num_users", "num_links", "data_completeness",
            "missing_data", "limiting_factor", "links",
        ]
        for field in required:
            assert field in site, f"Missing field: {field}"

    def test_link_has_required_fields(self, client, tmp_data):
        with patch.dict(os.environ, {"DATA_DIR": str(tmp_data)}):
            resp = client.get("/api/v1/connectivity")
        sites = resp.json()["sites"]
        site_with_links = next((s for s in sites if s["links"]), None)
        assert site_with_links is not None
        link = site_with_links["links"][0]
        required = [
            "cid", "effective_mbps", "rtt_ms", "rtt_source",
            "loss", "loss_source", "is_primary",
        ]
        for field in required:
            assert field in link, f"Missing link field: {field}"

    def test_diversity_bonus_for_multi_provider_site(self, client, tmp_data):
        with patch.dict(os.environ, {"DATA_DIR": str(tmp_data)}):
            resp = client.get("/api/v1/connectivity")
        sites = resp.json()["sites"]
        jub = next((s for s in sites if s["site_code"] == "JUB"), None)
        assert jub is not None
        assert jub["diversity_bonus"] == 1.05  # 2 providers: MTN + Zain

    def test_summary_counts(self, client, tmp_data):
        with patch.dict(os.environ, {"DATA_DIR": str(tmp_data)}):
            resp = client.get("/api/v1/connectivity")
        summary = resp.json()["summary"]
        assert summary["total_sites"] == 2  # JUB + BNG (HQ excluded)
        assert summary["scored_sites"] >= 1

    def test_coverage_counts(self, client, tmp_data):
        with patch.dict(os.environ, {"DATA_DIR": str(tmp_data)}):
            resp = client.get("/api/v1/connectivity")
        coverage = resp.json()["coverage"]
        assert coverage["total_sites"] == 2
        assert coverage["has_bandwidth"] >= 1
        assert coverage["has_circuits"] >= 1
        assert coverage["has_rtt"] == 0  # no blackbox exporter
        assert coverage["has_jitter"] == 0

    def test_empty_data_dir(self, client, tmp_path):
        (tmp_path / "processed").mkdir()
        (tmp_path / "reference").mkdir()
        with patch.dict(os.environ, {"DATA_DIR": str(tmp_path)}):
            resp = client.get("/api/v1/connectivity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["sites"] == []
        assert data["summary"]["scored_sites"] == 0
