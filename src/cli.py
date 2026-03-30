"""HENRI — CLI entry point."""

from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

import click

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("henri")


def _data_dir() -> Path:
    import os
    return Path(os.getenv("DATA_DIR", "./data"))


# ── ServiceNow extraction ────────────────────────────────────────────

@click.group()
def cli() -> None:
    """HENRI — Humanitarian Early-warning Network Resilience Intelligence."""


@cli.command()
@click.option("--start", type=click.DateTime(["%Y-%m-%d"]), required=True)
@click.option("--end", type=click.DateTime(["%Y-%m-%d"]), default=str(date.today()))
def snow_extract(start: datetime, end: datetime) -> None:
    """Extract incidents from ServiceNow (batched by month)."""
    import asyncio
    from snow_extract.config import SnowConfig
    from snow_extract.exporter import SnowExporter

    config = SnowConfig()
    if not config.username or not config.password:
        click.echo("Error: SNOW_USERNAME and SNOW_PASSWORD must be set.", err=True)
        sys.exit(1)

    exporter = SnowExporter(config)
    asyncio.run(exporter.export_incidents(start.date(), end.date()))


@cli.command()
def snow_extract_incremental() -> None:
    """Incremental extraction from ServiceNow (since last run)."""
    import asyncio
    from snow_extract.config import SnowConfig
    from snow_extract.exporter import SnowExporter

    config = SnowConfig()
    exporter = SnowExporter(config)
    last_run_file = config.data_dir / ".last_run"
    if not last_run_file.exists():
        click.echo("No .last_run file found. Run a full extraction first.", err=True)
        sys.exit(1)
    ts = datetime.fromisoformat(last_run_file.read_text().strip())
    asyncio.run(exporter.export_incidents_incremental(ts))


@cli.command()
def snow_extract_locations() -> None:
    """Extract cmn_location table from ServiceNow."""
    import asyncio
    from snow_extract.config import SnowConfig
    from snow_extract.exporter import SnowExporter

    config = SnowConfig()
    exporter = SnowExporter(config)
    asyncio.run(exporter.export_locations())


# ── ServiceNow parsing ───────────────────────────────────────────────

