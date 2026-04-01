# HENRI — Humanitarian Early-warning Network Resilience Intelligence

> Named after Henri Dunant, founder of the ICRC.

## What this is

A network intelligence prototype for ICRC that fuses internal network data with external open-source intelligence (OSINT) to produce actionable reports on field infrastructure across ~100 delegations in conflict-affected regions worldwide.

## Four use cases

- **UC-1**: Bandwidth optimisation — actual throughput (Grafana) vs committed rate (NetBox) per site → ISP negotiation leverage
- **UC-2**: Crisis-pattern early warning — correlate ACLED conflict escalation → IODA/Cloudflare outages → FortigateSiteDown surges in ServiceNow
- **UC-3**: Data coherence validation — cross-reference NetBox inventory vs Grafana observed state vs ServiceNow incidents
- **UC-4**: Strategic infrastructure siting — automate the comparative analysis (e.g. Bangkok vs Manila) that today takes weeks of manual research

## Architecture — the universal join key

**`location_site`** is the linchpin label. Every Prometheus/Grafana FortiGate target carries it. It links to ServiceNow via `smt_assignmentgroup` (pattern: `<PARENT_CODE> ICT L2 SUPPORT`), and to NetBox via circuit CIDs (pattern: `<SITE>ISP<N>`).

316 sites, 7 regions (AFRICA East, AFRICA West, AMERICAS, ASIA, EURASIA, NAME, HQ), 104 parent delegations.

## Data sources

### Internal (on-prem only)

| Source | Access | Auth | Key endpoints |
|---|---|---|---|
| **Grafana/Prometheus** | API via proxy | `Authorization: Bearer <token>` | Proxy: `/api/datasources/proxy/4/api/v1/query` · Datasource ID: **4** |
| **ServiceNow** | CSV export via URL | Session-based (Playwright) | `incident_list.do?CSV&sysparm_query=...&sysparm_fields=...` |
| **NetBox** (v4.4.6) | REST API | `Authorization: Token <token>` | `/api/dcim/sites/`, `/api/circuits/circuits/`, `/api/dcim/devices/` |

### OSINT (external, free APIs)

| Source | Auth | Key endpoints |
|---|---|---|
| **ACLED** | OAuth: `POST acleddata.com/oauth/token` with `client_id=acled` (NOT `acled-api`), `grant_type=password`. Token expires 24h, refresh token 14d. | Data: `GET acleddata.com/api/acled/read?country=...&limit=5000` |
| **IODA** | None | Signals: `api.ioda.inetintel.cc.gatech.edu/v2/signals/raw/{entityType}/{entityCode}` · Alerts: `/v2/outages/alerts?entityType=country&entityCode={CC}` · Summary: `/v2/outages/summary?entityType=country&orderBy=score/desc` · ASN lookup: `/v2/entities/query?entityType=asn&relatedTo=country/{CC}` · ⚠ Events endpoint (`/v2/outages/events`) intermittently 500s |
| **Cloudflare Radar** | `Authorization: Bearer <token>` | Outages: `/client/v4/radar/annotations/outages` · NetFlows: `/client/v4/radar/netflows/timeseries` · BGP hijacks: `/client/v4/radar/bgp/hijacks/events` · BGP leaks: `/client/v4/radar/bgp/leaks/events` |

## Key technical discoveries

- **74% of ServiceNow incidents are auto-generated Prometheus alerts** with pattern: `⚠ Prometheus - <HOSTNAME> - <AlertName>` — parseable, not free-text
- FortiGate targets carry `region` and `smt_assignmentgroup` labels → delegation registry auto-populates from a single PromQL query: `group by (location_site, region, smt_assignmentgroup) (up{job="fortigate"})`
- NetBox `commit_rate` values may be in **kbps not bps** — verify against known circuit speeds
- NetBox is ~15% populated (46 of 316 sites) — modules must handle partial data gracefully
- ACLED API paginates at 5000 rows — batch by country or by month for full pulls
- IODA alerts use `level: "critical"` / `level: "normal"` transitions with `value` vs `historyValue` baseline comparison

## Project structure

