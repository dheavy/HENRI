# ETU — Effective Throughput per User

## What this is

A new metric and a new page in the HENRI web app that computes a 
per-site connectivity quality score called **ETU (Effective Throughput 
per User)**. It collapses bandwidth, latency, packet loss, jitter, 
availability, user count, and link diversity into a single number 
that answers: "can staff at this site reliably work?"

This goes in a new page at `/connectivity` with its own nav icon 
(Lucide: `Wifi`), a new API endpoint, and a new backend module. 
Keep it fully isolated from existing pages — no changes to 
Dashboard, Country, Surges, Delegations, or Report.

---

## Backend

### New module: `src/henri/etu/`

Create `src/henri/etu/__init__.py` and `src/henri/etu/calculator.py`.

#### `calculator.py` — the ETU algorithm

```python
import math
from dataclasses import dataclass, field


# ── Constants ──

MSS = 1460            # TCP max segment size (bytes)
MATHIS_C = 1.22       # Mathis formula constant
JITTER_FLOOR = 30     # ms — below this, no penalty
JITTER_CEIL = 200     # ms — above this, max penalty
MIN_USERS = 5         # floor to avoid division by tiny numbers
REDUNDANCY_WEIGHT = 0.3  # backup link contribution weight


# ── RTT defaults by link type (ms) ──
# Used when no measurement is available

RTT_DEFAULTS = {
    "Internet-VSAT": 620,       # GEO satellite
    "Internet-Starlink": 45,    # LEO constellation
    "Internet-Fiber": 15,       # terrestrial fiber
    "Internet-4G": 40,          # mobile broadband
    "Internet-Microwave": 8,    # point-to-point
    "Internet-DSL": 25,         # copper last-mile
}
RTT_DEFAULT_UNKNOWN = 80        # conservative fallback


@dataclass
class LinkETU:
    cid: str
    link_type: str | None
    provider: str | None
    effective_bps: float
    mathis_bps: float
    capacity_bps: float | None
    rtt_ms: float
    rtt_source: str             # "measured" or "estimated"
    loss: float
    loss_source: str            # "measured" or "default"
    is_primary: bool


@dataclass
class ETUResult:
    site_code: str
    score: int                  # 0-100
    grade: str                  # Excellent/Good/Adequate/Degraded/Critical
    etu_mbps: float             # final ETU per user after penalties
    etu_raw_mbps: float         # before penalties
    num_users: int
    num_users_source: str       # "dhcp" or "default"
    num_links: int
    aggregate_bps: float
    jitter_ms: float | None
    jitter_penalty: float
    availability_ratio: float | None
    availability_penalty: float
    diversity_bonus: float
    links: list[LinkETU]
    missing_data: list[str]     # what's not measured
    data_completeness: float    # 0.0-1.0 — how much we're guessing


def compute_etu(
    site_code: str,
    links: list[dict],          # from NetBox + Grafana join
    dhcp_lease_count: int | None,
    jitter_ms: float | None,
    availability_ratio: float | None,
) -> ETUResult:
    """
    Compute ETU for a single site.
    
    Each link dict should have:
    - cid: str
    - link_type: str | None (NetBox circuit type)
    - provider: str | None
    - committed_rate_kbps: int | None (NetBox)
    - measured_peak_bps: float | None (Grafana)
    - measured_rtt_ms: float | None (Grafana blackbox/SNMP)
    - packet_loss_ratio: float | None (Grafana, 0.0-1.0)
    - is_primary: bool
    """
    
    missing = []
    measured_count = 0
    total_fields = 0
    
    # ── Step 1: Effective throughput per link ──
    
    link_results = []
    for link in links:
        # RTT
        total_fields += 1
        rtt_ms = link.get("measured_rtt_ms")
        if rtt_ms is not None:
            rtt_source = "measured"
            measured_count += 1
        else:
            lt = link.get("link_type", "")
            rtt_ms = RTT_DEFAULTS.get(lt, RTT_DEFAULT_UNKNOWN)
            rtt_source = "estimated"
            missing.append(f"rtt:{link.get('cid', '?')}")
        
        # Packet loss
        total_fields += 1
        loss = link.get("packet_loss_ratio")
        if loss is not None:
            loss_source = "measured"
            measured_count += 1
        else:
            loss = 0.01  # conservative 1% default
            loss_source = "default"
            missing.append(f"loss:{link.get('cid', '?')}")
        
        # Capacity
        total_fields += 1
        committed_kbps = link.get("committed_rate_kbps")
        measured_peak = link.get("measured_peak_bps")
        if committed_kbps:
            measured_count += 1
        elif measured_peak:
            measured_count += 1
        else:
            missing.append(f"capacity:{link.get('cid', '?')}")
        
        # Mathis formula
        loss_floor = max(loss, 0.0001)
        rtt_sec = rtt_ms / 1000
        mathis_bps = (MSS / rtt_sec) * (MATHIS_C / math.sqrt(loss_floor)) * 8
        
        # Cap at known capacity
        capacity_bps = None
        if committed_kbps:
            capacity_bps = committed_kbps * 1000
        elif measured_peak:
            capacity_bps = measured_peak
        
        cap = capacity_bps or mathis_bps
        effective_bps = min(mathis_bps, cap)
        
        link_results.append(LinkETU(
            cid=link.get("cid", "unknown"),
            link_type=link.get("link_type"),
            provider=link.get("provider"),
            effective_bps=effective_bps,
            mathis_bps=mathis_bps,
            capacity_bps=capacity_bps,
            rtt_ms=rtt_ms,
            rtt_source=rtt_source,
            loss=loss,
            loss_source=loss_source,
            is_primary=link.get("is_primary", True),
        ))
    
    # ── Step 2: Aggregate links ──
    
    if not link_results:
        return ETUResult(
            site_code=site_code, score=0, grade="No data",
            etu_mbps=0, etu_raw_mbps=0, num_users=0,
            num_users_source="none", num_links=0,
            aggregate_bps=0, jitter_ms=None, jitter_penalty=1.0,
            availability_ratio=None, availability_penalty=1.0,
            diversity_bonus=1.0, links=[], missing_data=["all"],
            data_completeness=0.0,
        )
    
    primaries = [l for l in link_results if l.is_primary]
    secondaries = [l for l in link_results if not l.is_primary]
    
    # If no link is marked primary, treat all as primary
    if not primaries:
        primaries = link_results
        secondaries = []
    
    aggregate_bps = (
        sum(l.effective_bps for l in primaries)
        + sum(l.effective_bps * REDUNDANCY_WEIGHT for l in secondaries)
    )
    
    # ── Step 3: Per-user throughput ──
    
    total_fields += 1  # user count
    if dhcp_lease_count is not None and dhcp_lease_count >= MIN_USERS:
        num_users = dhcp_lease_count
        num_users_source = "dhcp"
        measured_count += 1
    else:
        num_users = MIN_USERS
        num_users_source = "default"
        missing.append("user_count")
    
    etu_raw_bps = aggregate_bps / num_users
    etu_raw_mbps = etu_raw_bps / 1_000_000
    
    # ── Step 4: Quality penalties ──
    
    # Jitter
    total_fields += 1
    if jitter_ms is not None:
        jitter_penalty = max(0.0, min(1.0,
            1.0 - (jitter_ms - JITTER_FLOOR) / (JITTER_CEIL - JITTER_FLOOR)
        ))
        measured_count += 1
    else:
        jitter_penalty = 1.0
        missing.append("jitter")
    
    # Availability
    total_fields += 1
    if availability_ratio is not None:
        availability_penalty = availability_ratio ** 2
        measured_count += 1
    else:
        availability_penalty = 1.0
        missing.append("availability")
    
    # Link diversity bonus
    unique_providers = len(set(
        l.provider for l in link_results if l.provider
    ))
    diversity_bonus = 1.0 + (0.05 * max(0, unique_providers - 1))
    
    # ── Step 5: Final ETU ──
    
    etu_final_mbps = etu_raw_mbps * jitter_penalty * availability_penalty * diversity_bonus
    
    # ── Step 6: Score ──
    
    score = _mbps_to_score(etu_final_mbps)
    grade = _score_to_grade(score)
    
    # Data completeness
    completeness = measured_count / total_fields if total_fields > 0 else 0.0
    
    return ETUResult(
        site_code=site_code,
        score=score,
        grade=grade,
        etu_mbps=etu_final_mbps,
        etu_raw_mbps=etu_raw_mbps,
        num_users=num_users,
        num_users_source=num_users_source,
        num_links=len(link_results),
        aggregate_bps=aggregate_bps,
        jitter_ms=jitter_ms,
        jitter_penalty=jitter_penalty,
        availability_ratio=availability_ratio,
        availability_penalty=availability_penalty,
        diversity_bonus=diversity_bonus,
        links=link_results,
        missing_data=missing,
        data_completeness=completeness,
    )


def _mbps_to_score(mbps: float) -> int:
    """
    Log-scale mapping: 0.05 Mbps → 0, 5 Mbps → 100.
    
    Logarithmic because the jump from 50kbps to 500kbps
    matters far more than 5Mbps to 50Mbps.
    """
    if mbps <= 0:
        return 0
    log_score = (
        (math.log10(mbps) - math.log10(0.05))
        / (math.log10(5) - math.log10(0.05))
    )
    return max(0, min(100, int(log_score * 100)))


def _score_to_grade(score: int) -> str:
    if score >= 90: return "Excellent"
    if score >= 70: return "Good"
    if score >= 50: return "Adequate"
    if score >= 25: return "Degraded"
    return "Critical"
```

