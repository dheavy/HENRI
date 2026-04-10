"""Tests for the fixture upload / listing API."""

import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from henri.web.app import create_app


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """TestClient with DATA_DIR pointing at a temp directory."""
    import os
    data_dir = tmp_path_factory.mktemp("fixtures_test")
    (data_dir / "fixtures").mkdir()
    (data_dir / "reference").mkdir()
    os.environ["DATA_DIR"] = str(data_dir)
    app = create_app()
    yield TestClient(app)
    os.environ.pop("DATA_DIR", None)


@pytest.fixture
def fixtures_dir(client):
    import os
    return Path(os.environ["DATA_DIR"]) / "fixtures"


class TestListFixtures:
    def test_returns_fixture_slots(self, client):
        resp = client.get("/api/v1/fixtures")
        assert resp.status_code == 200
        data = resp.json()
        assert "fixtures" in data
        ids = [f["id"] for f in data["fixtures"]]
        assert "incidents" in ids
        assert "acled" in ids
        assert "grafana_registry" in ids

    def test_categories(self, client):
        data = client.get("/api/v1/fixtures").json()
        categories = {f["category"] for f in data["fixtures"]}
        assert categories == {"servicenow", "osint", "internal"}


class TestUploadCSV:
    def test_upload_incident_csv(self, client, fixtures_dir):
        csv_content = "sys_id,short_description,opened_at\nabc123,test ticket,01.01.2026\n"
        resp = client.post(
            "/api/v1/fixtures/upload/incidents",
            files={"file": ("incidents_test.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["uploaded"] is True
        assert body["filename"] == "incidents_test.csv"
        assert (fixtures_dir / "incidents_test.csv").exists()

    def test_rejects_csv_missing_columns(self, client):
        csv_content = "foo,bar\n1,2\n"
        resp = client.post(
            "/api/v1/fixtures/upload/incidents",
            files={"file": ("bad.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert resp.status_code == 400
        assert "Missing required columns" in resp.json()["detail"]

    def test_rejects_empty_csv(self, client):
        resp = client.post(
            "/api/v1/fixtures/upload/incidents",
            files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
        )
        assert resp.status_code == 400

    def test_single_file_csv_uses_canonical_name(self, client, fixtures_dir):
        csv_content = "location,country\nGeneva,Switzerland\n"
        resp = client.post(
            "/api/v1/fixtures/upload/locations",
            files={"file": ("my_locations.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert resp.status_code == 200
        # Single-file fixtures always use the canonical pattern name.
        assert resp.json()["filename"] == "locations.csv"
        assert (fixtures_dir / "locations.csv").exists()


class TestUploadJSON:
    def test_upload_acled_json(self, client, fixtures_dir):
        data = {"status": 200, "data": [{"event_id": "1", "country": "Nigeria"}]}
        resp = client.post(
            "/api/v1/fixtures/upload/acled",
            files={"file": ("acled.json", io.BytesIO(json.dumps(data).encode()), "application/json")},
        )
        assert resp.status_code == 200
        assert resp.json()["uploaded"] is True
        assert (fixtures_dir / "acled_sample.json").exists()

    def test_rejects_invalid_json(self, client):
        resp = client.post(
            "/api/v1/fixtures/upload/acled",
            files={"file": ("bad.json", io.BytesIO(b"not json{"), "application/json")},
        )
        assert resp.status_code == 400
        assert "Invalid JSON" in resp.json()["detail"]


class TestDeleteFixture:
    def test_delete_multi_file(self, client, fixtures_dir):
        # Create a file first
        csv_content = "sys_id,short_description\ndel1,to delete\n"
        client.post(
            "/api/v1/fixtures/upload/incidents",
            files={"file": ("incidents_delete_me.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert (fixtures_dir / "incidents_delete_me.csv").exists()

        resp = client.delete("/api/v1/fixtures/incidents/incidents_delete_me.csv")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True
        assert not (fixtures_dir / "incidents_delete_me.csv").exists()

    def test_cannot_delete_single_file_fixture(self, client):
        resp = client.delete("/api/v1/fixtures/acled/acled_sample.json")
        assert resp.status_code == 400

    def test_rejects_path_traversal(self, client):
        # Filename containing ".." — reaches the endpoint because it's a single
        # path segment, not a multi-level traversal that the HTTP framework resolves.
        resp = client.delete("/api/v1/fixtures/incidents/..passwd")
        assert resp.status_code == 400

    def test_unknown_fixture_id(self, client):
        resp = client.post(
            "/api/v1/fixtures/upload/nonexistent",
            files={"file": ("x.csv", io.BytesIO(b"a"), "text/csv")},
        )
        assert resp.status_code == 400


class TestListAfterUpload:
    def test_uploaded_files_appear_in_listing(self, client, fixtures_dir):
        csv_content = "sys_id,short_description\nlist1,listed\n"
        client.post(
            "/api/v1/fixtures/upload/incidents",
            files={"file": ("incidents_listed.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        resp = client.get("/api/v1/fixtures")
        incidents = next(f for f in resp.json()["fixtures"] if f["id"] == "incidents")
        names = [fi["name"] for fi in incidents["files"]]
        assert "incidents_listed.csv" in names