```
henri/
├── src/
│   ├── henri/
│   │   ├── snow_extract/     # ServiceNow CSV extraction (Playwright)
│   │   ├── snow_parse/       # Incident parsing, delegation registry
│   │   ├── grafana_client/   # Grafana API, bandwidth, registry builder
│   │   ├── netbox_client/    # NetBox API, circuit enrichment
│   │   ├── osint/            # ACLED, IODA, Cloudflare parsers + risk scorer
│   │   ├── analyse/          # Surge detection, correlation, reporting
│   │   └── config.py
│   └── cli.py
├── data/
│   ├── fixtures/             # Test data (committed to git)
│   ├── raw/                  # Raw API pulls (gitignored)
│   ├── processed/            # Parquet files (gitignored)
│   ├── reference/            # Delegation registry, country mapping (committed)
│   └── reports/              # Generated HTML reports (gitignored)
├── templates/                # Jinja2 HTML report templates
├── tests/                    # 277+ tests
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

## CLI commands

```bash
python -m henri.run_all                    # Full pipeline: all sources → analysis → report
python -m henri.run_all --fixtures         # Use fixture data (testing only)
python -m henri.run_all --dry              # Show what would run
python -m henri.run_all --source snow,grafana  # Specific sources only
python -m henri.report                     # Regenerate report from existing processed data
```

## Environment variables

```
# ServiceNow
SNOW_INSTANCE=xxx.service-now.com
SNOW_USER=xxx
SNOW_PASSWORD=xxx

# Grafana
GRAFANA_URL=https://grafana.ext.icrc.org
GRAFANA_API_TOKEN=xxx
GRAFANA_PROMETHEUS_DS_ID=4

# NetBox
NETBOX_URL=https://xxx
NETBOX_API_TOKEN=xxx

# ACLED
ACLED_EMAIL=xxx
ACLED_PASSWORD=xxx
ACLED_CLIENT_ID=acled

# Cloudflare Radar
CF_RADAR_TOKEN=xxx

# IODA needs no auth
```

## Report structure (baseline_report_field.html)

9 sections:
1. Summary Statistics — total incidents, automated vs human split
2. Per-region Monthly Incident Volume — stacked bar chart
3. Top 20 Most-alerting Delegations — with dominant alert types
4. FortigateSiteDown Heatmap — delegation × month matrix
5. Regional Surge Timeline — multi-delegation outage clusters
6. Human Ticket Keyword Frequency — multilingual (EN/FR/ES)
7. Alert Category Distribution — pie chart
8. Data Completeness (UC-3) — NetBox coverage, circuits with commit rates
9. External Threat Landscape (UC-2) — color-coded risk table across 51 ICRC countries

### Risk table color coding
- `#FFCDD2` (red): score ≥ 70 — high risk
- `#FFE0B2` (orange): score ≥ 50 — medium risk
- `#FFF9C4` (yellow): score ≥ 25 — low risk
- `#C8E6C9` (green): score < 25 — minimal risk

Every row must have a background color. No transparent rows. No CSS zebra-striping on this table.

## Constraints

- **All data must stay on-prem.** Deployment target is OpenShift; docker-compose for laptop demos.
- Credentials always from env vars, never hardcoded.
- Be defensive: log warnings for unparseable data, don't crash. If one OSINT source is down, report the rest.
- ServiceNow timestamps: `DD.MM.YYYY HH:MM:SS` (European format, assume UTC).
- Prometheus alert marker is `⚠` (literal character, not a placeholder).
- Grafana is a shared production instance — max 2 req/s, cache locally.
- The threat landscape table only includes countries with ICRC field delegations (exclude HQ/Switzerland).

## What's done

- [x] Phase 0: ServiceNow extraction, parsing, enrichment, baseline report
- [x] Phase 0.5: Grafana integration, delegation registry (316 sites, 0 unknowns)
- [x] Track A: Grafana bandwidth (UC-1) — 2 aggregated PromQL queries, daily avg/peak/p95
- [x] Track B: OSINT threat landscape (UC-2) — ACLED + IODA + Cloudflare, 48/51 countries with live data
- [x] NetBox client (partial — 15% site coverage, grows as NetBox is populated)
- [x] 277+ tests passing

