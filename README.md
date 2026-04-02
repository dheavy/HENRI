```
  .          ...                .       .
 .      . . ..:++=====-:.    .       .. .
  .     ..:=+#%##***##%%%+==-:.       ...  ..
       ..+#%###*********+=*%#%#+... .
   ....-#%%#=:.............:+##%%*:.......
   ...-%%%+:................:**%%##=::.... .
   ...-%%*-:................:+##%%%*:::....
   ...:#%*-:...............:-+#%%@@+:.....
 . ...:+%*-:........:==-::::-*%%##*:......  .
   ...:*%#==-=+=:..:=-+-:.::-+%*+=-:::...  .
   ...:-*%++==--=..........:-+#+--:::::..
   ...:::#=:...:-..::......:-*%-:::::::..  .
   ...:::*#-...::..::.:....:-#%=-=:::::...
  ....:::+@*-..-+#*+-::-:::-+#%%+:::::::.
   ...:::+%%*--=##*##*+*+=++*#%@#-:::.:..
 .....:::#%%%%%%%#-::-+%%*###%%%+::...:..   .
.. ...::-%%%%@@%**++=:..=##%%%*-=::::::.... .
   ...:::=%%%@@@+-.....:=%%%+..:#%=::::....
   ...::::::=*+=##+==+*#*+:...:+*@@#-::......
   ...::::::::::=+**===:....:=+-#%%%%%+-.....
   ...:::::::::=%#=-=:..:=+##*:#%####%%#*-...
  ....:::::-+*%@@@@%***#%%#=:.#######*##*-..
 . ..-+##%%%%%%%%@@%%#%%##+..*######****=:..
   .=#%%%%#%%%%%%%%%%%%%#*-.+##******++*=...
 ..:*#%%%%###%%*-:..=*#**#==#*******+===-...
 .:+**###%%%%#:..  ...-*+:-*******++===+-...
 ..:=+***###*:..     .....-++++++==--=+=:...
 ....::-=**+-..        ...::::--::..:.:.....
...... .......   .     ...... ...::.::::...
  .                         .  ........... .

    HENRI — Humanitarian Early-warning Network
             Resilience Intelligence
```

> Named after Henri Dunant, founder of the ICRC and first Nobel Peace Prize laureate. He'd probably appreciate that 160 years later, his organisation is using network intelligence to anticipate disruptions before they hit.

**Creator and maintainer:** Davy Braun <dbraun@icrc.org> — T&I Architecture

---

## Table of contents

