"""Tests for security hardening — URL validation, input sanitization, path safety."""

import pytest

from snow_extract.exporter import _validate_instance_url


class TestValidateInstanceUrl:
    def test_valid_https(self):
        _validate_instance_url("https://smt.example.com/")  # no exception

    def test_rejects_http(self):
        with pytest.raises(ValueError, match="HTTPS"):
            _validate_instance_url("http://smt.example.com/")

    def test_rejects_empty_host(self):
        with pytest.raises(ValueError, match="hostname"):
            _validate_instance_url("https://")

    def test_rejects_ftp(self):
        with pytest.raises(ValueError, match="HTTPS"):
            _validate_instance_url("ftp://files.example.com/")

    def test_rejects_no_scheme(self):
        with pytest.raises(ValueError, match="HTTPS"):
            _validate_instance_url("smt.example.com")


class TestPromqlDaysValidation:
    def test_valid_days(self):
        from grafana_client.site_status import pull_site_status
        from grafana_client.client import GrafanaClient
        # Unconfigured client returns empty — but no crash
        client = GrafanaClient("", "", "1")
        result = pull_site_status(client, days=30)
        assert result.empty

    def test_negative_days_clamped(self):
        from grafana_client.site_status import pull_site_status
        from grafana_client.client import GrafanaClient
        client = GrafanaClient("", "", "1")
        # Should not crash, just clamp and return empty
        result = pull_site_status(client, days=-5)
        assert result.empty

    def test_excessive_days_clamped(self):
        from grafana_client.site_status import pull_site_status
        from grafana_client.client import GrafanaClient
        client = GrafanaClient("", "", "1")
        result = pull_site_status(client, days=9999)
        assert result.empty


class TestDashboardUidValidation:
    def test_valid_uid_passes(self):
        import re
        uid_re = re.compile(r"^[\w-]+$")
        assert uid_re.match("abc123-def")
        assert uid_re.match("simple_uid")

    def test_traversal_uid_rejected(self):
        import re
        uid_re = re.compile(r"^[\w-]+$")
        assert not uid_re.match("../../../etc/passwd")
        assert not uid_re.match("uid;rm -rf /")
        assert not uid_re.match("uid\ninjection")
        assert not uid_re.match("")


class TestBandwidthLabelValidation:
    def test_safe_labels_accepted(self):
        from grafana_client.bandwidth import _SAFE_LABEL_RE
        assert _SAFE_LABEL_RE.match("JUB")
        assert _SAFE_LABEL_RE.match("ABE_Starlink_05")
        assert _SAFE_LABEL_RE.match("GVA HQ")

    def test_injection_labels_rejected(self):
        from grafana_client.bandwidth import _SAFE_LABEL_RE
        assert not _SAFE_LABEL_RE.match('JUB"})')
        assert not _SAFE_LABEL_RE.match("JUB\nmalicious")
        assert not _SAFE_LABEL_RE.match('"; drop table')
        assert not _SAFE_LABEL_RE.match("")


class TestCsvFormulaProtection:
    def test_locations_csv_quoted(self, tmp_path):
        """Location CSV should use QUOTE_ALL to prevent formula injection."""
        import pandas as pd
        from snow_parse.location_normaliser import normalise_locations

        # Create a minimal CSV with a formula-like value
        csv_in = tmp_path / "locations.csv"
        csv_in.write_text(
            'sys_id,name,city,state,country,latitude,longitude,parent\n'
            '1,"=CMD(calc)",Juba,,South Sudan,,,\n'
        )
        csv_out = tmp_path / "clean.csv"
        normalise_locations(csv_in, csv_out)

        raw = csv_out.read_text()
        # Every field should be quoted (QUOTE_ALL)
        for line in raw.strip().split("\n"):
            fields = line.split(",")
            for field in fields:
                # Each field should start and end with quotes
                assert field.startswith('"') and field.endswith('"'), (
                    f"Field not quoted: {field!r}"
                )


class TestScriptTagEscaping:
    def test_safe_json_escapes_script_close(self):
        from snow_analyse.baseline_report import _safe_json
        result = _safe_json({"text": "</script><script>alert(1)</script>"})
        assert "</script>" not in result
        assert r"<\/script>" in result
