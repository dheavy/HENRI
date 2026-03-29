import logging
from typing import Any

import pandas as pd

from .client import GrafanaClient

logger = logging.getLogger(__name__)

FORTIGATE_LABELS_QUERY = (
    'group by (location_site, region, smt_assignmentgroup) (up{job="fortigate"})'
)


def build_registry_from_grafana(client: GrafanaClient) -> dict[str, Any]:
    """Build a delegation registry from Grafana FortiGate labels.

    Queries Prometheus via Grafana for FortiGate site metadata and
    returns a structured registry keyed by location_site code.

    Returns an empty dict if Grafana is unavailable or the query fails.
    """
    if not client.is_available:
        logger.warning(
            "Grafana client not available; returning empty delegation registry"
        )
        return {}

    logger.info("Querying Grafana for FortiGate site labels")
    df: pd.DataFrame = client.query_instant(FORTIGATE_LABELS_QUERY)

    if df.empty:
        logger.warning("No results from FortiGate labels query")
        return {}

    registry: dict[str, Any] = {}
    for _, row in df.iterrows():
        site_code = row.get("location_site", "")
        if not site_code:
            continue
        registry[site_code] = {
            "code": site_code,
            "name": site_code,
            "region": row.get("region", ""),
            "smt_assignmentgroup": row.get("smt_assignmentgroup", ""),
            "source": "grafana_fortigate_labels",
        }

    logger.info("Built delegation registry with %d sites from Grafana", len(registry))
    return registry
