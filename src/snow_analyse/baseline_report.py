"""Generate the HENRI baseline HTML report from processed data."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd
import numpy as np
from jinja2 import Environment, FileSystemLoader

from snow_parse.parser import load_and_parse
from snow_parse.prometheus_parser import enrich_prometheus
from snow_parse.human_parser import enrich_human
from .timeseries import aggregate_incidents, detect_anomalies
from .surge_detector import detect_surges
from osint.risk_scorer import compute_risk_cards

logger = logging.getLogger(__name__)

# Project root (three levels up: baseline_report.py → snow_analyse → src → project)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_registry(data_dir: Path) -> dict[str, Any]:
    """Load the delegation registry from reference/delegations.json."""
    registry_path = data_dir / "reference" / "delegations.json"
    if registry_path.exists():
        with open(registry_path) as f:
            return json.load(f)
    logger.warning("Delegation registry not found at %s", registry_path)
    return {}


def _load_grafana_bandwidth(data_dir: Path) -> pd.DataFrame | None:
    """Load bandwidth parquet if it exists.

    Checks for both the aggregated ``bandwidth_by_site.parquet`` (preferred)
    and the legacy ``bandwidth.parquet`` file.
    """
    for name in ("bandwidth_by_site.parquet", "bandwidth.parquet"):
        bw_path = data_dir / "processed" / name
        if bw_path.exists():
            logger.info("Loading bandwidth data from %s", bw_path)
            return pd.read_parquet(bw_path)
    return None


def _safe_json(obj: Any) -> str:
    """Serialize to JSON safe for embedding in <script> tags.

    Escapes ``</`` sequences to prevent script injection when used with
    Jinja2's ``| safe`` filter.
    """

    def _default(o: Any) -> Any:
        if isinstance(o, pd.Period):
            return str(o)
        if isinstance(o, (pd.Timestamp, np.datetime64)):
            return str(o)
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        raise TypeError(f"Object of type {type(o)} is not JSON serializable")

    # Escape </ to prevent </script> injection in HTML context
    return json.dumps(obj, default=_default).replace("</", r"<\/")


def _build_summary(df: pd.DataFrame) -> dict[str, Any]:
    """Compute top-level summary statistics."""
    total = len(df)
    automated = int(df["is_prometheus"].sum()) if "is_prometheus" in df.columns else 0
    human = total - automated
    network = int(df["is_network_related"].sum()) if "is_network_related" in df.columns else 0

    return {
        "total_tickets": total,
        "automated_count": automated,
        "automated_pct": round(automated / total * 100, 1) if total else 0,
        "human_count": human,
        "human_pct": round(human / total * 100, 1) if total else 0,
        "network_count": network,
        "network_pct": round(network / total * 100, 1) if total else 0,
    }


def _build_region_chart_data(agg: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Prepare region monthly data for Chart.js bar chart."""
    rm = agg.get("region_monthly")
    if rm is None or rm.empty:
        return {"labels": [], "datasets": []}

    months = sorted(rm["month"].unique())
    regions = sorted(rm["region"].unique())
    labels = [str(m) for m in months]

    # Color palette for regions
    palette = [
        "#D52B1E", "#2C5F8A", "#4CAF50", "#FF9800", "#9C27B0",
        "#00BCD4", "#795548", "#607D8B", "#E91E63", "#3F51B5",
    ]

    datasets = []
    for i, region in enumerate(regions):
        region_data = rm[rm["region"] == region]
        month_counts = {row["month"]: row["count"] for _, row in region_data.iterrows()}
        datasets.append({
            "label": str(region),
            "data": [int(month_counts.get(m, 0)) for m in months],
            "backgroundColor": palette[i % len(palette)],
        })

    return {"labels": labels, "datasets": datasets}


