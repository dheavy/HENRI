# HENRI — Phase 0: Network intelligence extraction toolkit

## Context

I'm building **HENRI** (Humanitarian Early-warning Network Resilience Intelligence) — a network intelligence pipeline for a large humanitarian organisation (ICRC). The goal is to fuse internal network data with external OSINT to produce actionable reports on field infrastructure. This is Phase 0: extracting and analysing data from ServiceNow and Grafana — our two currently accessible sources.

**ServiceNow**: URL-based CSV export works from our instance. No API access; extraction is done via authenticated browser session hitting `incident_list.do?CSV&...` URLs. An initial 50,000-row export has been analysed. Key discovery: **74% of tickets are auto-generated Prometheus alerts** with structured descriptions like `? Prometheus - KADFGT - FortigateSiteDown`. The hostname encodes a 3-letter delegation code (KAD = Kaduna) and a device type suffix (FGT = FortiGate). There are 201 distinct delegation codes across 6 ICT regions.

**Grafana**: We have Viewer access to a rich set of Field dashboards (ICT Resilience, Fortinet, IOT, Starlink, Electricity, etc.). A Grafana API service account (Viewer role) is being provisioned. Direct Prometheus access is being cut for security — **Grafana's data source proxy is the only long-term path to PromQL queries**.

Critical discovery: all Prometheus targets carry a `location_site` label that is the **universal join key** across everything. FortiGate targets also carry `region` and `smt_assignmentgroup` labels that map directly to ServiceNow fields. Bandwidth data (`ifHCInOctets/ifHCOutOctets`) exists for ~100 sites with downsampled recording rules for long-term retention.

## What to build

A Python toolkit in a single project with the following modules. Use Python 3.11+, type hints throughout, `uv` for dependency management. Keep it containerisable (include a Dockerfile and docker-compose.yml for local dev).

### 1. `snow_extract/` — ServiceNow CSV extraction

**`snow_extract/exporter.py`**: Playwright-based extraction that:
- Authenticates to ServiceNow via SSO (configurable for different IdPs — start with a simple username/password login to `login.do`, with hooks for SAML/Okta flows)
- Saves and reuses session state (`storage_state`) to avoid re-auth on subsequent runs
- Constructs export URLs with configurable table, fields, query filters, and date range
- Handles the 10,000-row limit by batching exports by month (e.g. `opened_at>=2025-12-01^opened_at<2026-01-01`)
- Saves each batch as a CSV in `data/raw/incidents_YYYY-MM.csv`
- Supports incremental mode: only fetch rows where `sys_updated_on>=<last_run_timestamp>`
- Also exports the `cmn_location` table (once, not incremental): `cmn_location_list.do?CSV&sysparm_fields=sys_id,name,city,state,country,latitude,longitude,parent&sysparm_default_export_fields=all`

**`snow_extract/config.py`**: Configuration via environment variables or `.env` file:
```
SNOW_INSTANCE_URL=https://smt.ext.icrc.org/
SNOW_USERNAME=...
SNOW_PASSWORD=...
SNOW_EXPORT_FIELDS=sys_id,number,short_description,priority,urgency,impact,state,category,subcategory,opened_at,resolved_at,closed_at,location,cmdb_ci,assignment_group,sys_updated_on
SNOW_EXPORT_START_DATE=2024-01-01
DATA_DIR=./data
```

### 2. `snow_parse/` — Incident parsing and enrichment

**`snow_parse/parser.py`**: Parse the raw CSV exports into structured records:
- Load all CSVs from `data/raw/` and deduplicate on `sys_id`
- Parse `opened_at` and other timestamps (format: `DD.MM.YYYY HH:MM:SS`) into proper datetime objects
- Classify each ticket as `prometheus_automated` or `human_filed` based on the `? Prometheus` prefix in `short_description`

**`snow_parse/prometheus_parser.py`**: For Prometheus-automated tickets, extract structured fields from the `short_description` using regex:
- Pattern: `? Prometheus - <HOSTNAME> - <ALERT_NAME>`
- From the hostname, extract the **delegation code** (first 2-4 uppercase letters before a device-type suffix)
- Known device-type suffixes to strip: `FGT` (FortiGate), `SPM`, `SWI`, `RTR`, etc. — but be flexible, not all hostnames follow the same pattern. Some are FQDNs like `gvacfsp2app03p.gva.icrc.priv` where the delegation code is in the domain segment (e.g. `gva`)
- Extract the **alert name** (the last segment after ` - `)
- Categorise alerts into network-relevant groups:
  - `site_down`: FortigateSiteDown, FemTargetDown, CollectorNodeDown
  - `wan_degraded`: FortigateWanLatencyDeviation, FortigateWanLatency
  - `voip_down`: AudiocodesPingDown
  - `capacity`: DhcpHighDHCPAddressUsageByScope
  - `packet_loss`: VmwareHostHighDroppedPacketsRx
  - `latency`: LdapBindLatencyCritical
  - `server`: WindowsServerDown, WindowsServerCpuUsage, WindowsServerMemoryUsage, etc.
  - `other`: everything else