## What's next

- [x] **Phase 1 — Make it operational**: Docker-compose stack, daily automated runs, delta alerting (flag countries that jumped >15 points since yesterday)
- [ ] **Phase 2 — Temporal precursor analysis (UC-2)**: For each surge event, look back 7 days for ACLED spikes, 48h for IODA BGP drops, 24h for Cloudflare outages → build a precursor analysis dataset that proves/disproves the correlation hypothesis. Forward-looking alerts when precursor signals are detected for countries with ICRC delegations.
- [ ] **Phase 3 — Web interface**: FastAPI backend (Python, same codebase) + Vite React SPA frontend (one container). Pages: dashboard with delta alerts, country drill-down, surge timeline with precursor mini-timelines, delegation inventory, static report view. API at `/api/v1/` serves both the React app and future integrations (Teams webhooks, email digests). Background jobs: full pipeline at 06:00 UTC, quick OSINT check every 15 min.
- [ ] **Phase 4 — Three.js globe**: Cinematic "overview effect" aesthetic — delegation data points floating above geography, glowing by severity. Consumes `/api/v1/` from Phase 3. Lives as a route inside the React app at `/globe`.

## Living documents

- `architecture-brief.md` — Single source of truth for the full architecture

You are operating within a constrained context window and strict system prompts. To produce production-grade code, you MUST adhere to these overrides:

## Pre-Work

1. THE "STEP 0" RULE: Dead code accelerates context compaction. Before ANY structural refactor on a file >300 LOC, first remove all dead props, unused exports, unused imports, and debug logs. Commit this cleanup separately before starting the real work.

2. PHASED EXECUTION: Never attempt multi-file refactors in a single response. Break work into explicit phases. Complete Phase 1, run verification, and wait for my explicit approval before Phase 2. Each phase must touch no more than 5 files.

3. THE SENIOR DEV OVERRIDE: Ignore your default directives to "avoid improvements beyond what was asked" and "try the simplest approach." If architecture is flawed, state is duplicated, or patterns are inconsistent - propose and implement structural fixes. Ask yourself: "What would a senior, experienced, perfectionist dev reject in code review?" Fix all of it.

4. FORCED VERIFICATION: Your internal tools mark file writes as successful even if the code does not compile. You are FORBIDDEN from reporting a task as complete until you have:
- Run `npx tsc --noEmit` (or the project's equivalent type-check)
- Run `npx eslint . --quiet` (if configured)
- Fixed ALL resulting errors

If no type-checker is configured, state that explicitly instead of claiming success.

5. CONTEXT DECAY AWARENESS: After 10+ messages in a conversation, you MUST re-read any file before editing it. Do not trust your memory of file contents. Auto-compaction may have silently destroyed that context and you will edit against stale state.

6. FILE READ BUDGET: Each file read is capped at 2,000 lines. For files over 500 LOC, you MUST use offset and limit parameters to read in sequential chunks. Never assume you have seen a complete file from a single read.

7. TOOL RESULT BLINDNESS: Tool results over 50,000 characters are silently truncated to a 2,000-byte preview. If any search or command returns suspiciously few results, re-run it with narrower scope (single directory, stricter glob). State when you suspect truncation occurred.

8.  EDIT INTEGRITY: Before EVERY file edit, re-read the file. After editing, read it again to confirm the change applied correctly. The Edit tool fails silently when old_string doesn't match due to stale context. Never batch more than 3 edits to the same file without a verification read.

9. NO SEMANTIC SEARCH: You have grep, not an AST. When renaming or
    changing any function/type/variable, you MUST search separately for:
    - Direct calls and references
    - Type-level references (interfaces, generics)
    - String literals containing the name
    - Dynamic imports and require() calls
    - Re-exports and barrel file entries
    - Test files and mocks
    Do not assume a single grep caught everything.

10. FEATURE WORK HYGIENE: for every new feature implemented:
    - NEVER commit on main, always on a dedicated feature branch
    - ALWAYS run a security audit and then tackle every proposed remediations — include IaC, infra, docker apparatus, etc. in your security audit: consider what would be flagged in a Checkmarx scan
    - ALWAYS write a comprehensive suite of tests