def _build_top_delegations(df: pd.DataFrame, top_n: int = 20) -> list[dict]:
    """Top N most-alerting **parent** delegations with dominant alert type.

    Uses ``parent_code`` when available so that sub-site alerts roll up
    to their parent delegation (e.g. RBUX → YAO).
    """
    prom = df[df["is_prometheus"]].copy()
    code_col = "parent_code" if "parent_code" in prom.columns else "delegation_code"
    prom = prom[prom[code_col].notna()]
    if prom.empty:
        return []

    deleg_counts = prom.groupby(code_col).size().reset_index(name="total_count")
    deleg_counts = deleg_counts.nlargest(top_n, "total_count")

    result = []
    for _, row in deleg_counts.iterrows():
        code = row[code_col]
        subset = prom[prom[code_col] == code]
        dominant = subset["alert_name"].value_counts()
        dominant_alert = dominant.index[0] if not dominant.empty else "N/A"
        dominant_count = int(dominant.iloc[0]) if not dominant.empty else 0
        result.append({
            "delegation_code": code,
            "total_count": int(row["total_count"]),
            "dominant_alert": dominant_alert,
            "dominant_count": dominant_count,
        })

    return result


def _build_sitedown_heatmap(df: pd.DataFrame) -> dict[str, Any]:
    """FortigateSiteDown heatmap: parent delegation x month matrix.

    Uses ``parent_code`` to roll up sub-site events to their parent.
    """
    code_col = "parent_code" if "parent_code" in df.columns else "delegation_code"
    sd = df[
        (df["alert_name"] == "FortigateSiteDown")
        & df[code_col].notna()
        & df["opened_dt"].notna()
    ].copy()

    if sd.empty:
        return {"delegations": [], "months": [], "matrix": [], "max_count": 0}

    sd["month"] = sd["opened_dt"].dt.to_period("M")

    pivot = sd.groupby([code_col, "month"]).size().reset_index(name="count")
    months = sorted(pivot["month"].unique())
    delegations = sorted(pivot[code_col].unique())

    # Build a lookup
    lookup: dict[tuple[str, str], int] = {}
    for _, row in pivot.iterrows():
        lookup[(row[code_col], str(row["month"]))] = int(row["count"])

    month_strs = [str(m) for m in months]
    matrix = []
    for deleg in delegations:
        row_data = [lookup.get((deleg, m), 0) for m in month_strs]
        matrix.append(row_data)

    max_count = max((max(r) for r in matrix if r), default=0)

    return {
        "delegations": list(delegations),
        "months": month_strs,
        "matrix": matrix,
        "max_count": max_count,
    }


def _build_keyword_breakdown(df: pd.DataFrame) -> list[dict]:
    """Human ticket keyword frequency by region."""
    human = df[~df["is_prometheus"]].copy()
    if human.empty or "matched_keywords" not in human.columns:
        return []

    rows = []
    for _, row in human.iterrows():
        try:
            keywords = json.loads(row["matched_keywords"])
        except (json.JSONDecodeError, TypeError):
            keywords = []
        region = row.get("region", "Unknown")
        for kw in keywords:
            rows.append({"region": region, "keyword": kw})

    if not rows:
        return []

    kw_df = pd.DataFrame(rows)
    result = (
        kw_df.groupby(["region", "keyword"])
        .size()
        .reset_index(name="count")
        .sort_values(["region", "count"], ascending=[True, False])
    )

    return result.to_dict("records")


def _build_category_chart_data(df: pd.DataFrame) -> dict[str, Any]:
    """Alert category distribution for Chart.js pie chart."""
    prom = df[df["is_prometheus"] & df["alert_category"].notna()].copy()
    if prom.empty:
        return {"labels": [], "data": [], "colors": []}

    counts = prom["alert_category"].value_counts()
    labels = counts.index.tolist()
    data = [int(v) for v in counts.values]

    palette = [
        "#D52B1E", "#2C5F8A", "#4CAF50", "#FF9800", "#9C27B0",
        "#00BCD4", "#795548", "#607D8B", "#E91E63", "#3F51B5",
        "#CDDC39", "#FF5722", "#009688", "#673AB7", "#FFC107",
    ]
    colors = [palette[i % len(palette)] for i in range(len(labels))]

    return {"labels": labels, "data": data, "colors": colors}


