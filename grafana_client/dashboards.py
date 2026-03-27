import json
import logging
import re
from pathlib import Path
from typing import Any

from .client import GrafanaClient

logger = logging.getLogger(__name__)

# Regex to find PromQL expressions inside Grafana dashboard JSON.
# Matches common keys: expr, query, legendFormat is excluded.
_PROMQL_PATTERN = re.compile(r'"expr"\s*:\s*"([^"]+)"')


def export_dashboards(
    client: GrafanaClient,
    output_dir: Path,
) -> None:
    """Export all Grafana dashboards as JSON and extract PromQL queries.

    For each dashboard found via the search API:
      1. Fetches the full dashboard JSON and saves it to *output_dir*.
      2. Extracts all PromQL expressions from panel targets.

    A consolidated ``grafana_queries.json`` reference file is written to
    *output_dir* mapping dashboard UIDs to their extracted queries.

    Does nothing if Grafana is unavailable.
    """
    if not client.is_available:
        logger.warning("Grafana client not available; skipping dashboard export")
        return

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    dashboards: list[dict] = client.search_dashboards()
    if not dashboards:
        logger.warning("No dashboards found in Grafana")
        return

    logger.info("Found %d dashboards to export", len(dashboards))

    all_queries: dict[str, Any] = {}

    for dash_meta in dashboards:
        uid: str = dash_meta.get("uid", "")
        title: str = dash_meta.get("title", "untitled")
        if not uid:
            logger.debug("Skipping dashboard with no UID: %s", title)
            continue

        logger.info("Exporting dashboard: %s (uid=%s)", title, uid)
        dash_data: dict = client.get_dashboard(uid)
        if not dash_data:
            logger.warning("Failed to fetch dashboard %s", uid)
            continue

        # Save full dashboard JSON
        safe_title = re.sub(r"[^\w\-.]", "_", title)
        dash_file = output_dir / f"{safe_title}_{uid}.json"
        dash_file.write_text(json.dumps(dash_data, indent=2), encoding="utf-8")
        logger.debug("Saved dashboard JSON to %s", dash_file)

        # Extract PromQL queries from panels
        queries = _extract_promql(dash_data)
        if queries:
            all_queries[uid] = {
                "title": title,
                "queries": queries,
            }
            logger.info(
                "Extracted %d PromQL queries from dashboard %s", len(queries), title
            )

    # Write consolidated query reference file
    queries_file = output_dir / "grafana_queries.json"
    queries_file.write_text(json.dumps(all_queries, indent=2), encoding="utf-8")
    logger.info("Wrote consolidated query reference to %s", queries_file)


def _extract_promql(dashboard_data: dict) -> list[str]:
    """Extract unique PromQL expressions from a dashboard JSON structure."""
    queries: list[str] = []
    seen: set[str] = set()

    # Walk through panels and their targets
    dash = dashboard_data.get("dashboard", dashboard_data)
    panels = dash.get("panels", [])

    for panel in panels:
        _extract_from_panel(panel, queries, seen)
        # Handle nested panels (rows)
        for nested in panel.get("panels", []):
            _extract_from_panel(nested, queries, seen)

    # Fallback: regex search the entire JSON string for any missed expressions
    raw = json.dumps(dashboard_data)
    for match in _PROMQL_PATTERN.finditer(raw):
        expr = match.group(1)
        if expr and expr not in seen:
            seen.add(expr)
            queries.append(expr)

    return queries


def _extract_from_panel(
    panel: dict,
    queries: list[str],
    seen: set[str],
) -> None:
    """Extract PromQL expressions from a single panel's targets."""
    for target in panel.get("targets", []):
        expr: str = target.get("expr", "")
        if expr and expr not in seen:
            seen.add(expr)
            queries.append(expr)