### New API endpoint: `src/henri/web/api/connectivity.py`

```
GET /api/v1/connectivity
```

Returns:
```json
{
  "sites": [
    {
      "site_code": "JUB",
      "country": "South Sudan",
      "region": "AFRICA East",
      "score": 52,
      "grade": "Adequate",
      "etu_mbps": 0.14,
      "etu_raw_mbps": 0.18,
      "num_users": 80,
      "num_users_source": "dhcp",
      "num_links": 2,
      "jitter_penalty": 1.0,
      "availability_penalty": 0.96,
      "diversity_bonus": 1.05,
      "data_completeness": 0.85,
      "missing_data": ["jitter"],
      "links": [
        {
          "cid": "JUBISP1",
          "link_type": "Internet-Fiber",
          "provider": "MTN",
          "effective_mbps": 8.2,
          "rtt_ms": 25,
          "rtt_source": "measured",
          "loss": 0.005,
          "loss_source": "measured",
          "is_primary": true
        }
      ]
    }
  ],
  "summary": {
    "total_sites": 110,
    "scored_sites": 16,
    "by_grade": {
      "Excellent": 0,
      "Good": 3,
      "Adequate": 8,
      "Degraded": 4,
      "Critical": 1
    },
    "avg_completeness": 0.62
  },
  "coverage": {
    "has_bandwidth": 85,
    "has_circuits": 31,
    "has_rtt": 12,
    "has_loss": 12,
    "has_jitter": 0,
    "has_dhcp": 8,
    "has_availability": 85,
    "full_data": 5
  }
}
```

