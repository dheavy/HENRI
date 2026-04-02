import logging
import re
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .client import GrafanaClient

logger = logging.getLogger(__name__)

_SAFE_LABEL_RE = re.compile(r"^[A-Za-z0-9_. -]+$")

# Hardcoded PromQL queries — no user input, no injection risk
_PROMQL_IN = "sum by (location_site) (rate(ifHCInOctets[1h])) * 8"
_PROMQL_OUT = "sum by (location_site) (rate(ifHCOutOctets[1h])) * 8"


def _parse_direction(df_raw: pd.DataFrame, direction: str) -> pd.DataFrame:
    """Convert a raw matrix DataFrame into per-site timeseries rows.

    Expects columns: ``location_site``, ``timestamp``, ``value``.
    Returns a DataFrame with columns: site, direction, timestamp, bps.
    """
    if df_raw.empty:
        return pd.DataFrame(columns=["site", "direction", "timestamp", "bps"])

    result = pd.DataFrame({
        "site": df_raw["location_site"],
        "direction": direction,
        "timestamp": df_raw["timestamp"],
        "bps": df_raw["value"],
    })
    return result


def _aggregate_daily(ts_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-site timeseries into daily avg / peak / p95.

    Input columns: site, direction, timestamp, bps.
    Output columns: site, direction, date, avg_bps, peak_bps, p95_bps.
    """
    if ts_df.empty:
        return pd.DataFrame(columns=["site", "direction", "date", "avg_bps", "peak_bps", "p95_bps"])

    ts_df = ts_df.copy()
    ts_df["datetime"] = pd.to_datetime(ts_df["timestamp"], unit="s")
    ts_df["date"] = ts_df["datetime"].dt.date

    agg = (
        ts_df.groupby(["site", "direction", "date"])["bps"]
        .agg(
            avg_bps="mean",
            peak_bps="max",
            p95_bps=lambda x: np.percentile(x, 95),
        )
        .reset_index()
    )
    return agg


def pull_bandwidth(
    client: GrafanaClient,
    sites: list[str] | None = None,
    days: int = 7,
    output_path: Path | None = None,
) -> pd.DataFrame:
    """Pull bandwidth metrics for all sites via two aggregated PromQL queries.

    Uses ``sum by (location_site)`` to fetch every site in a single query
    per direction (in/out), instead of one query per site. This reduces
    the number of API calls from 2*N to just 2.

    Parameters
    ----------
    client : GrafanaClient
        Configured Grafana client.
    sites : list[str] | None
        Optional list of site codes. If provided, the result is filtered
        to only these sites. The queries themselves always fetch all sites.
    days : int
        Number of days of history to pull (default 7).
    output_path : Path | None
        If given, save the result as Parquet.

    Returns
    -------
    pd.DataFrame
        Aggregated daily bandwidth data with columns:
        site, direction, date, avg_bps, peak_bps, p95_bps.
        Empty DataFrame if Grafana is unavailable.
    """
    if not client.is_available:
        logger.warning("Grafana client not available; returning empty bandwidth DataFrame")
        return pd.DataFrame()

    end_ts: float = time.time()
    start_ts: float = end_ts - (days * 86400)

    logger.info("Pulling aggregated bandwidth data (%d days, 2 queries)", days)

    df_in: pd.DataFrame = client.query_range(
        _PROMQL_IN, start=start_ts, end=end_ts, step="1h"
    )
    df_out: pd.DataFrame = client.query_range(
        _PROMQL_OUT, start=start_ts, end=end_ts, step="1h"
    )

    ts_in = _parse_direction(df_in, "in")
    ts_out = _parse_direction(df_out, "out")

    ts_all = pd.concat([ts_in, ts_out], ignore_index=True)

    if ts_all.empty:
        logger.warning("No bandwidth data returned from Grafana")
        return pd.DataFrame()

    # Filter to requested sites if provided
    if sites:
        ts_all = ts_all[ts_all["site"].isin(sites)]
        if ts_all.empty:
            logger.warning("No bandwidth data for requested sites")
            return pd.DataFrame()

    unique_sites = ts_all["site"].nunique()
    logger.info("Received bandwidth data for %d sites", unique_sites)

    result = _aggregate_daily(ts_all)

    logger.info(
        "Collected %d bandwidth records across %d sites",
        len(result),
        unique_sites,
    )

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result.to_parquet(output_path, index=False)
        logger.info("Saved bandwidth data to %s", output_path)

    return result