- [Introduction](#introduction)
- [Use cases](#use-cases)
- [Tech stack](#tech-stack)
- [Architecture](#architecture)
- [Quickstart](#quickstart)
- [Deployment](#deployment)
- [Dashboard](#dashboard)
- [Pages](#pages)
- [Data sources](#data-sources)
- [Testing](#testing)
- [Known issues](#known-issues)
- [Contributing](#contributing)
- [License](#license)

---

## Introduction

HENRI is a network intelligence platform for ICRC that fuses internal network data (ServiceNow incidents, Grafana/Prometheus metrics, NetBox inventory) with external open-source intelligence (ACLED conflict data, IODA outage detection, Cloudflare Radar) to produce actionable early-warning intelligence for field infrastructure across ~110 delegations in conflict-affected regions worldwide.

The platform answers one question: **"Is anything about to go down, and can we see it coming?"**

54% of historical network outage surges had detectable external warning signals — visible hours to days before the outage hit. HENRI surfaces these signals in real-time.

## Use cases

| # | Use case | What it does |
|---|----------|-------------|
| **UC-1** | Bandwidth optimisation | Compares actual throughput (Grafana) vs contracted capacity (NetBox) per site. Identifies over-utilised (>80%) and under-utilised (<10%) links for ISP negotiation leverage. |
| **UC-2** | Crisis-pattern early warning | Correlates ACLED conflict escalation → IODA/Cloudflare internet outages → FortigateSiteDown surges in ServiceNow. Forward-looking alerts flag countries where conflict activity is spiking above baseline. |
| **UC-3** | Data coherence validation | Cross-references NetBox inventory vs Grafana observed state vs ServiceNow incidents. Highlights gaps: sites without inventory records, circuits without committed rates, silent sites with zero incidents. |
| **UC-4** | Strategic infrastructure siting | Automate the comparative analysis (e.g. Bangkok vs Manila) that today takes weeks of manual research. *(Future)* |

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.13, FastAPI, uvicorn, APScheduler |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS v4, Recharts, countUp.js |
| Data | Pandas, PyArrow (Parquet), SQLite |
| Extraction | Playwright (ServiceNow browser automation), httpx (API clients) |
| Deployment | Docker (multi-stage), OpenShift, Kustomize, Azure Pipelines |
| Testing | pytest (336 tests), TypeScript strict mode |

## Architecture

```
┌────────────────────────────────────────────────────────┐
│                  Docker container                      │
│                                                        │
│  ┌──────────────┐  ┌──────────────────────────────┐    │
│  │ APScheduler  │  │ FastAPI (uvicorn :8000)      │    │
│  │              │  │                              │    │
│  │ Daily 06:00  │──│  /api/v1/*     JSON API      │    │
│  │ OSINT /15min │  │  /api/health   Health check  │    │
│  └──────────────┘  │  /*            React SPA     │    │
│         │          └──────────────────────────────┘    │
│         │                        │                     │
│  ┌──────▼────────────────────────▼──────────────────┐  │
│  │              Pipeline (run_all.py)               │  │
│  │                                                  │  │
│  │  ServiceNow → Grafana → NetBox → OSINT → Report  │  │
│  └──────────────────────────────────────────────────┘  │
│         │                                              │
│  ┌──────▼───────────────────────────────────────────┐  │
│  │  data/                                           │  │
│  │  ├── processed/  Parquet files, risk scores      │  │
│  │  ├── reference/  Delegation registry, circuits   │  │
│  │  ├── reports/    HTML reports (timestamped)      │  │
│  │  └── henri.db    SQLite (scores, alerts, audit)  │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

For the detailed data architecture diagram, see [`documents/henri_architecture_diagram.svg`](documents/henri_architecture_diagram.svg).

The universal join key across all sources is **`location_site`** — the Prometheus label carried by every FortiGate target. It links to ServiceNow via assignment groups (`<CODE> ICT L2 SUPPORT`) and to NetBox via circuit CIDs (`<SITE>ISP<N>`).

## Quickstart

### Prerequisites

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- Node.js 22+ (for frontend build)
- Docker (for containerised deployment)

### Local development

```bash
# Clone and install
git clone <repo-url> && cd henri
cp .env.example .env
# Edit .env with your API credentials

# Install Python dependencies
uv sync

# Install frontend dependencies and build
cd frontend && npm ci && npm run build && cd ..

# Run the pipeline (generates reports from fixture data)
uv run python -m henri run_all --fixtures

# Start the web application
uv run uvicorn henri.web.app:app --reload --port 8000
# Open http://localhost:8000
```

### Frontend development (with hot reload)

```bash
# Terminal 1: API backend
uv run uvicorn henri.web.app:app --reload --port 8000

# Terminal 2: Vite dev server (proxies /api to backend)
cd frontend && npm run dev
# Open http://localhost:5173
```

## Deployment

### Docker Compose (laptop demo)

```bash
docker compose up --build
# HENRI available at http://localhost:8000
```

### OpenShift (production)

HENRI deploys via Azure Pipelines with Kustomize overlays:

```
.azure-pipelines/
├── build-and-push.yaml     # Multi-stage Docker build → Nexus registry
└── deploy-test.yaml        # Secrets + Kustomize apply + rollout

deploy/
├── base/                   # Deployment, Service, Route, PVC, Secret
└── overlays/test/          # Namespace + hostname override
```

**Required secrets** (Azure DevOps variable group `henri-secrets-test`):

| Variable | Description |
|----------|------------|
| `GRAFANA_URL` | Grafana instance URL |
| `GRAFANA_API_TOKEN` | Service account token (Viewer role) |
| `NETBOX_URL` | NetBox instance URL |
| `NETBOX_TOKEN` | NetBox API token |
| `ACLED_EMAIL` | ACLED registered email |
| `ACLED_PASSWORD` | ACLED API password |
| `CF_API_TOKEN` | Cloudflare Radar API token |

See `.env.example` for the full list including scheduler configuration.

## Dashboard

The dashboard is a bento-style dark interface built with ICRC brand colours (Graphite, Brick, Pomegranate). Key cards:

| Card | What it shows |
|------|--------------|
| **Alert summary** | Collapsible card with active precursor warnings — countries with conflict spikes, delegations at risk |
| **Threat landscape** | 51 field countries ranked by combined risk score, colour-coded rows, dot sparklines |
| **Stat cards** | Surges with precursors (118/218), detection rate (54%), average lead time (87h) |
| **Surge activity** | Weekly stacked bar chart — cyan for surges with precursors, grey for without |
| **Incident volume** | Dot histogram — monthly incidents by region, each dot ≈ 50 incidents |
| **Most alerting delegations** | Top 10 field sites by alert count (HQ filtered out) |
| **Bandwidth scorecard** | UC-1: over/under-utilised sites, utilisation % where NetBox commit_rate available |
| **Data coherence** | UC-3: NetBox coverage gaps, orphan codes, silent sites — progress bars |
| **Source health** | Live status of all 6 data feeds with record counts and freshness |

All numeric values animate with countUp.js odometer effects, triggered by IntersectionObserver when scrolled into view.

## Pages

| Page | Route | Content |
|------|-------|---------|
| **Dashboard** | `/` | Bento grid with all cards above |
| **Country** | `/country/:iso2` | ACLED daily bar chart, ServiceNow incidents by delegation, surge history with precursor badges |
| **Surges** | `/surges` | Interactive precursor analysis table — filterable by region, expandable rows, lead time colour coding |
| **Delegations** | `/delegations` | Searchable site inventory — circuits, sub-sites, incident counts |
| **Report** | `/report` | Static HTML report browser with iframe embed and download |

## Data sources

| Source | Auth | What HENRI extracts |
|--------|------|-------------------|
| **ServiceNow** | Playwright (session cookies) | 50,000+ incidents — parsed, classified (74% automated Prometheus alerts), enriched with delegation codes |
| **Grafana/Prometheus** | Bearer token | FortiGate site registry (322 sites), bandwidth per site (104 sites), uptime status |
| **NetBox** | Token | 46 sites, 64 circuits with ISP providers and committed rates |
| **ACLED** | OAuth (password grant, `client_id=acled`) | 62,000+ conflict events across 51 ICRC countries, 90-day rolling window |
| **IODA** | None | Internet outage alerts and summary scores per country |
| **Cloudflare Radar** | Bearer token | Verified outage annotations, BGP hijack and leak events |

## Testing

```bash
# Run all 336 tests
uv run pytest tests/

# Run specific test modules
uv run pytest tests/test_web_api.py              # FastAPI endpoints
uv run pytest tests/test_precursor.py            # Precursor analysis
uv run pytest tests/test_osint.py                # OSINT parsers
uv run pytest tests/test_prometheus_parser.py    # Hostname extraction

# Frontend type check
cd frontend && npx tsc --noEmit
```

## Known issues

- **Grafana query_range returns 302 on GET**: Workaround implemented — all PromQL queries use POST. The reverse proxy in front of Grafana rewrites long query strings. Retry logic (5 attempts × 180s) handles transient failures.
- **ACLED country name mismatches**: Ukraine shows 0 ACLED events — likely a country name mismatch. Côte d'Ivoire and Tajikistan also at zero. Investigate ACLED's exact country naming.
- **Bandwidth data sparse**: Only 5 sites showing bandwidth (BNG, MOG, MSC, MOS, HEB). The PromQL query may need adjustment for sites using different metric names.
- **UC-1 utilisation**: Only 3 of 103 field sites have both Grafana bandwidth AND NetBox commit_rate. Coverage improves as NetBox is populated.
- **ServiceNow**: Running on fixture data (50,000 incidents from Nov 2025 – Mar 2026) until the service account is provisioned.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

**Proprietary — ICRC Internal Use Only**

This software is developed for and owned by the International Committee of the Red Cross (ICRC). Unauthorised distribution, reproduction, or use outside ICRC is prohibited. Contact T&I Architecture for access and licensing enquiries.