def _build_bandwidth_context(bw_df: pd.DataFrame | None) -> dict[str, Any] | None:
    """Prepare Grafana bandwidth overview data if available."""
    if bw_df is None or bw_df.empty:
        return None

    # Aggregate per site
    site_agg = (
        bw_df.groupby(["site", "direction"])
        .agg(avg_bps=("avg_bps", "mean"), peak_bps=("peak_bps", "max"), p95_bps=("p95_bps", "mean"))
        .reset_index()
    )

    # Top sites by throughput (average of in + out)
    site_total = (
        bw_df.groupby("site")["avg_bps"]
        .mean()
        .reset_index()
        .sort_values("avg_bps", ascending=False)
    )

    top_sites = site_total.head(10).to_dict("records")
    bottom_sites = site_total.tail(10).to_dict("records")

    # Format bps values for display
    def fmt_bps(val: float) -> str:
        if val >= 1e9:
            return f"{val / 1e9:.1f} Gbps"
        if val >= 1e6:
            return f"{val / 1e6:.1f} Mbps"
        if val >= 1e3:
            return f"{val / 1e3:.1f} Kbps"
        return f"{val:.0f} bps"

    for row in top_sites + bottom_sites:
        row["avg_bps_fmt"] = fmt_bps(row["avg_bps"])

    return {
        "top_sites": top_sites,
        "bottom_sites": bottom_sites,
        "total_sites": len(site_total),
    }


def _build_data_completeness(data_dir: Path, registry: dict) -> dict[str, Any] | None:
    """Build data completeness context: NetBox/Grafana coverage stats."""
    ref = data_dir / "reference"
    nb_map_path = ref / "netbox_site_map.json"
    circuits_path = ref / "circuits.json"

    if not nb_map_path.exists():
        return None

    with open(nb_map_path) as f:
        nb_site_map = json.load(f)

    grafana_sites = {k for k, v in registry.items() if v.get("source", "").startswith("grafana")}
    nb_matched = set(nb_site_map.keys())
    nb_matched_grafana = nb_matched & grafana_sites

    circuits: list[dict] = []
    if circuits_path.exists():
        with open(circuits_path) as f:
            circuits = json.load(f)

    total_circuits = len(circuits)
    with_site = sum(1 for c in circuits if c.get("site_code"))
    with_rate = sum(1 for c in circuits if c.get("commit_rate_kbps"))

    # Per-provider circuit breakdown
    provider_counts: dict[str, int] = {}
    for c in circuits:
        p = c.get("provider", "Unknown")
        if p:
            provider_counts[p] = provider_counts.get(p, 0) + 1
    top_providers = sorted(provider_counts.items(), key=lambda x: -x[1])[:10]

    return {
        "grafana_total_sites": len(grafana_sites),
        "netbox_matched": len(nb_matched_grafana),
        "netbox_total": len(nb_site_map),
        "netbox_pct": round(len(nb_matched_grafana) / len(grafana_sites) * 100, 1) if grafana_sites else 0,
        "total_circuits": total_circuits,
        "circuits_with_site": with_site,
        "circuits_with_rate": with_rate,
        "circuits_rate_pct": round(with_rate / total_circuits * 100, 1) if total_circuits else 0,
        "top_providers": top_providers,
    }


def _build_threat_landscape(
    data_dir: Path,
    registry: dict[str, Any],
    *,
    use_fixtures: bool = False,
) -> list[dict[str, Any]] | None:
    """Build threat landscape data from OSINT sources.

    Tries live APIs first (ACLED, IODA, Cloudflare), falls back to
    fixtures if credentials are missing or APIs are unavailable.
    When *use_fixtures* is True, always uses fixture files.

    Returns a list of risk cards sorted by combined risk score descending,
    or None if no data is available.
    """
    try:
        cards = compute_risk_cards(data_dir, registry, use_fixtures=use_fixtures)
    except Exception as exc:
        logger.warning("Threat landscape computation failed: %s", exc)
        return None

    if not cards:
        return None

    return cards