@cli.command()
def snow_parse() -> None:
    """Parse raw CSVs into enriched parquet files."""
    import pandas as pd
    from snow_parse.parser import load_and_parse
    from snow_parse.prometheus_parser import enrich_prometheus
    from snow_parse.human_parser import enrich_human
    from snow_parse.location_normaliser import normalise_locations
    from snow_parse.delegation_registry import build_registry, build_subsite_map

    data_dir = _data_dir()

    # 1. Parse incidents
    click.echo("Loading and parsing incident CSVs...")
    df = load_and_parse(data_dir)
    if df.empty:
        click.echo("No incident data found.", err=True)
        sys.exit(1)
    click.echo(f"  Loaded {len(df):,} incidents")

    # 2. Enrich Prometheus tickets
    click.echo("Enriching Prometheus tickets...")
    df = enrich_prometheus(df)
    prom_count = df["is_prometheus"].sum()
    click.echo(f"  {prom_count:,} Prometheus tickets enriched")

    # 3. Enrich human tickets
    click.echo("Enriching human-filed tickets...")
    df = enrich_human(df)
    human_net = df[~df["is_prometheus"] & df["is_network_related"]].shape[0]
    click.echo(f"  {human_net:,} human tickets flagged as network-related")

    # 4. Normalise locations
    locations_csv = data_dir / "fixtures" / "locations.csv"
    if not locations_csv.exists():
        locations_csv = data_dir / "raw" / "locations.csv"
    locations_df = pd.DataFrame()
    if locations_csv.exists():
        click.echo("Normalising locations...")
        processed_dir = data_dir / "processed"
        processed_dir.mkdir(parents=True, exist_ok=True)
        locations_df = normalise_locations(locations_csv, processed_dir / "locations_clean.csv")
        click.echo(f"  {len(locations_df):,} locations normalised")

    # 5. Build delegation registry and sub-site map
    #    Priority: Grafana fixture > Grafana live API > ServiceNow-only
    click.echo("Building delegation registry...")
    grafana_fixture = data_dir / "fixtures" / "grafana_registry.json"
    grafana_registry = {}
    grafana_subsite = {}

    if grafana_fixture.exists():
        from grafana_client.registry_builder import build_registry_from_fixture
        grafana_registry, grafana_subsite = build_registry_from_fixture(grafana_fixture)
        click.echo(f"  Grafana fixture: {len(grafana_registry)} parent delegations, "
                    f"{len(grafana_subsite)} site codes")

    # ServiceNow-derived registry (fills in country/GPS from curated data + locations)
    snow_registry = build_registry(df, locations_df, grafana_available=bool(grafana_registry))
    snow_subsite = build_subsite_map(df)

    # Merge: Grafana is authoritative for region and sub-site mapping;
    # ServiceNow/curated fills in country, GPS, and codes not in Grafana
    ref_dir = data_dir / "reference"
    ref_dir.mkdir(parents=True, exist_ok=True)

    if grafana_registry:
        # Enrich Grafana registry with country/GPS from ServiceNow registry
        for code, g_entry in grafana_registry.items():
            s_entry = snow_registry.get(code, {})
            if s_entry.get("country") and not g_entry.get("country"):
                g_entry["country"] = s_entry["country"]
                g_entry["country_iso3"] = s_entry.get("country_iso3")
            if s_entry.get("latitude") and not g_entry.get("latitude"):
                g_entry["latitude"] = s_entry["latitude"]
                g_entry["longitude"] = s_entry.get("longitude")
        # Add ServiceNow-only codes not present in Grafana
        for code, s_entry in snow_registry.items():
            if code not in grafana_registry:
                grafana_registry[code] = s_entry
        registry = grafana_registry
        subsite_map = {**snow_subsite, **grafana_subsite}  # Grafana wins on conflicts
    else:
        registry = snow_registry
        subsite_map = snow_subsite

    with open(ref_dir / "delegations.json", "w") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)
    with open(ref_dir / "subsite_map.json", "w") as f:
        json.dump(subsite_map, f, indent=2, ensure_ascii=False)
    subsites = sum(1 for k, v in subsite_map.items() if k != v)
    click.echo(f"  {len(registry)} delegation codes registered, {subsites} sub-sites mapped")

    # 5b. NetBox enrichment (if fixture available)
    netbox_sites_fixture = data_dir / "fixtures" / "netbox_sites.json"
    netbox_circuits_fixture = data_dir / "fixtures" / "netbox_circuits.json"
    if netbox_sites_fixture.exists() and netbox_circuits_fixture.exists():
        from netbox_client.site_matcher import build_site_map
        from netbox_client.circuit_enrichment import (
            load_circuits_from_fixture, enrich_circuits,
        )
        grafana_codes = set(subsite_map.keys())
        nb_site_map = build_site_map(netbox_sites_fixture, grafana_codes)
        click.echo(f"  NetBox sites matched: {len(nb_site_map)} of {len(grafana_codes)} Grafana codes")

        raw_circuits = load_circuits_from_fixture(netbox_circuits_fixture)
        enriched_circuits = enrich_circuits(raw_circuits, subsite_map)
        circuits_path = ref_dir / "circuits.json"
        with open(circuits_path, "w") as f:
            json.dump(enriched_circuits, f, indent=2, ensure_ascii=False)
        with_site = sum(1 for c in enriched_circuits if c["site_code"])
        with_rate = sum(1 for c in enriched_circuits if c["commit_rate_kbps"])
        click.echo(f"  Circuits: {len(enriched_circuits)} total, {with_site} with site code, "
                    f"{with_rate} with commit_rate")

        # Save netbox site map for report
        nb_map_out = {code: {"slug": s.get("slug"), "name": s.get("name")}
                      for code, s in nb_site_map.items()}
        with open(ref_dir / "netbox_site_map.json", "w") as f:
            json.dump(nb_map_out, f, indent=2, ensure_ascii=False)

    # Map sub-site delegation codes to parent codes
    if "delegation_code" in df.columns:
        df["parent_code"] = df["delegation_code"].map(
            lambda c: subsite_map.get(str(c).upper(), c) if pd.notna(c) else None
        )

    # 6. Save processed data
    processed_dir = data_dir / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    # Convert datetime columns for parquet compatibility
    for col in ["opened_dt", "resolved_dt", "closed_dt", "updated_dt"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce")

    output_path = processed_dir / "incidents_all.parquet"
    df.to_parquet(output_path, index=False)
    click.echo(f"  Written {output_path}")

    # Also save prometheus-only subset
    prom_df = df[df["is_prometheus"]].copy()
    prom_path = processed_dir / "prometheus_alerts.parquet"
    prom_df.to_parquet(prom_path, index=False)
    click.echo(f"  Written {prom_path}")

    click.echo("Parsing complete.")


# ── Grafana integration ──────────────────────────────────────────────

def _get_grafana_client():
    from snow_extract.config import GrafanaConfig
    from grafana_client.client import GrafanaClient

    config = GrafanaConfig()
    if not config.is_configured:
        click.echo("Grafana not configured (GRAFANA_URL and GRAFANA_API_TOKEN required).", err=True)
        click.echo("Skipping Grafana operations — ServiceNow-only mode.", err=True)
        return None
    return GrafanaClient(config.url, config.api_token, config.prometheus_ds_id)


@cli.command()
def grafana_build_registry() -> None:
    """Build delegation registry from Grafana FortiGate labels."""
    from grafana_client.registry_builder import build_registry_from_grafana

    client = _get_grafana_client()
    if not client:
        return
    registry = build_registry_from_grafana(client)
    ref_dir = _data_dir() / "reference"
    ref_dir.mkdir(parents=True, exist_ok=True)
    with open(ref_dir / "delegations.json", "w") as f:
        json.dump(registry, f, indent=2)
    click.echo(f"Registry: {len(registry)} delegations from Grafana")
    client.close()


@cli.command()
@click.option("--days", default=7, help="Number of days to pull")
def grafana_bandwidth(days: int) -> None:
    """Pull bandwidth data from Grafana for all sites."""
    from grafana_client.bandwidth import pull_bandwidth

    client = _get_grafana_client()
    if not client:
        return
    registry_path = _data_dir() / "reference" / "delegations.json"
    if registry_path.exists():
        with open(registry_path) as f:
            sites = list(json.load(f).keys())
    else:
        click.echo("No delegation registry found. Run grafana-build-registry first.", err=True)
        return
    output = _data_dir() / "processed" / "bandwidth_by_site.parquet"
    pull_bandwidth(client, sites, days=days)
    client.close()


@cli.command()
@click.option("--days", default=30, help="Number of days")
def grafana_site_status(days: int) -> None:
    """Pull FortiGate site uptime data from Grafana."""
    from grafana_client.site_status import pull_site_status

    client = _get_grafana_client()
    if not client:
        return
    pull_site_status(client, days=days)
    client.close()


@cli.command()
def grafana_export_dashboards() -> None:
    """Export all Grafana dashboard definitions."""
    from grafana_client.dashboards import export_dashboards

    client = _get_grafana_client()
    if not client:
        return
    export_dashboards(client, _data_dir() / "grafana_dashboards")
    client.close()


# ── Analysis ─────────────────────────────────────────────────────────

@cli.command()
@click.option("--field-only", is_flag=True, default=False,
              help="Exclude HQ and UNASSIGNED tickets from charts (field regions only)")
def analyse(field_only: bool) -> None:
    """Run analysis and generate the baseline report."""
    from snow_analyse.baseline_report import generate_report

    data_dir = _data_dir()
    mode = "field-only" if field_only else "full"
    click.echo(f"Generating baseline report ({mode})...")
    output = generate_report(data_dir, field_only=field_only)
    click.echo(f"Report written to {output}")


# ── Pipeline shortcuts ───────────────────────────────────────────────

@cli.command()
@click.option("--start", type=click.DateTime(["%Y-%m-%d"]), default="2024-01-01")
@click.option("--end", type=click.DateTime(["%Y-%m-%d"]), default=str(date.today()))
@click.option("--field-only", is_flag=True, default=False,
              help="Exclude HQ and UNASSIGNED tickets from charts")
@click.pass_context
def run_snow(ctx: click.Context, start: datetime, end: datetime, field_only: bool) -> None:
    """ServiceNow pipeline: parse fixtures/raw -> analyse -> report."""
    ctx.invoke(snow_parse)
    ctx.invoke(analyse, field_only=field_only)


@cli.command()
@click.option("--start", type=click.DateTime(["%Y-%m-%d"]), default="2024-01-01")
@click.option("--end", type=click.DateTime(["%Y-%m-%d"]), default=str(date.today()))
@click.option("--field-only", is_flag=True, default=False,
              help="Exclude HQ and UNASSIGNED tickets from charts")
@click.pass_context
def run_all(ctx: click.Context, start: datetime, end: datetime, field_only: bool) -> None:
    """Full pipeline: all sources -> parse -> analyse -> report."""
    ctx.invoke(snow_parse)
    # Grafana steps degrade gracefully if unconfigured
    ctx.invoke(grafana_build_registry)
    ctx.invoke(grafana_bandwidth, days=7)
    ctx.invoke(grafana_site_status, days=30)
    ctx.invoke(analyse, field_only=field_only)


if __name__ == "__main__":
    cli()
