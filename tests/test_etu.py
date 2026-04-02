"""Tests for ETU (Effective Throughput per User) calculator."""

import math

import pytest

from henri.etu.calculator import (
    ETUResult,
    LinkETU,
    MSS,
    MATHIS_C,
    MIN_USERS,
    JITTER_FLOOR,
    JITTER_CEIL,
    RTT_DEFAULTS,
    RTT_DEFAULT_UNKNOWN,
    REDUNDANCY_WEIGHT,
    _mbps_to_score,
    _score_to_grade,
    compute_etu,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _make_link(
    cid: str = "TESTISP1",
    link_type: str | None = "Internet-Fiber",
    provider: str | None = "TestISP",
    committed_rate_kbps: int | None = 10_000,  # 10 Mbps
    measured_peak_bps: float | None = None,
    measured_rtt_ms: float | None = 10.0,
    packet_loss_ratio: float | None = 0.001,
    is_primary: bool = True,
) -> dict:
    return {
        "cid": cid,
        "link_type": link_type,
        "provider": provider,
        "committed_rate_kbps": committed_rate_kbps,
        "measured_peak_bps": measured_peak_bps,
        "measured_rtt_ms": measured_rtt_ms,
        "packet_loss_ratio": packet_loss_ratio,
        "is_primary": is_primary,
    }


# ── Test 1: Perfect data ────────────────────────────────────────────


class TestPerfectData:
    """Site with perfect data -> score near 100."""

    def test_high_score_with_good_link(self):
        link = _make_link(
            committed_rate_kbps=50_000,  # 50 Mbps
            measured_rtt_ms=10.0,
            packet_loss_ratio=0.0001,
        )
        result = compute_etu(
            site_code="TEST",
            links=[link],
            dhcp_lease_count=5,
            jitter_ms=5.0,
            availability_ratio=1.0,
        )
        assert result.score >= 85
        assert result.grade in ("Excellent", "Good")
        assert result.data_completeness == 1.0
        assert len(result.missing_data) == 0

    def test_all_fields_measured(self):
        link = _make_link()
        result = compute_etu("TEST", [link], dhcp_lease_count=10, jitter_ms=5, availability_ratio=0.99)
        for l in result.links:
            assert l.rtt_source == "measured"
            assert l.loss_source == "measured"


# ── Test 2: GEO VSAT with high loss ─────────────────────────────────


class TestVSATHighLoss:
    """Site with GEO VSAT only, high loss -> score < 30."""

    def test_vsat_scores_low(self):
        link = _make_link(
            link_type="Internet-VSAT",
            committed_rate_kbps=2_000,  # 2 Mbps
            measured_rtt_ms=620.0,
            packet_loss_ratio=0.05,
        )
        result = compute_etu("VSAT", [link], dhcp_lease_count=20, jitter_ms=None, availability_ratio=None)
        assert result.score < 30
        assert result.grade in ("Critical", "Degraded")


# ── Test 3: Starlink vs GEO VSAT ────────────────────────────────────


class TestStarlinkVsVSAT:
    """Same bandwidth, Starlink scores much higher than GEO VSAT."""

    def test_starlink_beats_vsat(self):
        vsat_link = _make_link(
            cid="VSAT1",
            link_type="Internet-VSAT",
            committed_rate_kbps=10_000,
            measured_rtt_ms=620.0,
            packet_loss_ratio=0.01,
        )
        starlink_link = _make_link(
            cid="STAR1",
            link_type="Internet-Starlink",
            committed_rate_kbps=10_000,
            measured_rtt_ms=45.0,
            packet_loss_ratio=0.01,
        )
        vsat_result = compute_etu("V", [vsat_link], None, None, None)
        star_result = compute_etu("S", [starlink_link], None, None, None)
        assert star_result.score > vsat_result.score
        assert star_result.etu_mbps > vsat_result.etu_mbps * 5  # dramatically better


# ── Test 4: Jitter penalty ───────────────────────────────────────────


class TestJitterPenalty:
    """0ms -> no penalty, 200ms -> max penalty."""

    def test_zero_jitter_no_penalty(self):
        result = compute_etu("J", [_make_link()], None, jitter_ms=0.0, availability_ratio=None)
        assert result.jitter_penalty == 1.0

    def test_below_floor_no_penalty(self):
        result = compute_etu("J", [_make_link()], None, jitter_ms=JITTER_FLOOR, availability_ratio=None)
        assert result.jitter_penalty == 1.0

    def test_max_jitter_max_penalty(self):
        result = compute_etu("J", [_make_link()], None, jitter_ms=200.0, availability_ratio=None)
        assert result.jitter_penalty == 0.0

    def test_above_ceiling_clamped(self):
        result = compute_etu("J", [_make_link()], None, jitter_ms=500.0, availability_ratio=None)
        assert result.jitter_penalty == 0.0

    def test_mid_jitter_partial_penalty(self):
        mid = (JITTER_FLOOR + JITTER_CEIL) / 2
        result = compute_etu("J", [_make_link()], None, jitter_ms=mid, availability_ratio=None)
        assert 0.4 < result.jitter_penalty < 0.6

    def test_none_jitter_no_penalty(self):
        result = compute_etu("J", [_make_link()], None, jitter_ms=None, availability_ratio=None)
        assert result.jitter_penalty == 1.0
        assert "jitter" in result.missing_data


# ── Test 5: Availability penalty (squared) ───────────────────────────


class TestAvailabilityPenalty:
    """100% -> no penalty, 90% -> 81% penalty (squared)."""

    def test_full_availability(self):
        result = compute_etu("A", [_make_link()], None, None, availability_ratio=1.0)
        assert result.availability_penalty == 1.0

    def test_90pct_availability(self):
        result = compute_etu("A", [_make_link()], None, None, availability_ratio=0.9)
        assert abs(result.availability_penalty - 0.81) < 0.001

    def test_50pct_availability(self):
        result = compute_etu("A", [_make_link()], None, None, availability_ratio=0.5)
        assert abs(result.availability_penalty - 0.25) < 0.001

    def test_none_availability_no_penalty(self):
        result = compute_etu("A", [_make_link()], None, None, availability_ratio=None)
        assert result.availability_penalty == 1.0
        assert "availability" in result.missing_data


# ── Test 6: Diversity bonus ──────────────────────────────────────────


class TestDiversityBonus:
    """1 provider -> 1.0, 3 providers -> 1.1."""

    def test_single_provider(self):
        result = compute_etu("D", [_make_link(provider="ISP-A")], None, None, None)
        assert result.diversity_bonus == 1.0

    def test_two_providers(self):
        links = [
            _make_link(cid="L1", provider="ISP-A"),
            _make_link(cid="L2", provider="ISP-B", is_primary=False),
        ]
        result = compute_etu("D", links, None, None, None)
        assert result.diversity_bonus == 1.05

    def test_three_providers(self):
        links = [
            _make_link(cid="L1", provider="ISP-A"),
            _make_link(cid="L2", provider="ISP-B", is_primary=False),
            _make_link(cid="L3", provider="ISP-C", is_primary=False),
        ]
        result = compute_etu("D", links, None, None, None)
        assert result.diversity_bonus == 1.1

    def test_null_providers_ignored(self):
        links = [
            _make_link(cid="L1", provider=None),
            _make_link(cid="L2", provider=None, is_primary=False),
        ]
        result = compute_etu("D", links, None, None, None)
        assert result.diversity_bonus == 1.0


# ── Test 7: Missing data completeness ────────────────────────────────


class TestMissingData:
    """All estimated -> completeness near 0."""

    def test_all_estimated(self):
        link = _make_link(
            committed_rate_kbps=None,
            measured_peak_bps=None,
            measured_rtt_ms=None,
            packet_loss_ratio=None,
        )
        result = compute_etu("M", [link], None, None, None)
        assert result.data_completeness == 0.0
        assert len(result.missing_data) > 3

    def test_all_measured(self):
        link = _make_link()  # has rtt, loss, capacity
        result = compute_etu("M", [link], dhcp_lease_count=10, jitter_ms=5, availability_ratio=0.99)
        assert result.data_completeness == 1.0
        assert len(result.missing_data) == 0


# ── Test 8: Zero links ──────────────────────────────────────────────


class TestZeroLinks:
    """Zero links -> score 0, grade 'No data'."""

    def test_empty_links(self):
        result = compute_etu("EMPTY", [], None, None, None)
        assert result.score == 0
        assert result.grade == "No data"
        assert result.etu_mbps == 0
        assert result.num_links == 0
        assert result.data_completeness == 0.0
        assert "all" in result.missing_data


# ── Test 9: User count floor ────────────────────────────────────────


class TestUserCountFloor:
    """2 DHCP leases -> uses MIN_USERS (5)."""

    def test_below_minimum(self):
        result = compute_etu("U", [_make_link()], dhcp_lease_count=2, jitter_ms=None, availability_ratio=None)
        assert result.num_users == MIN_USERS
        assert result.num_users_source == "default"
        assert "user_count" in result.missing_data

    def test_none_uses_default(self):
        result = compute_etu("U", [_make_link()], dhcp_lease_count=None, jitter_ms=None, availability_ratio=None)
        assert result.num_users == MIN_USERS
        assert result.num_users_source == "default"

    def test_above_minimum_uses_actual(self):
        result = compute_etu("U", [_make_link()], dhcp_lease_count=50, jitter_ms=None, availability_ratio=None)
        assert result.num_users == 50
        assert result.num_users_source == "dhcp"

    def test_exact_minimum(self):
        result = compute_etu("U", [_make_link()], dhcp_lease_count=MIN_USERS, jitter_ms=None, availability_ratio=None)
        assert result.num_users == MIN_USERS
        assert result.num_users_source == "dhcp"


# ── Test 10: Log score mapping ───────────────────────────────────────


class TestLogScoreMapping:
    """0.05 Mbps -> 0, 5 Mbps -> 100, 0.5 Mbps -> ~50."""

    def test_minimum_threshold(self):
        assert _mbps_to_score(0.05) == 0

    def test_maximum_threshold(self):
        assert _mbps_to_score(5.0) == 100

    def test_midpoint_roughly_50(self):
        score = _mbps_to_score(0.5)
        assert 45 <= score <= 55

    def test_zero_mbps(self):
        assert _mbps_to_score(0) == 0

    def test_negative_mbps(self):
        assert _mbps_to_score(-1) == 0

    def test_above_max(self):
        assert _mbps_to_score(100) == 100

    def test_very_low(self):
        score = _mbps_to_score(0.01)
        assert score < 20


# ── Grade mapping ────────────────────────────────────────────────────


class TestGradeMapping:
    def test_grades(self):
        assert _score_to_grade(100) == "Excellent"
        assert _score_to_grade(90) == "Excellent"
        assert _score_to_grade(89) == "Good"
        assert _score_to_grade(70) == "Good"
        assert _score_to_grade(69) == "Adequate"
        assert _score_to_grade(50) == "Adequate"
        assert _score_to_grade(49) == "Degraded"
        assert _score_to_grade(25) == "Degraded"
        assert _score_to_grade(24) == "Critical"
        assert _score_to_grade(0) == "Critical"


# ── RTT defaults ─────────────────────────────────────────────────────


class TestRTTDefaults:
    """Estimated RTT uses link type defaults."""

    def test_vsat_default(self):
        link = _make_link(link_type="Internet-VSAT", measured_rtt_ms=None)
        result = compute_etu("R", [link], None, None, None)
        assert result.links[0].rtt_ms == RTT_DEFAULTS["Internet-VSAT"]
        assert result.links[0].rtt_source == "estimated"

    def test_fiber_default(self):
        link = _make_link(link_type="Internet-Fiber", measured_rtt_ms=None)
        result = compute_etu("R", [link], None, None, None)
        assert result.links[0].rtt_ms == RTT_DEFAULTS["Internet-Fiber"]

    def test_unknown_type_default(self):
        link = _make_link(link_type="Unknown-Type", measured_rtt_ms=None)
        result = compute_etu("R", [link], None, None, None)
        assert result.links[0].rtt_ms == RTT_DEFAULT_UNKNOWN


# ── Aggregation ──────────────────────────────────────────────────────


class TestLinkAggregation:
    """Primary + secondary aggregation with REDUNDANCY_WEIGHT."""

    def test_primary_only(self):
        result = compute_etu("A", [_make_link(is_primary=True)], None, None, None)
        assert result.aggregate_bps > 0
        assert result.aggregate_bps == result.links[0].effective_bps

    def test_secondary_weighted(self):
        primary = _make_link(cid="P1", is_primary=True)
        backup = _make_link(cid="B1", is_primary=False, provider="ISP-B")
        result = compute_etu("A", [primary, backup], None, None, None)
        primary_bps = result.links[0].effective_bps
        backup_bps = result.links[1].effective_bps
        expected = primary_bps + backup_bps * REDUNDANCY_WEIGHT
        assert abs(result.aggregate_bps - expected) < 1

    def test_no_primary_treats_all_as_primary(self):
        links = [
            _make_link(cid="L1", is_primary=False),
            _make_link(cid="L2", is_primary=False, provider="ISP-B"),
        ]
        result = compute_etu("A", links, None, None, None)
        total = sum(l.effective_bps for l in result.links)
        assert abs(result.aggregate_bps - total) < 1


# ── Mathis formula ───────────────────────────────────────────────────


class TestMathisFormula:
    """Verify the Mathis throughput formula."""

    def test_mathis_basic(self):
        """Mathis = (MSS / RTT) * (C / sqrt(loss)) * 8."""
        link = _make_link(
            measured_rtt_ms=100.0,
            packet_loss_ratio=0.01,
            committed_rate_kbps=None,
            measured_peak_bps=None,
        )
        result = compute_etu("M", [link], None, None, None)
        rtt_sec = 0.1
        expected_bps = (MSS / rtt_sec) * (MATHIS_C / math.sqrt(0.01)) * 8
        assert abs(result.links[0].mathis_bps - expected_bps) < 1

    def test_capped_at_capacity(self):
        """Effective throughput is capped at committed rate."""
        link = _make_link(
            committed_rate_kbps=1_000,  # 1 Mbps
            measured_rtt_ms=10.0,
            packet_loss_ratio=0.0001,
        )
        result = compute_etu("C", [link], None, None, None)
        assert result.links[0].effective_bps <= 1_000_000  # 1 Mbps in bps
        assert result.links[0].mathis_bps > result.links[0].effective_bps

    def test_loss_floor(self):
        """Very low loss (0) uses floor of 0.0001."""
        link = _make_link(packet_loss_ratio=0.0)
        result = compute_etu("L", [link], None, None, None)
        # Should not be infinite
        assert result.links[0].mathis_bps > 0
        assert result.links[0].mathis_bps < 1e15
