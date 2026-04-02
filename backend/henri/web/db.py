"""SQLite database for risk score history, alerts, and pipeline runs.

Uses stdlib sqlite3 — no ORM, minimal abstraction.
Database file: ``data/henri.db``
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

logger = logging.getLogger(__name__)

_DB_PATH: Path | None = None


def _get_db_path() -> Path:
    global _DB_PATH
    if _DB_PATH is None:
        data_dir = Path(os.getenv("DATA_DIR", "./data"))
        data_dir.mkdir(parents=True, exist_ok=True)
        _DB_PATH = data_dir / "henri.db"
    return _DB_PATH


def init_db() -> None:
    """Create tables if they don't exist."""
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS risk_scores (
                date TEXT NOT NULL,
                country_iso2 TEXT NOT NULL,
                risk_score REAL,
                acled_events INTEGER DEFAULT 0,
                acled_fatalities INTEGER DEFAULT 0,
                ioda_score REAL DEFAULT 0,
                cf_outages INTEGER DEFAULT 0,
                snow_sitedown INTEGER DEFAULT 0,
                PRIMARY KEY (date, country_iso2)
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                type TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'info',
                country_iso2 TEXT,
                message TEXT,
                delegations TEXT,
                resolved_at TEXT
            );

            CREATE TABLE IF NOT EXISTS pipeline_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT DEFAULT 'running',
                sources TEXT,
                report_path TEXT
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                action TEXT NOT NULL,
                user TEXT,
                detail TEXT,
                correlation_id TEXT
            );
        """)
    logger.info("Database initialized at %s", _get_db_path().name)


@contextmanager
def get_conn() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for database connections."""
    conn = sqlite3.connect(str(_get_db_path()))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Risk scores ───────────────────────────────────────────────────────

def upsert_risk_scores(date_str: str, cards: list[dict]) -> int:
    """Insert or update risk scores for a given date.

    Returns the number of rows upserted.
    """
    import pycountry

    rows = []
    for card in cards:
        iso3 = card.get("country_iso3", "")
        try:
            c = pycountry.countries.get(alpha_3=iso3)
            iso2 = c.alpha_2 if c else iso3[:2]
        except (AttributeError, LookupError):
            iso2 = iso3[:2]

        rows.append((
            date_str,
            iso2.upper(),
            card.get("combined_risk", 0),
            card.get("acled_events", 0),
            card.get("acled_fatalities", 0),
            card.get("ioda_score", 0),
            card.get("cf_outages", 0),
            card.get("snow_sitedown", 0),
        ))

    with get_conn() as conn:
        conn.executemany(
            """INSERT OR REPLACE INTO risk_scores
               (date, country_iso2, risk_score, acled_events, acled_fatalities,
                ioda_score, cf_outages, snow_sitedown)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
    return len(rows)


def get_sparkline(country_iso2: str, days: int = 30) -> list[float]:
    """Get the last N days of risk scores for a country."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT risk_score FROM risk_scores
               WHERE country_iso2 = ?
               ORDER BY date DESC LIMIT ?""",
            (country_iso2.upper(), days),
        ).fetchall()
    return [row["risk_score"] for row in reversed(rows)]


# ── Alerts ────────────────────────────────────────────────────────────

def insert_alert(
    alert_type: str,
    severity: str,
    message: str,
    country_iso2: str | None = None,
    delegations: list[str] | None = None,
) -> int:
    """Insert an alert and return its ID."""
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        cursor = conn.execute(
            """INSERT INTO alerts (created_at, type, severity, country_iso2, message, delegations)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (now, alert_type, severity, country_iso2,
             message, json.dumps(delegations) if delegations else None),
        )
        return cursor.lastrowid or 0


def get_active_alerts() -> list[dict]:
    """Get alerts that haven't been resolved."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT id, created_at, type, severity, country_iso2, message, delegations
               FROM alerts WHERE resolved_at IS NULL
               ORDER BY created_at DESC LIMIT 100""",
        ).fetchall()
    return [
        {
            "id": r["id"],
            "created_at": r["created_at"],
            "type": r["type"],
            "severity": r["severity"],
            "country_iso2": r["country_iso2"],
            "message": r["message"],
            "delegations": json.loads(r["delegations"]) if r["delegations"] else [],
        }
        for r in rows
    ]


def get_alert_history(from_date: str | None = None, until_date: str | None = None) -> list[dict]:
    """Get historical alerts with optional date range filter."""
    query = "SELECT * FROM alerts WHERE 1=1"
    params: list[str] = []
    if from_date:
        query += " AND created_at >= ?"
        params.append(from_date)
    if until_date:
        query += " AND created_at <= ?"
        params.append(until_date)
    query += " ORDER BY created_at DESC LIMIT 500"

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


# ── Pipeline runs ─────────────────────────────────────────────────────

def start_pipeline_run() -> int:
    """Record a pipeline run start. Returns the run ID."""
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO pipeline_runs (started_at) VALUES (?)", (now,)
        )
        return cursor.lastrowid or 0


def finish_pipeline_run(
    run_id: int,
    status: str,
    sources: dict | None = None,
    report_path: str | None = None,
) -> None:
    """Record pipeline run completion."""
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            """UPDATE pipeline_runs
               SET finished_at = ?, status = ?, sources = ?, report_path = ?
               WHERE id = ?""",
            (now, status, json.dumps(sources) if sources else None, report_path, run_id),
        )


def get_last_pipeline_run() -> dict | None:
    """Get the most recent pipeline run."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM pipeline_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


# ── Audit log ─────────────────────────────────────────────────────────

def write_audit(action: str, user: str | None = None, detail: str | None = None,
                correlation_id: str | None = None) -> None:
    """Write an audit log entry to SQLite."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO audit_log (ts, action, user, detail, correlation_id) VALUES (?, ?, ?, ?, ?)",
                (now, action, user, detail, correlation_id),
            )
    except Exception:
        pass  # Don't let audit logging failures crash the app


def get_audit_log(limit: int = 100) -> list[dict]:
    """Get recent audit log entries."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