def generate_report(
    data_dir: Path,
    *,
    field_only: bool = False,
    use_fixtures: bool = False,
    deltas: list[dict] | None = None,
    output_name: str | None = None,
) -> Path:
    """Generate the HENRI baseline HTML report.

    Loads processed data from *data_dir*, runs all analysis, renders
    the Jinja2 template, and writes the report to
    ``data_dir/reports/<output_name>`` (or the default name).

    Parameters
    ----------
    data_dir : Path
        Root data directory containing ``raw/`` (or ``fixtures/``),
        ``reference/``, and ``processed/`` subdirectories.
    field_only : bool
        If True, filter out HQ and UNASSIGNED tickets from charts and
        tables (summary cards still show totals). Produces a report
        focused on the six field ICT regions.

    Returns
    -------
    Path
        Path to the generated HTML report.
    """
    data_dir = Path(data_dir)

    # Load data — prefer processed parquet, fall back to raw CSV parsing
    parquet_path = data_dir / "processed" / "incidents_all.parquet"
    if parquet_path.exists():
        logger.info("Loading processed incidents from %s", parquet_path)
        df = pd.read_parquet(parquet_path)
    else:
        logger.info("Loading and parsing ServiceNow data from %s", data_dir)
        df = load_and_parse(data_dir)
        if not df.empty:
            df = enrich_prometheus(df)
            df = enrich_human(df)

    if df.empty:
        logger.warning("No data loaded; generating a minimal report")
        df = pd.DataFrame()

    registry = _load_registry(data_dir)

    # Assign region from registry, with hostname-based HQ detection and L1 tagging
    if not df.empty:
        lookup_col = "parent_code" if "parent_code" in df.columns else "delegation_code"
        if lookup_col in df.columns:
            df["region"] = df[lookup_col].apply(
                lambda c: registry.get(str(c).upper() if pd.notna(c) else "", {}).get("region") or "Unknown"
            )

        # Fix 1: Hostname-based HQ detection — tickets with GVA hostnames
        # in non-L2 groups (e.g. "TI EXPR LOGFIN") are HQ infrastructure
        if "hostname" in df.columns:
            gva_mask = (
                df["region"].eq("Unknown")
                & (
                    df["hostname"].str.contains(".gva.icrc.priv", case=False, na=False)
                    | df["hostname"].str.lower().str.startswith("gva", na=False)
                )
            )
            df.loc[gva_mask, "region"] = "HQ"
            df.loc[gva_mask, "parent_code"] = df.loc[gva_mask, "parent_code"].fillna("GVA")
            gva_count = gva_mask.sum()
            if gva_count:
                logger.info("Reclassified %d tickets as HQ via hostname detection", gva_count)

        # Central infrastructure teams (no delegation code) → HQ
        if "assignment_group" in df.columns:
            central_mask = (
                df["region"].eq("Unknown")
                & df["assignment_group"].str.match(r"^TI\s", case=False, na=False)
            )
            df.loc[central_mask, "region"] = "HQ"
            central_count = central_mask.sum()
            if central_count:
                logger.info("Reclassified %d central IT tickets as HQ", central_count)

        # Fix 2: Tag L1 ServiceDesk tickets as UNASSIGNED (not "Unknown")
        if "assignment_group" in df.columns:
            l1_mask = (
                df["assignment_group"].str.contains(r"L1|Service.?Desk", case=False, na=False, regex=True)
                & df["region"].eq("Unknown")
            )
            df.loc[l1_mask, "region"] = "UNASSIGNED"
            l1_count = l1_mask.sum()
            if l1_count:
                logger.info("Tagged %d L1/ServiceDesk tickets as UNASSIGNED", l1_count)

    # Summary always uses full data
    summary = _build_summary(df) if not df.empty else {
        "total_tickets": 0, "automated_count": 0, "automated_pct": 0,
        "human_count": 0, "human_pct": 0, "network_count": 0, "network_pct": 0,
    }

    # For charts/tables, optionally filter to field regions only
    _EXCLUDED_REGIONS = {"HQ", "UNASSIGNED", "Unknown"} if field_only else set()
    chart_df = df
    if field_only and not df.empty and "region" in df.columns:
        chart_df = df[~df["region"].isin(_EXCLUDED_REGIONS)].copy()
        logger.info(
            "Field-only mode: %d of %d tickets in scope (excluded HQ/UNASSIGNED/Unknown)",
            len(chart_df), len(df),
        )

    agg = aggregate_incidents(chart_df) if not chart_df.empty else {}
    region_chart = _build_region_chart_data(agg)
    top_delegations = _build_top_delegations(chart_df) if not chart_df.empty else []
    sitedown_heatmap = _build_sitedown_heatmap(chart_df) if not chart_df.empty else {
        "delegations": [], "months": [], "matrix": [], "max_count": 0,
    }
    surges = detect_surges(chart_df, registry) if not chart_df.empty else []
    keyword_breakdown = _build_keyword_breakdown(chart_df) if not chart_df.empty else []
    category_chart = _build_category_chart_data(chart_df) if not chart_df.empty else {
        "labels": [], "data": [], "colors": [],
    }

    # Anomalies
    anomalies = []
    if not chart_df.empty and "delegation_code" in chart_df.columns:
        try:
            anom_df = detect_anomalies(chart_df[chart_df["delegation_code"].notna()], "delegation_code")
            anomalies = anom_df.to_dict("records")
        except Exception as exc:
            logger.warning("Anomaly detection failed: %s", exc)

    # Grafana data (optional)
    bw_df = _load_grafana_bandwidth(data_dir)
    bandwidth_ctx = _build_bandwidth_context(bw_df)

    # Data completeness (NetBox + Grafana coverage)
    completeness = _build_data_completeness(data_dir, registry)

    # External threat landscape (OSINT)
    threat_landscape = _build_threat_landscape(data_dir, registry, use_fixtures=use_fixtures)

    # Precursor analysis
    precursor_ctx = None
    try:
        from snow_analyse.precursor import analyse_precursors, compute_precursor_stats
        if surges:
            precursor_data = analyse_precursors(surges, registry, data_dir)
            precursor_stats = compute_precursor_stats(precursor_data)
            # Only include surges that had precursors for the report
            precursor_with = [p for p in precursor_data if p["any_external_precursor"] or p["internal_precursor"]["detected"]]
            if precursor_data:
                precursor_ctx = {"stats": precursor_stats, "surges": precursor_with[:30]}
    except Exception as exc:
        logger.warning("Precursor analysis failed: %s", exc)

    # Forward-looking alerts
    forward_alerts: list[dict] = []
    try:
        from henri.forward_alert import check_forward_alerts
        forward_alerts = check_forward_alerts(data_dir, registry)
    except Exception as exc:
        logger.warning("Forward alert check failed: %s", exc)

    # Prepare template context
    context = {
        "summary": summary,
        "region_chart_json": _safe_json(region_chart),
        "top_delegations": top_delegations,
        "sitedown_heatmap": sitedown_heatmap,
        "surges": surges,
        "keyword_breakdown": keyword_breakdown,
        "category_chart_json": _safe_json(category_chart),
        "anomalies": anomalies,
        "has_grafana_data": bandwidth_ctx is not None,
        "bandwidth": bandwidth_ctx,
        "field_only": field_only,
        "completeness": completeness,
        "threat_landscape": threat_landscape,
        "delta_alerts": deltas or [],
        "has_deltas": bool(deltas),
        "precursor": precursor_ctx,
        "forward_alerts": forward_alerts,
    }

    # Render template
    template_dir = _PROJECT_ROOT / "templates"
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=True,
    )
    template = env.get_template("baseline_report.html.j2")
    html = template.render(**context)

    # Write output
    output_dir = data_dir / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    if output_name:
        filename = output_name
    elif field_only:
        filename = "baseline_report_field.html"
    else:
        filename = "baseline_report.html"
    output_path = output_dir / filename
    output_path.write_text(html, encoding="utf-8")

    logger.info("Baseline report written to %s", output_path)
    return output_path
