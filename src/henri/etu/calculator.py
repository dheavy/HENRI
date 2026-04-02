"""
ETU (Effective Throughput per User) calculator.

Collapses bandwidth, latency, packet loss, jitter, availability,
user count, and link diversity into a single 0-100 score that answers:
"can staff at this site reliably work?"

Pure Python + math — no web dependencies.
"""

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

    missing: list[str] = []
    measured_count = 0
    total_fields = 0

    # ── Step 1: Effective throughput per link ──

    link_results: list[LinkETU] = []
    for link in links:
        # RTT
        total_fields += 1
        rtt_ms_val = link.get("measured_rtt_ms")
        if rtt_ms_val is not None:
            rtt_source = "measured"
            measured_count += 1
        else:
            lt = link.get("link_type", "")
            rtt_ms_val = RTT_DEFAULTS.get(lt, RTT_DEFAULT_UNKNOWN)
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
        rtt_sec = rtt_ms_val / 1000
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
            rtt_ms=rtt_ms_val,
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
    Log-scale mapping: 0.05 Mbps -> 0, 5 Mbps -> 100.

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
    if score >= 90:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 50:
        return "Adequate"
    if score >= 25:
        return "Degraded"
    return "Critical"
