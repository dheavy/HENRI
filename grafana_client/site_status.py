import logging
import time

import pandas as pd

from .client import GrafanaClient

logger = logging.getLogger(__name__)

CURRENT_STATUS_QUERY = 'up{job="fortigate"}'


def pull_site_status(
    client: GrafanaClient,
    days: int = 30,
) -> pd.DataFrame:
    """Pull FortiGate site status: current up/down state and historical uptime %.

    Queries Prometheus via Grafana for the current value of up{job="fortigate"}
    and a historical average over the requested window.

    Returns an empty DataFrame if Grafana is unavailable.
    """
    if not client.is_available:
        logger.warning("Grafana client not available; returning empty site status DataFrame")
        return pd.DataFrame()

    logger.info("Pulling current FortiGate site status")
    df_current: pd.DataFrame = client.query_instant(CURRENT_STATUS_QUERY)

    if df_current.empty:
        logger.warning("No current status data returned from Grafana")
        return pd.DataFrame()

    # Rename the instant value to 'up' (1 = up, 0 = down)
    df_current = df_current.rename(columns={"value": "up"})

    # Query historical uptime percentage
    if not isinstance(days, int) or days < 1 or days > 365:
        logger.warning("Invalid days value %s, clamping to 1-365", days)
        days = max(1, min(365, int(days)))
    logger.info("Pulling historical uptime over %d days", days)
    uptime_query = f'avg_over_time(up{{job="fortigate"}}[{days}d]) * 100'
    df_uptime: pd.DataFrame = client.query_instant(uptime_query)

    if not df_uptime.empty:
        # Build a lookup from instance/location_site to uptime %
        uptime_key = "location_site" if "location_site" in df_uptime.columns else "instance"
        current_key = "location_site" if "location_site" in df_current.columns else "instance"

        if uptime_key in df_uptime.columns and current_key in df_current.columns:
            uptime_map = dict(zip(df_uptime[uptime_key], df_uptime["value"]))
            df_current["uptime_pct"] = df_current[current_key].map(uptime_map)
        else:
            logger.debug("Could not map uptime data; key columns missing")
            df_current["uptime_pct"] = None
    else:
        logger.debug("No historical uptime data returned")
        df_current["uptime_pct"] = None

    logger.info("Collected status for %d FortiGate instances", len(df_current))
    return df_current
