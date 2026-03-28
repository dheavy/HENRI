"""Tests for snow_parse.prometheus_parser — hostname extraction and alert categorisation."""

import pandas as pd
import pytest

from snow_parse.prometheus_parser import _extract_delegation, _parse_description, _categorise, enrich_prometheus


# ── Delegation code extraction ────────────────────────────────────────

class TestExtractDelegation:
    """Test hostname → delegation code mapping."""

    # Device-code hostnames (CODE + suffix)
    @pytest.mark.parametrize("hostname, expected", [
        ("ABEFGT", "ABE"),
        ("KADFGT", "KAD"),
        ("JUBSPM", "JUB"),
        ("LSHSPM01", "LSH"),       # suffix + trailing digits
        ("ABAM01FGT", "ABAM"),     # digits before suffix
        ("ABUK1FGT", "ABUK"),      # digit in code area before suffix
        ("ABUK2FGT", "ABUK"),
        ("ADESPM01", "ADE"),       # SPM + trailing digits
        ("ALCFEM01", "ALC"),       # FEM not in suffix list → other pattern
        ("ADOUPS01", "ADO"),       # UPS + trailing digits
        ("ALCUPS02", "ALC"),
    ])
    def test_device_code_hostnames(self, hostname: str, expected: str):
        assert _extract_delegation(hostname) == expected

    # FQDN hostnames (subdomain.site.icrc.priv)
    @pytest.mark.parametrize("hostname, expected", [
        ("gvacfsp2app03p.gva.icrc.priv", "GVA"),
        ("gvaipamapp03p.gva.icrc.priv", "GVA"),
        ("esx-vsan-b2-wit.gva.icrc.priv", "GVA"),
        ("admin.hcp2.gva.icrc.priv", "GVA"),  # deeper nesting
    ])
    def test_fqdn_hostnames(self, hostname: str, expected: str):
        assert _extract_delegation(hostname) == expected

    # Domain-host hostnames (CODEX99.site.icrc.priv)
    @pytest.mark.parametrize("hostname, expected", [
        ("ABED21.gva.icrc.priv", "ABE"),
        ("ABED41.gva.icrc.priv", "ABE"),
        ("OUGA21.gva.icrc.priv", "OUG"),
        ("EREA21.gva.icrc.priv", "ERE"),
    ])
    def test_domain_host_hostnames(self, hostname: str, expected: str):
        assert _extract_delegation(hostname) == expected

    # Starlink hostnames
    @pytest.mark.parametrize("hostname, expected", [
        ("ABE Starlink 02", "ABE"),
        ("ABJ Starlink", "ABJ"),
        ("ADE Starlink 05", "ADE"),
        ("ADE_Starlink_05", "ADE"),       # underscore variant
        ("ABUK1 ISP1 STARLINK 01", "ABUK"),  # digits in code word
        ("AGOM2 STARLINK 01", "AGOM"),
    ])
    def test_starlink_hostnames(self, hostname: str, expected: str):
        assert _extract_delegation(hostname) == expected

    # IP addresses → None
    @pytest.mark.parametrize("hostname", [
        "10.128.108.16",
        "10.64.16.25",
        "10.130.2.90",
    ])
    def test_ip_addresses_return_none(self, hostname: str):
        assert _extract_delegation(hostname) is None

    # Empty / whitespace
    def test_empty_string(self):
        assert _extract_delegation("") is None

    def test_whitespace_only(self):
        assert _extract_delegation("   ") is None


# ── Description parsing ──────────────────────────────────────────────

class TestParseDescription:
    def test_standard_prometheus_format(self):
        desc = "? Prometheus - KADFGT - FortigateSiteDown"
        hostname, alert = _parse_description(desc)
        assert hostname == "KADFGT"
        assert alert == "FortigateSiteDown"

    def test_fqdn_hostname(self):
        desc = "? Prometheus - gvacfsp2app03p.gva.icrc.priv - WindowsServerCpuUsage"
        hostname, alert = _parse_description(desc)
        assert hostname == "gvacfsp2app03p.gva.icrc.priv"
        assert alert == "WindowsServerCpuUsage"

    def test_starlink_hostname(self):
        desc = "? Prometheus - ABE Starlink 02 - StarlinkStatusState"
        hostname, alert = _parse_description(desc)
        # The " - " split may grab "ABE Starlink 02" correctly
        assert alert == "StarlinkStatusState"

    def test_no_prometheus_keyword(self):
        hostname, alert = _parse_description("Some random description")
        assert hostname is None
        assert alert is None


# ── Alert categorisation ─────────────────────────────────────────────

class TestCategorise:
    @pytest.mark.parametrize("alert, expected_cat", [
        ("FortigateSiteDown", "site_down"),
        ("FemTargetDown", "site_down"),
        ("FortigateWanLatencyDeviation", "wan_degraded"),
        ("AudiocodesPingDown", "voip_down"),
        ("DhcpHighDHCPAddressUsageByScope", "capacity"),
        ("WindowsServerDown", "server"),
        ("VmwareDatastoreUtilization", "storage"),
        ("PostgresqlDown", "database"),
        ("BackupHealthCritical", "backup"),
        ("FortigateApDown", "wireless"),
        ("StarlinkStatusState", "network_device"),
        ("SomeUnknownAlert", "other"),
        (None, "other"),
    ])
    def test_alert_categories(self, alert: str, expected_cat: str):
        assert _categorise(alert) == expected_cat


# ── Network-related flag ─────────────────────────────────────────────

class TestNetworkRelated:
    def test_site_down_is_network(self):
        df = pd.DataFrame({
            "short_description": ["? Prometheus - KADFGT - FortigateSiteDown"],
            "is_prometheus": [True],
        })
        result = enrich_prometheus(df)
        assert bool(result["is_network_related"].iloc[0]) is True

    def test_server_alert_not_network(self):
        df = pd.DataFrame({
            "short_description": ["? Prometheus - srv01.gva.icrc.priv - WindowsServerCpuUsage"],
            "is_prometheus": [True],
        })
        result = enrich_prometheus(df)
        assert bool(result["is_network_related"].iloc[0]) is False

    def test_human_ticket_skipped(self):
        df = pd.DataFrame({
            "short_description": ["Cannot connect to VPN"],
            "is_prometheus": [False],
        })
        result = enrich_prometheus(df)
        assert bool(result["is_network_related"].iloc[0]) is False
        assert result["delegation_code"].iloc[0] is None
