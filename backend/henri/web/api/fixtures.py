"""Fixture upload and listing endpoints.

Allows the web UI to upload updated ServiceNow CSVs and OSINT JSON
fixtures to the pod's PVC without requiring a rebuild or CLI access.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, UploadFile, File, HTTPException

router = APIRouter()
logger = logging.getLogger(__name__)

_REQUIRED_INCIDENT_COLS = {"sys_id", "short_description"}


def _data_dir() -> Path:
    return Path(os.getenv("DATA_DIR", "./data"))


def _fixtures_dir() -> Path:
    d = _data_dir() / "fixtures"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Fixture metadata ────────────────────────────────────────────────

_FIXTURE_DEFS: list[dict[str, Any]] = [
    # ServiceNow CSVs
    {
        "id": "incidents",
        "label": "ServiceNow Incidents",
        "category": "servicenow",
        "type": "csv",
        "multi": True,
        "pattern": "incidents_*.csv",
        "description": "Monthly incident exports from ServiceNow. All matching CSVs are merged by the pipeline.",
        "required_columns": sorted(_REQUIRED_INCIDENT_COLS),
        "refresh_info": None,
    },
    {
        "id": "locations",
        "label": "ServiceNow Locations",
        "category": "servicenow",
        "type": "csv",
        "multi": False,
        "pattern": "locations.csv",
        "description": "CMDB location table export. Maps incidents to GPS coordinates and country names.",
        "required_columns": ["location", "country"],
        "refresh_info": None,
    },
    # OSINT
    {
        "id": "acled",
        "label": "ACLED Conflict Events",
        "category": "osint",
        "type": "json",
        "multi": False,
        "pattern": "acled_sample.json",
        "description": "Armed Conflict Location & Event Data. Used for risk scoring and precursor analysis.",
        "required_columns": None,
        "refresh_info": {
            "prerequisites": "Account at acleddata.com",
            "env_vars": ["ACLED_EMAIL", "ACLED_PASSWORD"],
            "cli": "python -m henri export-fixture acled",
            "notes": "The pipeline also fetches live ACLED data automatically when credentials are configured. Token expires after 24h, refresh token after 14 days.",
        },
    },
    {
        "id": "ioda",
        "label": "IODA Internet Outages",
        "category": "osint",
        "type": "json",
        "multi": False,
        "pattern": "ioda_summary_7d.json",
        "description": "Internet Outage Detection & Analysis — BGP, active probing, and darknet signals.",
        "required_columns": None,
        "refresh_info": {
            "prerequisites": "None (public API, no authentication)",
            "env_vars": [],
            "cli": "python -m henri export-fixture ioda",
            "notes": "IODA alerts are also fetched live by the scheduler every 15 minutes.",
        },
    },
    {
        "id": "cloudflare",
        "label": "Cloudflare Radar Outages",
        "category": "osint",
        "type": "json",
        "multi": False,
        "pattern": "cf_outages_90d.json",
        "description": "Cloudflare Radar outage annotations — internet disruptions observed from the edge.",
        "required_columns": None,
        "refresh_info": {
            "prerequisites": "Cloudflare API token with Radar read access",
            "env_vars": ["CF_API_TOKEN"],
            "cli": "python -m henri export-fixture cloudflare",
            "notes": "Covers a 180-day rolling window. Also fetched live during pipeline runs.",
        },
    },
    # Internal sources
    {
        "id": "grafana_registry",
        "label": "Grafana Site Registry",
        "category": "internal",
        "type": "json",
        "multi": False,
        "pattern": "grafana_registry.json",
        "description": "FortiGate site labels from Prometheus via Grafana. Defines the 319-site delegation registry.",
        "required_columns": None,
        "refresh_info": {
            "prerequisites": "VPN access to grafana.ext.icrc.org",
            "env_vars": ["GRAFANA_API_TOKEN"],
            "cli": "python -m henri export-fixture grafana",
            "notes": "The pipeline pulls this live when Grafana is reachable. Fixture is the fallback.",
        },
    },
    {
        "id": "netbox_sites",
        "label": "NetBox Sites",
        "category": "internal",
        "type": "json",
        "multi": False,
        "pattern": "netbox_sites.json",
        "description": "NetBox DCIM site inventory — physical locations and metadata.",
        "required_columns": None,
        "refresh_info": {
            "prerequisites": "VPN access to netbox.test.icrc.org",
            "env_vars": ["NETBOX_URL", "NETBOX_TOKEN"],
            "cli": "python -m henri export-fixture netbox",
            "notes": "NetBox is ~15% populated. Coverage improves as the NetBox team adds sites.",
        },
    },
    {
        "id": "netbox_circuits",
        "label": "NetBox Circuits",
        "category": "internal",
        "type": "json",
        "multi": False,
        "pattern": "netbox_circuits.json",
        "description": "NetBox circuit inventory — ISP links with commit rates (kbps).",
        "required_columns": None,
        "refresh_info": {
            "prerequisites": "Same as NetBox Sites",
            "env_vars": ["NETBOX_URL", "NETBOX_TOKEN"],
            "cli": "python -m henri export-fixture netbox",
            "notes": "25 of 64 circuits have commit_rate populated.",
        },
    },
]


def _file_info(path: Path) -> dict[str, Any]:
    """Return metadata about a fixture file on disk."""
    if not path.exists():
        return {"exists": False}
    stat = path.stat()
    info: dict[str, Any] = {
        "exists": True,
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }
    # Add summary stats
    try:
        if path.suffix == ".csv":
            with open(path, newline="", encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                row_count = sum(1 for _ in reader)
            info["rows"] = row_count
            info["columns"] = header or []
        elif path.suffix == ".json":
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, dict):
                if "data" in data and isinstance(data["data"], list):
                    info["record_count"] = len(data["data"])
                elif "results" in data and isinstance(data["results"], list):
                    info["record_count"] = len(data["results"])
                else:
                    info["top_keys"] = sorted(data.keys())[:10]
            elif isinstance(data, list):
                info["record_count"] = len(data)
    except Exception:
        pass
    return info


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("")
async def list_fixtures() -> dict:
    """List all fixture slots with their current file info."""
    fixtures_dir = _fixtures_dir()
    result = []
    for defn in _FIXTURE_DEFS:
        entry = {**defn}
        pattern = defn["pattern"]
        if defn.get("multi"):
            import glob
            matched = sorted(glob.glob(str(fixtures_dir / pattern)))
            entry["files"] = [
                {"name": Path(p).name, **_file_info(Path(p))}
                for p in matched
            ]
        else:
            path = fixtures_dir / pattern
            entry["file"] = {"name": pattern, **_file_info(path)}
        result.append(entry)
    return {"fixtures": result}


@router.post("/upload/{fixture_id}")
async def upload_fixture(
    fixture_id: str,
    file: UploadFile = File(...),
) -> dict:
    """Upload a fixture file. Validates format before saving."""
    defn = next((d for d in _FIXTURE_DEFS if d["id"] == fixture_id), None)
    if not defn:
        raise HTTPException(400, f"Unknown fixture ID: {fixture_id}")

    fixtures_dir = _fixtures_dir()
    content = await file.read()

    if not file.filename:
        raise HTTPException(400, "Filename is required")

    # ── Validate ─────────────────────────────────────────────────
    if defn["type"] == "csv":
        try:
            text = content.decode("utf-8", errors="replace")
            reader = csv.reader(io.StringIO(text))
            header = next(reader, None)
            if not header:
                raise HTTPException(400, "CSV is empty — no header row found")
            header_lower = {c.strip().lower() for c in header}
            required = defn.get("required_columns") or []
            missing = [c for c in required if c.lower() not in header_lower]
            if missing:
                raise HTTPException(
                    400,
                    f"Missing required columns: {', '.join(missing)}. "
                    f"Found: {', '.join(sorted(header_lower))}",
                )
            row_count = sum(1 for _ in reader)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(400, f"Cannot parse CSV: {exc}")

        # For multi-file fixtures (incidents), keep the original filename.
        # For single-file fixtures, use the canonical pattern name.
        if defn.get("multi"):
            dest_name = file.filename
        else:
            dest_name = defn["pattern"]

    elif defn["type"] == "json":
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise HTTPException(400, f"Invalid JSON: {exc}")
        dest_name = defn["pattern"]
        row_count = None
    else:
        raise HTTPException(400, f"Unsupported fixture type: {defn['type']}")

    # ── Save ─────────────────────────────────────────────────────
    dest = fixtures_dir / dest_name
    dest.write_bytes(content)
    logger.info(
        "Fixture uploaded: %s → %s (%d bytes)",
        file.filename, dest_name, len(content),
    )

    info = _file_info(dest)
    return {
        "uploaded": True,
        "fixture_id": fixture_id,
        "filename": dest_name,
        "size_bytes": len(content),
        **({" rows": row_count} if row_count is not None else {}),
        "file_info": info,
    }


@router.delete("/{fixture_id}/{filename}")
async def delete_fixture(fixture_id: str, filename: str) -> dict:
    """Delete a specific fixture file (only for multi-file fixtures like incidents)."""
    defn = next((d for d in _FIXTURE_DEFS if d["id"] == fixture_id), None)
    if not defn:
        raise HTTPException(400, f"Unknown fixture ID: {fixture_id}")
    if not defn.get("multi"):
        raise HTTPException(400, "Cannot delete single-file fixtures — upload a replacement instead")
    if ".." in filename or "/" in filename:
        raise HTTPException(400, "Invalid filename")

    path = _fixtures_dir() / filename
    if not path.exists():
        raise HTTPException(404, f"File not found: {filename}")

    path.unlink()
    logger.info("Fixture deleted: %s/%s", fixture_id, filename)
    return {"deleted": True, "filename": filename}