**How to build the input data:**

For each site in the delegation registry:

1. Look up NetBox circuits by CID pattern (`{SITE}ISP{N}`). 
   Get: circuit type, provider, commit_rate.

2. Look up Grafana bandwidth data from `bandwidth_by_site.parquet`.
   Get: measured peak throughput.

3. If blackbox exporter data is available for this site, get RTT and 
   loss. This is the metric we may NOT have yet — check what 
   Prometheus jobs exist. If not available, use `estimate_rtt()` 
   from the link type and flag it as missing.

4. DHCP lease count: check if `DhcpHighDHCPAddressUsageByScope` 
   alerts exist for this site in the ServiceNow data. The alert 
   description sometimes includes the scope size. If not available 
   from Prometheus directly, estimate from incident volume as a 
   rough proxy (more tickets ≈ more users) — but flag it.

5. Availability: compute from `probe_success` if available, or 
   from FortigateSiteDown events (uptime = 1 - downtime_hours/total_hours).

6. Jitter: we likely don't have this metric yet. Flag it as missing 
   for all sites. It becomes available when we get blackbox exporter 
   access.

Wire this into the existing router at `src/henri/web/api/router.py`.

---

## Frontend

### New page: `/connectivity`

Add to the React router and sidebar nav (Lucide `Wifi` icon).

**Page layout — two zones:**

#### Zone 1: Scored sites (top)

A table of all sites where ETU could be computed (even partially):

```
CONNECTIVITY QUALITY — EFFECTIVE THROUGHPUT PER USER
Sites ranked by user experience score — lower scores need attention first

┌─────┬──────────┬──────┬──────────┬──────────┬───────┬───────┬──────────┬──────────────┐
│ #   │ Site     │Score │ Grade    │ ETU/user │ Users │ Links │ Limiting │ Completeness │
│     │          │      │          │          │       │       │ factor   │              │
├─────┼──────────┼──────┼──────────┼──────────┼───────┼───────┼──────────┼──────────────┤
│  1  │ MOG      │  18  │ Critical │ 0.02 Mbps│   25  │   1   │ Latency  │ ████░░░ 62%  │
│  2  │ BUK      │  34  │ Degraded │ 0.06 Mbps│   15  │   1   │ Loss     │ █████░░ 71%  │
│  3  │ JUB      │  52  │ Adequate │ 0.14 Mbps│   80  │   2   │ Users    │ ██████░ 85%  │
│  4  │ KYI      │  83  │ Good     │ 1.30 Mbps│   45  │   2   │ —        │ ███████ 100% │
└─────┴──────────┴──────┴──────────┴──────────┴───────┴───────┴──────────┴──────────────┘
```

