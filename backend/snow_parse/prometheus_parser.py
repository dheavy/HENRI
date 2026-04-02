"""Enrich Prometheus-automated tickets with hostname, delegation, and alert metadata."""

from __future__ import annotations

import logging
import re
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Known device-type suffixes (order matters — longer first)
_DEVICE_SUFFIXES = ("FGT", "SPM", "SWI", "RTR", "UPS", "FEM", "AP")

# Alert-name → category mapping
_ALERT_CATEGORIES: dict[str, str] = {
    # site_down
    "FortigateSiteDown": "site_down",
    "FemTargetDown": "site_down",
    "CollectorNodeDown": "site_down",
    "GvaFgtDown": "site_down",
    # wan_degraded
    "FortigateWanLatencyDeviation": "wan_degraded",
    "FortigateWanLatency": "wan_degraded",
    # voip_down
    "AudiocodesPingDown": "voip_down",
    # capacity
    "DhcpHighDHCPAddressUsageByScope": "capacity",
    # packet_loss
    "VmwareHostHighDroppedPacketsRx": "packet_loss",
    # latency
    "LdapBindLatencyCritical": "latency",
    "UrlHighHttpResponseTime": "latency",
    # wireless
    "FortigateApDown": "wireless",
    "HqFortigateApDown": "wireless",
    "HqWifiFortigateApDown": "wireless",
    # server
    "WindowsServerDown": "server",
    "WindowsServerCpuUsage": "server",
    "WindowsServerMemoryUsage": "server",
    "WindowsServerDiskSpaceUsage": "server",
    "LinuxTargetDown": "server",
    "LinuxHighCpuLoad90": "server",
    # storage
    "VmwareDatastoreUtilization": "storage",
    "VmwareDatastoreAccessibility": "storage",
    "HNASVolumeCapacityCritical": "storage",
    "LinuxOutOfDiskSpace": "storage",
    # backup
    "BackupHealthCritical": "backup",
    "BackupTooOld": "backup",
    # network_device
    "DockerTargetDown": "network_device",
    "UpsTargetDown": "network_device",
    "StarlinkStatusState": "network_device",
    "StarlinkStatusFractionObstructed": "network_device",
    # database
    "PostgresqlDown": "database",
    "MongodbDown": "database",
    "MssqlDeadlocks": "database",
    "MysqlSlaveIoThreadNotRunning": "database",
    # monitoring
    "PrometheusComponentDown": "monitoring",
    "PrometheusTargetEmpty": "monitoring",
}

_NETWORK_CATEGORIES = frozenset(
    {
        "site_down",
        "wan_degraded",
        "voip_down",
        "capacity",
        "packet_loss",
        "latency",
        "wireless",
        "network_device",
    }
)

# Regex: matches an IPv4 address
_IP_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")

# Regex: FQDN like gvacfsp2app03p.gva.icrc.priv (supports multi-level subdomains)
_FQDN_RE = re.compile(r"^[A-Za-z0-9.-]+\.([a-z]{3,})\.icrc\.priv$")

# Regex: hostname like ABED21.gva.icrc.priv → delegation = first 3 letters
# Pattern: <3-letter code><type char><digits>.<domain>.icrc.priv
_HOST_DOMAIN_RE = re.compile(r"^([A-Z]{3})[A-Z][A-Z0-9]*\.[a-z]+\.icrc\.priv$", re.IGNORECASE)