**`snow_parse/human_parser.py`**: For human-filed tickets, classify as network-related using multilingual keyword matching:
- English: network, dns, vpn, bandwidth, internet, connectivity, wifi, wi-fi, firewall, router, switch, vsat, link down, latency, proxy, slow, cannot connect, no access
- French: réseau, connexion, internet, lent, pas de connexion, problème de connexion, wifi
- Spanish: internet, red, conexión, lento, problemas con internet, vpn
- Tag each human ticket with matched keywords for later analysis

**`snow_parse/delegation_registry.py`**: Build and maintain the canonical delegation code mapping. **Primary source is Grafana** (much more complete than ServiceNow alone):
- If Grafana API is configured, query `group by (location_site, region, smt_assignmentgroup) (up{job="fortigate"})` via the Grafana proxy to get the authoritative site→region→assignment group mapping (~220 entries). This is the ground truth.
- Fallback: extract 3-letter codes from ServiceNow `assignment_group` values matching pattern `<CODE> ICT L2 Support`
- Merge GPS coordinates from `cmn_location` where a fuzzy match exists (e.g. "Juba" in `cmn_location.city` matches JUB)
- Map country names to ISO 3166-1 alpha-3 codes using `pycountry`
- Output: `data/reference/delegations.json` with structure:
  ```json
  {
    "JUB": {
      "name": "Juba",
      "region": "AFRICA East",
      "country": "South Sudan",
      "country_iso3": "SSD",
      "smt_assignmentgroup": "JUB ICT L2 SUPPORT",
      "latitude": 4.85,
      "longitude": 31.61,
      "source": "grafana_fortigate_labels"
    }
  }
  ```
- The `region` values from Prometheus are: `AFRICA East`, `AFRICA West`, `NAME`, `AMERICAS`, `EURASIA`, `ASIA`, `HQ`

**`snow_parse/location_normaliser.py`**: Clean and normalise the `cmn_location` export:
- Deduplicate country names: "Mali | Mali" → "Mali", "CAMEROON" → "Cameroon", etc.
- Map country names to ISO 3166-1 alpha-3 codes using `pycountry`
- Flag entries with missing GPS that have a city+country (candidates for geocoding later)
- Output: `data/processed/locations_clean.csv`

### 3. `grafana_client/` — Grafana API integration

**`grafana_client/client.py`**: Grafana API client for proxied PromQL queries and dashboard introspection:
- Authenticate via service account API token (header: `Authorization: Bearer <token>`)
- Base URL from config (e.g. `https://grafana.internal`)
- Discover Prometheus data sources: `GET /api/datasources` → find the one with `type: "prometheus"` → extract its `id` (or `uid`)
- Execute PromQL queries through the data source proxy:
  ```
  GET /api/datasources/proxy/<datasource_id>/api/v1/query?query=<promql>
  GET /api/datasources/proxy/<datasource_id>/api/v1/query_range?query=<promql>&start=<ts>&end=<ts>&step=<s>
  ```
  If the proxy endpoint is restricted, fall back to the unified query endpoint:
  ```
  POST /api/ds/query
  ```
- Return results as Pandas DataFrames (same pattern as `prometheus-api-client`)
- Implement retry logic and rate limiting (be respectful — this is a shared Grafana instance)

**`grafana_client/registry_builder.py`**: Auto-populate the delegation registry from Grafana:
- Query: `group by (location_site, region, smt_assignmentgroup) (up{job="fortigate"})` via the proxy
- Parse the response into the delegation registry format
- This is the **primary source** for the registry — far more complete than ServiceNow parsing

**`grafana_client/bandwidth.py`**: Pull bandwidth metrics for all sites:
- For each known `location_site`, query:
  ```promql
  rate(ifHCInOctets{location_site="<site>"}[1h]) * 8
  rate(ifHCOutOctets{location_site="<site>"}[1h]) * 8
  ```
- Also try the downsampled variants for longer time ranges:
  ```promql
  ifHCInOctets:downsampled{location_site="<site>"}
  ifHCOutOctets:downsampled{location_site="<site>"}
  ```
