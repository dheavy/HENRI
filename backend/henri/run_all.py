"""HENRI pipeline orchestrator — runs all data sources, analysis, and reporting.

Each step is wrapped in try/except so a single source failure does not
crash the entire pipeline.  Use ``run_pipeline()`` programmatically or
``python -m henri run_all`` from the command line.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def _data_dir() -> Path:
    return Path(os.getenv("DATA_DIR", "./data"))


# ── Step helpers ──────────────────────────────────────────────────────

def _step_cleanup(data_dir: Path, max_age_days: int = 30) -> None:
    """Delete raw CSV files older than *max_age_days*."""
    raw_dir = data_dir / "raw"
    if not raw_dir.is_dir():
        return
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for f in raw_dir.glob("*.csv"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            removed += 1
    if removed:
        logger.info("Cleanup: removed %d raw files older than %d days", removed, max_age_days)


def _step_snow_extract(data_dir: Path) -> None:
    """Pull ServiceNow incidents — incremental 7d or full 90d on first run."""
    from snow_extract.config import SnowConfig
    from snow_extract.exporter import SnowExporter

    config = SnowConfig()
    if not config.instance_url or not config.username:
        logger.warning("ServiceNow not configured; using existing raw/fixture data")
        return

    async def _run() -> None:
        async with SnowExporter(config) as exporter:
            await exporter.authenticate()
            last_run = exporter._read_last_run()
            if last_run:
                logger.info("ServiceNow: incremental pull since %s", last_run.date())
                await exporter.export_incidents_incremental(last_run)
            else:
                start = date.today() - timedelta(days=90)
                logger.info("ServiceNow: full 90-day pull from %s", start)
                await exporter.export_incidents(start, date.today())

    asyncio.run(_run())


def _step_snow_parse(data_dir: Path) -> tuple[pd.DataFrame, dict, dict]:
    """Parse ServiceNow CSVs → enriched parquet + registry.

    Returns (incidents_df, registry, subsite_map).
    """
    from snow_parse.parser import load_and_parse
    from snow_parse.prometheus_parser import enrich_prometheus
    from snow_parse.human_parser import enrich_human
    from snow_parse.location_normaliser import normalise_locations
    from snow_parse.delegation_registry import build_registry, build_subsite_map

    # Track which sources are live vs fallback
    source_status: dict[str, str] = {}  # "live" | "fallback" | "unavailable"

    df = load_and_parse(data_dir)
    if df.empty:
        logger.warning("No incident data found")
        return df, {}, {}
    logger.info("Loaded %d incidents", len(df))

    # Check if ServiceNow loaded from raw or fixtures
    raw_csvs = list((data_dir / "raw").glob("*.csv")) if (data_dir / "raw").is_dir() else []
    source_status["servicenow"] = "live" if raw_csvs else "fallback"

    df = enrich_prometheus(df)
    df = enrich_human(df)

    # Locations
    locations_csv = data_dir / "fixtures" / "locations.csv"
    if not locations_csv.exists():
        locations_csv = data_dir / "raw" / "locations.csv"
    locations_df = pd.DataFrame()
    if locations_csv.exists():
        processed_dir = data_dir / "processed"
        processed_dir.mkdir(parents=True, exist_ok=True)
        locations_df = normalise_locations(locations_csv, processed_dir / "locations_clean.csv")

    # Grafana registry: live API first, fall back to fixture
    grafana_registry, grafana_subsite = {}, {}
    try:
        from snow_extract.config import GrafanaConfig
        from grafana_client.client import GrafanaClient
        from grafana_client.registry_builder import build_registry_from_grafana, build_registry_from_fixture

        grafana_config = GrafanaConfig()
        if grafana_config.is_configured:
            logger.info("Grafana configured — pulling live registry")
            client = GrafanaClient(grafana_config.url, grafana_config.api_token, grafana_config.prometheus_ds_id)
            try:
                grafana_registry, grafana_subsite = build_registry_from_grafana(client)
            finally:
                client.close()

        if grafana_registry:
            source_status["grafana"] = "live"
        else:
            grafana_fixture = data_dir / "fixtures" / "grafana_registry.json"
            if grafana_fixture.exists():
                logger.info("Falling back to Grafana fixture")
                grafana_registry, grafana_subsite = build_registry_from_fixture(grafana_fixture)
            source_status["grafana"] = "fallback"
    except Exception as exc:
        logger.warning("Grafana registry failed: %s", type(exc).__name__)
        grafana_fixture = data_dir / "fixtures" / "grafana_registry.json"
        if grafana_fixture.exists():
            from grafana_client.registry_builder import build_registry_from_fixture
            grafana_registry, grafana_subsite = build_registry_from_fixture(grafana_fixture)

    snow_registry = build_registry(df, locations_df, grafana_available=bool(grafana_registry))
    snow_subsite = build_subsite_map(df)

    # Merge registries
    if grafana_registry:
        for code, g_entry in grafana_registry.items():
            s_entry = snow_registry.get(code, {})
            if s_entry.get("country") and not g_entry.get("country"):
                g_entry["country"] = s_entry["country"]
                g_entry["country_iso3"] = s_entry.get("country_iso3")
            if s_entry.get("latitude") and not g_entry.get("latitude"):
                g_entry["latitude"] = s_entry["latitude"]
                g_entry["longitude"] = s_entry.get("longitude")
        for code, s_entry in snow_registry.items():
            if code not in grafana_registry:
                grafana_registry[code] = s_entry
        registry = grafana_registry
        subsite_map = {**snow_subsite, **grafana_subsite}
    else:
        registry = snow_registry
        subsite_map = snow_subsite

    # Save reference data
    ref_dir = data_dir / "reference"
    ref_dir.mkdir(parents=True, exist_ok=True)
    with open(ref_dir / "delegations.json", "w") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)
    with open(ref_dir / "subsite_map.json", "w") as f:
        json.dump(subsite_map, f, indent=2, ensure_ascii=False)

    # NetBox enrichment (always fixture-based currently)
    source_status["netbox"] = "fallback"
    nb_sites = data_dir / "fixtures" / "netbox_sites.json"
    nb_circuits = data_dir / "fixtures" / "netbox_circuits.json"
    if nb_sites.exists() and nb_circuits.exists():
        from netbox_client.site_matcher import build_site_map
        from netbox_client.circuit_enrichment import load_circuits_from_fixture, enrich_circuits
        nb_map = build_site_map(nb_sites, set(subsite_map.keys()))
        circuits = enrich_circuits(load_circuits_from_fixture(nb_circuits), subsite_map)
        with open(ref_dir / "circuits.json", "w") as f:
            json.dump(circuits, f, indent=2, ensure_ascii=False)
        nb_out = {code: {"slug": s.get("slug"), "name": s.get("name")} for code, s in nb_map.items()}
        with open(ref_dir / "netbox_site_map.json", "w") as f:
            json.dump(nb_out, f, indent=2, ensure_ascii=False)

    # Map sub-sites and save parquet
    if "delegation_code" in df.columns:
        df["parent_code"] = df["delegation_code"].map(
            lambda c: subsite_map.get(str(c).upper(), c) if pd.notna(c) else None
        )

    processed_dir = data_dir / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    for col in ["opened_dt", "resolved_dt", "closed_dt", "updated_dt"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")

    df.to_parquet(processed_dir / "incidents_all.parquet", index=False)
    df[df["is_prometheus"]].to_parquet(processed_dir / "prometheus_alerts.parquet", index=False)

    # Save source status for the dashboard
    processed_dir.mkdir(parents=True, exist_ok=True)
    with open(processed_dir / "source_status.json", "w") as f:
        json.dump(source_status, f, indent=2)

    logger.info("Parse complete: %d delegation codes, %d sub-sites",
                len(registry), sum(1 for k, v in subsite_map.items() if k != v))
    return df, registry, subsite_map


def _step_grafana_bandwidth(data_dir: Path) -> None:
    """Pull live Grafana bandwidth data."""
    from snow_extract.config import GrafanaConfig
    from grafana_client.client import GrafanaClient
    from grafana_client.bandwidth import pull_bandwidth

    config = GrafanaConfig()
    if not config.is_configured:
        logger.info("Grafana not configured; skipping bandwidth pull")
        return

    client = GrafanaClient(config.url, config.api_token, config.prometheus_ds_id)
    try:
        pull_bandwidth(client, days=7,
                       output_path=data_dir / "processed" / "bandwidth_by_site.parquet")
    finally:
        client.close()


def _step_osint(data_dir: Path, registry: dict, fixtures: bool) -> list[dict]:
    """Run OSINT risk scoring."""
    from osint.risk_scorer import compute_risk_cards
    return compute_risk_cards(data_dir, registry, use_fixtures=fixtures)


# ── Main orchestrator ─────────────────────────────────────────────────

def run_pipeline(
    *,
    dry: bool = False,
    fixtures: bool = False,
    sources: set[str] | None = None,
    field_only: bool = False,
) -> dict[str, Any]:
    """Execute the full HENRI pipeline.

    Parameters
    ----------
    dry : bool
        Print the step plan without executing.
    fixtures : bool
        Use fixture files instead of live API calls.
    sources : set[str] | None
        If given, only run steps for these sources (e.g. {"snow", "grafana"}).
        None means run all.
    field_only : bool
        Generate field-region-only report (excludes HQ).

    Returns
    -------
    dict with keys: steps_run, steps_failed, report_paths, deltas.
    """
    from henri.delta import compute_deltas, save_risk_scores
    from snow_analyse.baseline_report import generate_report

    data_dir = _data_dir()
    today = date.today().isoformat()

    all_sources = {"snow", "grafana", "netbox", "osint"}
    active = sources if sources else all_sources

    steps = [
        ("cleanup", "Clean up old raw data (>30 days)", "snow" in active),
        ("snow_extract", "Pull ServiceNow incidents", "snow" in active and not fixtures),
        ("snow_parse", "Parse & enrich incidents", "snow" in active),
        ("grafana", "Pull Grafana bandwidth", "grafana" in active and not fixtures),
        ("osint", "OSINT risk scoring", "osint" in active),
        ("deltas", "Compute delta alerts", "osint" in active),
        ("reports", "Generate reports", True),
    ]

    if dry:
        logger.info("DRY RUN — would execute:")
        for name, desc, enabled in steps:
            status = "RUN" if enabled else "SKIP"
            logger.info("  [%s] %s: %s", status, name, desc)
        return {"steps_run": [], "steps_failed": [], "report_paths": [], "deltas": []}

    logger.info("Starting HENRI pipeline")
    start_time = time.time()
    steps_run: list[str] = []
    steps_failed: list[str] = []
    registry: dict = {}
    subsite_map: dict = {}
    risk_cards: list[dict] = []
    deltas: list[dict] = []
    report_paths: list[Path] = []

    # Step 1: Cleanup
    if "snow" in active:
        try:
            _step_cleanup(data_dir)
            steps_run.append("cleanup")
        except Exception as exc:
            logger.error("Cleanup failed: %s", exc)
            steps_failed.append("cleanup")

    # Step 2: ServiceNow extraction
    if "snow" in active and not fixtures:
        try:
            _step_snow_extract(data_dir)
            steps_run.append("snow_extract")
        except Exception as exc:
            logger.error("ServiceNow extraction failed: %s", exc)
            steps_failed.append("snow_extract")

    # Step 3: Parse & enrich
    if "snow" in active:
        try:
            _, registry, subsite_map = _step_snow_parse(data_dir)
            steps_run.append("snow_parse")
        except Exception as exc:
            logger.error("ServiceNow parsing failed: %s", exc)
            steps_failed.append("snow_parse")
            # Try to load existing registry
            reg_path = data_dir / "reference" / "delegations.json"
            if reg_path.exists():
                registry = json.loads(reg_path.read_text())

    # Step 4: Grafana bandwidth
    if "grafana" in active and not fixtures:
        try:
            _step_grafana_bandwidth(data_dir)
            steps_run.append("grafana")
        except Exception as exc:
            logger.error("Grafana bandwidth failed: %s", exc)
            steps_failed.append("grafana")

    # Step 5: OSINT
    if "osint" in active:
        try:
            risk_cards = _step_osint(data_dir, registry, fixtures)
            steps_run.append("osint")
        except Exception as exc:
            logger.error("OSINT scoring failed: %s", exc)
            steps_failed.append("osint")

    # Step 6: Delta alerting
    if "osint" in active and risk_cards:
        try:
            deltas = compute_deltas(risk_cards, data_dir)
            save_risk_scores(risk_cards, data_dir)
            steps_run.append("deltas")
        except Exception as exc:
            logger.error("Delta alerting failed: %s", exc)
            steps_failed.append("deltas")

    # Step 7: Generate reports
    try:
        for fo in ([True] if field_only else [False, True]):
            suffix = "field" if fo else "full"
            output_name = f"henri_{suffix}_{today}.html"
            path = generate_report(
                data_dir, field_only=fo, use_fixtures=fixtures,
                deltas=deltas, output_name=output_name,
            )
            report_paths.append(path)
            logger.info("Report generated: %s", path.name)
        steps_run.append("reports")
    except Exception as exc:
        logger.error("Report generation failed: %s", exc)
        steps_failed.append("reports")

    elapsed = time.time() - start_time
    logger.info(
        "Pipeline complete in %.1fs — %d steps OK, %d failed",
        elapsed, len(steps_run), len(steps_failed),
    )

    return {
        "steps_run": steps_run,
        "steps_failed": steps_failed,
        "report_paths": [str(p) for p in report_paths],
        "deltas": deltas,
    }


def regenerate_reports(field_only_only: bool = False) -> list[Path]:
    """Regenerate reports from existing processed data (no API calls)."""
    from henri.delta import compute_deltas
    from snow_analyse.baseline_report import generate_report

    data_dir = _data_dir()
    today = date.today().isoformat()

    # Load existing registry
    reg_path = data_dir / "reference" / "delegations.json"
    registry = json.loads(reg_path.read_text()) if reg_path.exists() else {}

    # Compute deltas from existing risk scores
    scores_path = data_dir / "processed" / "risk_scores.json"
    deltas: list[dict] = []
    if scores_path.exists():
        from osint.risk_scorer import compute_risk_cards
        risk_cards = compute_risk_cards(data_dir, registry, use_fixtures=True)
        deltas = compute_deltas(risk_cards, data_dir)

    paths: list[Path] = []
    variants = [True] if field_only_only else [False, True]
    for fo in variants:
        suffix = "field" if fo else "full"
        output_name = f"henri_{suffix}_{today}.html"
        path = generate_report(
            data_dir, field_only=fo, use_fixtures=True,
            deltas=deltas, output_name=output_name,
        )
        paths.append(path)
        logger.info("Report regenerated: %s", path.name)

    return paths
