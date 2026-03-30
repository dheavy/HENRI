"""Extract site codes from circuit CIDs and enrich with provider/commit_rate.

CID patterns:
- ``<SITE>ISP<N>``   — e.g. ADDISP4, ALJISP1, BUKISP5
- ``<RSITE>ISP<N>``  — e.g. RLUH4ISP03, RGOM01ISP4 (R/W prefix = sub-site)
- Free-form          — e.g. "002", "Castor ISP", "V0288948-3502"

commit_rate from NetBox is in **kbps** (NetBox default unit).
Values like 10000 = 10 Mbps, 1024000 = ~1 Gbps.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Extract site code before "ISP" (possibly with digits between code and ISP)
_CID_SITE_RE = re.compile(r"^([A-Z]{2,8}\d{0,3})ISP\d+$", re.IGNORECASE)


def _extract_site_from_cid(cid: str) -> str | None:
    """Extract the site code from a circuit CID.

    Examples::

        ADDISP4     → ADD
        RLUH4ISP03  → RLUH4  (sub-site, maps to parent via subsite_map)
        RGOM01ISP4  → RGOM01
        WJUB7ISP3   → WJUB7
        002         → None
        Castor ISP  → None
    """
    m = _CID_SITE_RE.match(cid.strip())
    if m:
        return m.group(1).upper()
    return None


def _format_rate(kbps: int | float | None) -> str:
    """Format a commit rate in kbps to a human-readable string."""
    if kbps is None or kbps <= 0:
        return "—"
    mbps = kbps / 1000
    if mbps >= 1000:
        return f"{mbps / 1000:.1f} Gbps"
    if mbps >= 1:
        return f"{mbps:.0f} Mbps"
    return f"{kbps:.0f} kbps"


def _detect_rate_unit(rates: list[int | float]) -> str:
    """Heuristic to detect whether commit_rate values are kbps or bps.

    NetBox default is kbps.  If median rate > 1_000_000 and we see
    values like 10_000_000_000 (10 Gbps in bps) then it's likely bps.
    For typical WAN circuits (1–500 Mbps), kbps values are 1_000–500_000.
    """
    if not rates:
        return "kbps"
    rates = sorted(rates)
    median = rates[len(rates) // 2]
    # In kbps: 10 Mbps = 10_000, 1 Gbps = 1_000_000
    # In bps:  10 Mbps = 10_000_000, 1 Gbps = 1_000_000_000
    if median > 5_000_000:
        # Likely bps — convert by dividing by 1000
        logger.info("commit_rate unit detected as bps (median=%d), converting to kbps", median)
        return "bps"
    return "kbps"


def enrich_circuits(
    circuits: list[dict],
    subsite_map: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Parse circuits into enriched records with site code, provider, rate.

    Parameters
    ----------
    circuits : list[dict]
        Raw NetBox circuit records (from API or fixture).
    subsite_map : dict
        Optional mapping ``{sub_site: parent_code}`` to resolve sub-site
        codes extracted from CIDs to their parent delegation.

    Returns
    -------
    list[dict]
        Enriched circuit records.
    """
    if subsite_map is None:
        subsite_map = {}

    # Detect unit
    raw_rates = [c.get("commit_rate") for c in circuits if c.get("commit_rate")]
    unit = _detect_rate_unit(raw_rates)
    rate_divisor = 1000 if unit == "bps" else 1

    enriched: list[dict[str, Any]] = []
    for circ in circuits:
        cid = circ.get("cid", "")
        site_code = _extract_site_from_cid(cid)
        parent_code = subsite_map.get(site_code, site_code) if site_code else None

        provider_obj = circ.get("provider") or {}
        provider_name = provider_obj.get("name", "") if isinstance(provider_obj, dict) else str(provider_obj)

        type_obj = circ.get("type") or {}
        circuit_type = type_obj.get("value", "") if isinstance(type_obj, dict) else ""

        raw_rate = circ.get("commit_rate")
        commit_rate_kbps = int(raw_rate / rate_divisor) if raw_rate else None

        tenant_obj = circ.get("tenant") or {}
        tenant = tenant_obj.get("name", "") if isinstance(tenant_obj, dict) else ""

        status_obj = circ.get("status") or {}
        status = status_obj.get("value", "") if isinstance(status_obj, dict) else ""

        enriched.append({
            "cid": cid,
            "site_code": site_code,
            "parent_code": parent_code,
            "provider": provider_name,
            "circuit_type": circuit_type,
            "commit_rate_kbps": commit_rate_kbps,
            "commit_rate_fmt": _format_rate(commit_rate_kbps),
            "tenant": tenant,
            "status": status,
            "description": circ.get("description", ""),
        })

    with_site = sum(1 for e in enriched if e["site_code"])
    with_rate = sum(1 for e in enriched if e["commit_rate_kbps"])
    logger.info(
        "Enriched %d circuits: %d with site code, %d with commit_rate",
        len(enriched), with_site, with_rate,
    )
    return enriched


def load_circuits_from_fixture(fixture_path: Path) -> list[dict]:
    """Load NetBox circuits from a saved fixture file."""
    with open(fixture_path) as f:
        data = json.load(f)
    return data.get("results", [])
