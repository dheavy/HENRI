"""Core ServiceNow CSV parser — loads, deduplicates, and enriches incident data."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

_TS_FORMAT = "%d.%m.%Y %H:%M:%S"


def _read_csvs(directory: Path) -> pd.DataFrame:
    """Read all CSV files from *directory*, trying utf-8 then latin-1."""
    frames: list[pd.DataFrame] = []
    for csv_path in sorted(directory.glob("*.csv")):
        try:
            df = pd.read_csv(csv_path, encoding="utf-8")
        except UnicodeDecodeError:
            logger.info("Falling back to latin-1 for %s", csv_path.name)
            df = pd.read_csv(csv_path, encoding="latin-1")
        # Only include CSVs that look like incident exports
        if "sys_id" in df.columns and "short_description" in df.columns:
            frames.append(df)
        else:
            logger.debug("Skipping %s (missing sys_id/short_description columns)", csv_path.name)
    if not frames:
        logger.warning("No CSV files found in %s", directory)
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _parse_ts(value: object) -> datetime | None:
    """Parse a DD.MM.YYYY HH:MM:SS string to a UTC datetime, or return None."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.strptime(value.strip(), _TS_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _classify(desc: object) -> str:
    """Return 'prometheus_automated' or 'human_filed'."""
    if isinstance(desc, str) and "Prometheus" in desc:
        return "prometheus_automated"
    return "human_filed"


def load_and_parse(data_dir: str | Path) -> pd.DataFrame:
    """Load ServiceNow CSVs from *data_dir*/raw/ (or fixtures/ fallback),
    deduplicate on ``sys_id``, parse timestamps, and classify tickets.

    Returns a :class:`~pandas.DataFrame` with added columns:
    ``is_prometheus``, ``opened_dt``, ``resolved_dt``, ``closed_dt``, ``updated_dt``.
    """
    data_dir = Path(data_dir)
    raw_dir = data_dir / "raw"
    fixtures_dir = data_dir / "fixtures"

    df = pd.DataFrame()
    if raw_dir.is_dir():
        df = _read_csvs(raw_dir)
    if df.empty and fixtures_dir.is_dir():
        logger.info("No data in raw/, falling back to fixtures/")
        df = _read_csvs(fixtures_dir)
    if df.empty:
        logger.warning("No CSV data found in raw/ or fixtures/ under %s", data_dir)
        return df

    # Deduplicate on sys_id
    if "sys_id" in df.columns:
        before = len(df)
        df = df.drop_duplicates(subset="sys_id", keep="last").reset_index(drop=True)
        dupes = before - len(df)
        if dupes:
            logger.info("Dropped %d duplicate sys_id rows", dupes)
    else:
        logger.warning("Column 'sys_id' not found — skipping deduplication")

    # Classify
    classification = df.get("short_description", pd.Series(dtype=str)).apply(_classify)
    df["is_prometheus"] = classification == "prometheus_automated"

    # Parse timestamps
    for col, new_col in [
        ("opened_at", "opened_dt"),
        ("resolved_at", "resolved_dt"),
        ("closed_at", "closed_dt"),
        ("sys_updated_on", "updated_dt"),
    ]:
        if col in df.columns:
            df[new_col] = df[col].apply(_parse_ts)
        else:
            df[new_col] = None

    return df