def _extract_delegation(hostname: str) -> Optional[str]:
    """Derive a delegation code from *hostname*."""
    hostname = hostname.strip()

    # IP address → unknown
    if _IP_RE.match(hostname):
        return None

    # Hostname.domain like ABED21.gva.icrc.priv → ABE (check before FQDN)
    # These start with an uppercase delegation code prefix
    m = _HOST_DOMAIN_RE.match(hostname)
    if m:
        return m.group(1).upper()

    # FQDN with domain segment (e.g. gvacfsp2app03p.gva.icrc.priv → gva)
    m = _FQDN_RE.match(hostname)
    if m:
        return m.group(1).upper()

    # Remove domain parts if present (not matching above patterns)
    bare = hostname.split(".")[0].strip()

    # Device-code pattern: ABEFGT, ABAM01FGT, LSHSPM01, ADOUPS01, etc.
    upper = bare.upper()
    for suffix in _DEVICE_SUFFIXES:
        # Match suffix possibly followed by trailing digits (e.g. SPM01, UPS02)
        m = re.match(rf"^([A-Z]{{2,5}})(?:\d{{0,2}}){suffix}\d*$", upper)
        if m:
            return m.group(1).upper()

    # "ABE Starlink 02" or "ABUK1 ISP1 STARLINK 01" → first word, strip digits
    parts = bare.split()
    if not parts:
        return None
    # Also handle underscore-separated: "ADE_Starlink_05"
    if "_" in bare and " " not in bare:
        parts = bare.split("_")
    if len(parts) > 1 and len(parts[0]) >= 2:
        code = re.sub(r"\d+$", "", parts[0]).upper()
        if code and code.isalpha():
            return code

    # Short all-alpha string (likely a code itself)
    if bare.isalpha() and 2 <= len(bare) <= 5:
        return bare.upper()

    return None


def _parse_description(desc: str) -> tuple[Optional[str], Optional[str]]:
    """Return (hostname, alert_name) from a Prometheus short_description."""
    # Expected: <prefix> Prometheus - <HOSTNAME> - <ALERT_NAME>
    prom_idx = desc.find("Prometheus")
    if prom_idx == -1:
        return None, None

    after_prom = desc[prom_idx + len("Prometheus") :]
    # Split on ' - '
    parts = [p.strip() for p in after_prom.split(" - ") if p.strip()]
    # parts[0] is usually empty (leading separator), so filter empties
    if len(parts) >= 2:
        hostname = parts[0] if parts[0] else parts[1] if len(parts) > 2 else None
        alert_name = parts[-1]
        return hostname, alert_name
    if len(parts) == 1:
        return None, parts[0]
    return None, None


def _categorise(alert_name: Optional[str]) -> str:
    """Map an alert name to a category."""
    if alert_name is None:
        return "other"
    return _ALERT_CATEGORIES.get(alert_name.strip(), "other")


def enrich_prometheus(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``hostname``, ``delegation_code``, ``alert_name``, ``alert_category``,
    and ``is_network_related`` columns to rows where ``is_prometheus`` is True.

    Non-Prometheus rows receive ``None`` / ``False`` for these columns.
    """
    hostnames: list[Optional[str]] = []
    delegations: list[Optional[str]] = []
    alert_names: list[Optional[str]] = []
    categories: list[str] = []
    network_flags: list[bool] = []

    for idx, row in df.iterrows():
        if not row.get("is_prometheus", False):
            hostnames.append(None)
            delegations.append(None)
            alert_names.append(None)
            categories.append("other")
            network_flags.append(False)
            continue

        desc = row.get("short_description", "")
        if not isinstance(desc, str):
            logger.warning("Row %s: short_description is not a string, skipping", idx)
            hostnames.append(None)
            delegations.append(None)
            alert_names.append(None)
            categories.append("other")
            network_flags.append(False)
            continue

        try:
            hostname, alert_name = _parse_description(desc)
        except Exception:
            logger.warning("Row %s: failed to parse description: %s", idx, desc)
            hostname, alert_name = None, None

        delegation = _extract_delegation(hostname) if hostname else None

        cat = _categorise(alert_name)

        hostnames.append(hostname)
        delegations.append(delegation)
        alert_names.append(alert_name)
        categories.append(cat)
        network_flags.append(cat in _NETWORK_CATEGORIES)

    df = df.copy()
    df["hostname"] = hostnames
    df["delegation_code"] = delegations
    df["alert_name"] = alert_names
    df["alert_category"] = categories
    df["is_network_related"] = network_flags

    return df