- Aggregate: per-site daily average, peak, and 95th percentile throughput
- Output: `data/processed/bandwidth_by_site.parquet`

**`grafana_client/site_status.py`**: Pull FortiGate site status for all sites:
- Query: `up{job="fortigate"}` → current up/down state per site
- Historical: `up{job="fortigate", location_site="<site>"}` over time range → calculate uptime percentage
- Output: `data/processed/site_uptime.parquet`

**`grafana_client/dashboards.py`**: Export dashboard definitions for reverse-engineering:
- List all dashboards: `GET /api/search?type=dash-db`
- Export each dashboard JSON: `GET /api/dashboards/uid/<uid>`
- Save to `data/grafana_dashboards/` for analysis of existing PromQL queries
- Extract all PromQL queries from the dashboard JSON panels → save as `data/reference/grafana_queries.json` for reuse

### 4. `snow_analyse/` — Analysis and reporting

**`snow_analyse/timeseries.py`**: Time-series analysis:
- Aggregate incidents by delegation code, ICT region, alert category, and time bucket (daily, weekly, monthly)
- Compute rolling averages and standard deviations for baseline detection
- Flag **anomalies**: periods where incident count exceeds mean + 2σ for a given delegation or region
- Special focus on `FortigateSiteDown` events: time-series by delegation and by region

**`snow_analyse/surge_detector.py`**: UC-2 precursor signal detection:
- Detect **regional clusters**: time windows (e.g. 24h, 48h, 7d) where multiple delegations in the same ICT region have `FortigateSiteDown` events
- Score each cluster: number of affected delegations, total duration, whether it was preceded by WAN latency deviations
- Output a ranked list of historical surge events with timestamps, affected delegations, and duration

**`snow_analyse/baseline_report.py`**: Generate the Phase 0 baseline report as HTML:
- Per-region monthly incident volume chart (mirroring the ServiceNow PA dashboard for validation)
- Top 20 most-alerting delegations with their dominant alert types
- `FortigateSiteDown` heatmap: delegation × month matrix with colour intensity = event count
- Regional surge timeline: the detected clusters from `surge_detector.py` plotted chronologically
- Human ticket keyword frequency cloud by region
- Summary statistics: total tickets, automated vs human split, network-relevant percentage, top categories
- **If Grafana data is available** (bandwidth_by_site.parquet exists):
  - Per-region bandwidth overview: total throughput, average utilisation
  - Top 10 highest-bandwidth sites and bottom 10 lowest
  - Sites with `up{job="fortigate"} == 0` currently (offline right now)
- Use a Jinja2 template for the HTML report, with embedded Chart.js for the charts
- The report should adapt gracefully: ServiceNow-only sections always render, Grafana sections render when data is present
- Output: `data/reports/baseline_report.html`

### 5. `data/` — Data directory structure

```
data/
├── raw/                          # Raw CSV exports from ServiceNow
│   ├── incidents_2025-11.csv
│   ├── incidents_2025-12.csv
│   └── ...
├── processed/                    # Parsed and enriched data
│   ├── incidents_all.parquet     # Deduplicated, parsed, enriched
│   ├── locations_clean.csv       # Normalised cmn_location
│   ├── prometheus_alerts.parquet # Prometheus tickets with parsed fields
│   ├── bandwidth_by_site.parquet # Grafana: throughput per site over time
│   └── site_uptime.parquet       # Grafana: FortiGate uptime per site
├── reference/                    # Curated reference data
│   ├── delegations.json          # Delegation code registry (auto + manual)
│   └── grafana_queries.json      # Extracted PromQL queries from dashboards
├── grafana_dashboards/           # Exported Grafana dashboard JSON definitions
└── reports/                      # Generated reports
    └── baseline_report.html
```

Use Parquet for the main data files (fast, typed, columnar). CSV for reference data that humans edit.

### 6. `cli.py` — Command-line interface

A single CLI entry point using `click`:

