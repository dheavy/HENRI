import logging
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .client import GrafanaClient

logger = logging.getLogger(__name__)


def pull_bandwidth(
    client: GrafanaClient,
    sites: list[str],
    days: int = 7,
    output_path: Path | None = None,
) -> pd.DataFrame:
    """Pull bandwidth metrics for the given sites over the specified period.

    For each site, queries inbound and outbound interface octet rates via
    Grafana/Prometheus datasource proxy, then aggregates per-site daily
    average, peak, and 95th-percentile bandwidth in bits/s.

    Returns an empty DataFrame if Grafana is unavailable.
    If *output_path* is provided the result is also saved as Parquet.
    """
    if not client.is_available:
        logger.warning("Grafana client not available; returning empty bandwidth DataFrame")
        return pd.DataFrame()

    if not sites:
        logger.warning("No sites provided for bandwidth pull")
        return pd.DataFrame()

    end_ts: float = time.time()
    start_ts: float = end_ts - (days * 86400)

    all_rows: list[dict[str, Any]] = []

    for site in sites:
        logger.info("Pulling bandwidth for site %s (%d days)", site, days)

        in_query = (
            f'rate(ifHCInOctets{{location_site="{site}"}}[1h]) * 8'
        )
        out_query = (
            f'rate(ifHCOutOctets{{location_site="{site}"}}[1h]) * 8'
        )

        df_in: pd.DataFrame = client.query_range(
            in_query, start=start_ts, end=end_ts, step="1h"
        )
        df_out: pd.DataFrame = client.query_range(
            out_query, start=start_ts, end=end_ts, step="1h"
        )

        for direction, df in [("in", df_in), ("out", df_out)]:
            if df.empty:
                logger.debug("No %s data for site %s", direction, site)
                continue

            df["datetime"] = pd.to_datetime(df["timestamp"], unit="s")
            df["date"] = df["datetime"].dt.date

            daily = df.groupby("date")["value"].agg(
                daily_avg="mean",
                daily_peak="max",
            )
            daily["daily_p95"] = df.groupby("date")["value"].quantile(0.95)

            for date_val, row in daily.iterrows():
                all_rows.append(
                    {
                        "site": site,
                        "direction": direction,
                        "date": date_val,
                        "avg_bps": row["daily_avg"],
                        "peak_bps": row["daily_peak"],
                        "p95_bps": row["daily_p95"],
                    }
                )

    if not all_rows:
        logger.warning("No bandwidth data collected for any site")
        return pd.DataFrame()

    result = pd.DataFrame(all_rows)
    logger.info(
        "Collected %d bandwidth records across %d sites", len(result), len(sites)
    )

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result.to_parquet(output_path, index=False)
        logger.info("Saved bandwidth data to %s", output_path)

    return result