- Sort by score ascending (worst first — these need attention)
- Score column: color-coded by grade (use existing risk tier colors)
- Grade column: text badge with grade color
- "Limiting factor": identify which component is dragging the score 
  down the most. Logic: compare each penalty/factor to see which 
  reduces the score the most from its theoretical maximum:
  - If Mathis throughput << capacity → "Latency" or "Loss"
  - If availability_penalty < 0.9 → "Availability"
  - If jitter_penalty < 0.8 → "Jitter"
  - If etu_raw is high but etu_final is low → whichever penalty is lowest
  - If etu_raw is already low → "Users" (too many) or "Bandwidth" (not enough)
  - If nothing is limiting → "—"
- Completeness column: mini progress bar showing data_completeness
- Click a row → expand to show link-by-link breakdown:
  CID, type, provider, RTT (with source tag), loss (with source tag), 
  Mathis vs capacity, effective throughput. Highlight estimated values 
  in a different color (--text-muted italic) vs measured values 
  (--text-primary).

#### Zone 2: Data coverage (bottom)

This is equally important — it shows what's missing across ALL sites 
and helps prioritize data collection.

```
DATA COVERAGE — WHAT'S NEEDED FOR FULL ETU SCORING
Metrics available across 110 field sites

Bandwidth (Grafana)     ████████████████████████████████████░░░░░░░  85 / 110
Link availability       ████████████████████████████████████░░░░░░░  85 / 110
Circuits (NetBox)       ████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  31 / 110
RTT / latency           ████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  12 / 110  ← biggest gap
Packet loss             ████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  12 / 110
DHCP user count         █████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   8 / 110
Jitter                  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   0 / 110  ← no data
Full ETU (all metrics)  ███░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░   5 / 110
```

- Horizontal bar chart (Recharts BarChart, horizontal)
- Each bar: filled portion in --green, empty in --bg-elevated
- Count label on the right: "85 / 110"
- Title: "Data coverage — what's needed for full ETU scoring"
- One-liner: "Metrics available across 110 field sites — 
  gaps indicate missing Prometheus exporters or NetBox records"

Below the bars, add a text block:

```
To improve coverage:
• RTT + loss: requires blackbox exporter or SNMP latency metrics 
  in Prometheus for each site
• DHCP: requires DhcpHighDHCPAddressUsageByScope alert or a 
  DHCP scope size metric in Prometheus
• Jitter: requires probe_duration_seconds stddev calculation — 
  available once blackbox exporter access is confirmed
• Circuits: 79 sites missing from NetBox — populate via 
  /api/dcim/sites/ and /api/circuits/circuits/
```

This makes the coverage gaps actionable — it tells the 
infrastructure team exactly what to configure to get better 
scoring.

---

## Styling

Use the existing HENRI design system (DM Sans, DM Mono, dark palette).

This is NOT a dashboard page — it's a functional/analytical page like 
Delegations or Surges. Clean table layout, no bespoke visualisations. 
Standard Recharts for the coverage bars.

Score color mapping (reuse risk tier colors):
- 90-100 Excellent: --green (#A8C97A)
- 70-89 Good: --green
- 50-69 Adequate: --yellow (#E5C46B)
- 25-49 Degraded: --orange (#D88A6C)
- 0-24 Critical: --red (#D83C3B)

Completeness bar: filled in --green, background --bg-elevated.
Estimated values in expanded rows: italic, --text-muted, with a 
small "est." tag.

---

## Tests

Write comprehensive tests for the ETU calculator:

1. A site with perfect data → score near 100
2. A site with GEO VSAT only, high loss → score < 30
3. A site with Starlink vs GEO VSAT at same bandwidth → 
   Starlink scores much higher
4. Jitter penalty: 0ms → no penalty, 200ms → max penalty
5. Availability: 100% → no penalty, 90% → 81% penalty (squared)
6. Diversity bonus: 1 provider → 1.0, 3 providers → 1.1
7. Missing data: all estimated → completeness near 0
8. Zero links → score 0, grade "No data"
9. User count floor: 2 DHCP leases → uses MIN_USERS (5)
10. Log score mapping: 0.05 Mbps → 0, 5 Mbps → 100, 
    0.5 Mbps → ~50

---

## Constraints

- No changes to existing pages or components
- New files only: `src/henri/etu/`, `src/henri/web/api/connectivity.py`, 
  `frontend/src/pages/Connectivity.tsx`
- The algorithm module (`etu/calculator.py`) must have zero web 
  dependencies — pure Python + math. This keeps it testable and 
  reusable outside the web app.
- Handle partial data gracefully everywhere. A site with only 
  bandwidth data should still appear in the table with a low 
  completeness score, not be silently excluded.
- Feature branch: `feature/etu-connectivity`