```bash
# === ServiceNow extraction ===
# Full extraction (batched by month)
python cli.py snow-extract --start 2024-01-01 --end 2026-03-27

# Incremental extraction (since last run)
python cli.py snow-extract --incremental

# Extract locations table only
python cli.py snow-extract-locations

# Parse all raw CSVs → processed parquet
python cli.py snow-parse

# === Grafana integration ===
# Build delegation registry from Grafana FortiGate labels (primary method)
python cli.py grafana-build-registry

# Pull bandwidth data for all sites (last 7 days by default)
python cli.py grafana-bandwidth --days 7

# Pull site uptime data
python cli.py grafana-site-status --days 30

# Export all Grafana dashboard definitions
python cli.py grafana-export-dashboards

# === Analysis ===
# Run analysis and generate baseline report
python cli.py analyse

# === Full pipelines ===
# ServiceNow only: extract → parse → analyse
python cli.py run-snow --start 2024-01-01 --end 2026-03-27

# Full pipeline: extract all sources → parse → analyse
python cli.py run-all --start 2024-01-01 --end 2026-03-27
```

### 7. Project files

**`pyproject.toml`**: Dependencies:
- `playwright` (browser automation for ServiceNow)
- `httpx` (async HTTP client for Grafana API — preferred over `requests` for async support)
- `pandas` + `pyarrow` (data processing and parquet)
- `click` (CLI)
- `pycountry` (ISO code mapping)
- `python-dotenv` (config)
- `jinja2` (report templates)
- `thefuzz` (fuzzy string matching for location→delegation matching)

**`Dockerfile`**: Python 3.11-slim base, install Playwright with Chromium, copy project, install deps.

**`docker-compose.yml`**: Single service for now; mounts `./data` as a volume so exports persist.

**`.env.example`**: Template with all required environment variables:
```
# ServiceNow
SNOW_INSTANCE_URL=https://smt.xxx.icrc.org/
SNOW_USERNAME=...
SNOW_PASSWORD=...
SNOW_EXPORT_FIELDS=sys_id,number,short_description,priority,urgency,impact,state,category,subcategory,opened_at,resolved_at,closed_at,location,cmdb_ci,assignment_group,sys_updated_on
SNOW_EXPORT_START_DATE=2024-01-01

# Grafana
GRAFANA_URL=https://grafana.internal
GRAFANA_API_TOKEN=...
GRAFANA_PROMETHEUS_DS_ID=1

# General
DATA_DIR=./data
```

## Important constraints

- **All data stays on-prem.** No external API calls in this phase (OSINT comes in Phase 2). Grafana is internal infrastructure.
- The ServiceNow instance URL, credentials, and Grafana API token should never be hardcoded — always from env vars.
- Be defensive with parsing: not all Prometheus tickets follow the exact same pattern. Log warnings for unparseable tickets rather than crashing.
- The delegation registry from Grafana will be near-complete (~220 sites from FortiGate labels). Sites that appear in ServiceNow but not in Grafana should be flagged as `source: "servicenow_only"`.
- Timestamps in the ServiceNow CSV use the format `DD.MM.YYYY HH:MM:SS` (European format, no timezone — assume UTC).
- The CSV export uses double-quote delimiters and comma separators.
- Some `short_description` values contain the `?` prefix character (literal, not a question mark placeholder) — this is the Prometheus alert marker.
- The Grafana API token may not be available immediately. All Grafana-dependent functionality must degrade gracefully — the ServiceNow pipeline must work standalone, and the registry builder should fall back to ServiceNow-derived data when Grafana is unavailable.
- Be respectful with Grafana API usage: this is a shared production instance. Implement rate limiting (max 2 requests/second), use reasonable time ranges, and cache responses locally.

## What success looks like

After running `python cli.py run-all`, I should have:

1. A `data/processed/incidents_all.parquet` file with all incidents, each tagged with: `is_prometheus`, `delegation_code`, `alert_name`, `alert_category`, `is_network_related`
2. A `data/reference/delegations.json` mapping ~220 site codes to names/regions/countries/GPS — auto-populated from Grafana FortiGate labels, enriched with GPS from `cmn_location`
3. A `data/processed/bandwidth_by_site.parquet` with throughput time series per site (when Grafana API is available)
4. A `data/processed/site_uptime.parquet` with FortiGate uptime history per site (when Grafana API is available)
5. A `data/reports/baseline_report.html` that I can open in a browser and show to the Head of Field IT Services — it should visually answer: "what are the patterns in our network incidents and performance across regions and delegations?"

The baseline report should include:
- Per-region monthly incident volume chart (mirroring ServiceNow PA dashboard for validation)
- Top 20 most-alerting delegations with their dominant alert types
- `FortigateSiteDown` heatmap: delegation × month matrix with colour intensity = event count
- Regional surge timeline: detected clusters plotted chronologically
- If Grafana data is available: per-region bandwidth utilisation overview, top/bottom 10 sites by throughput
- Human ticket keyword frequency breakdown by region
- Summary statistics: total tickets, automated vs human split, network-relevant percentage
