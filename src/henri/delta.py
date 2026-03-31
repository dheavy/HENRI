"""Delta alerting — compare today's risk scores against the previous run.

Flags countries that escalated or de-escalated by more than 15 points.
Persists scores to ``data/processed/risk_scores.json`` for next comparison.
"""

from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_THRESHOLD = 15.0

_SIGNAL_KEYS = ["acled_events", "acled_fatalities", "ioda_score", "cf_outages", "snow_sitedown"]


def _identify_changed_signals(prev: dict, curr: dict) -> list[str]:
    """Return signal names where the change is significant."""
    changed: list[str] = []
    for key in _SIGNAL_KEYS:
        old = float(prev.get(key, 0))
        new = float(curr.get(key, 0))
        abs_delta = abs(new - old)
        rel_delta = abs_delta / max(old, 1)
        if abs_delta > 5 or rel_delta > 0.2:
            changed.append(key)
    return changed


def compute_deltas(
    current_scores: list[dict[str, Any]],
    data_dir: Path,
) -> list[dict[str, Any]]:
    """Compare *current_scores* against the previously saved scores.

    Returns a list of alert dicts for countries that crossed the ±15
    threshold.  Returns ``[]`` if no previous scores exist (first run).
    """
    prev_path = data_dir / "processed" / "risk_scores.json"
    if not prev_path.exists():
        logger.info("No previous risk scores found (first run); skipping delta")
        return []

    try:
        with open(prev_path) as f:
            prev_data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not load previous risk scores: %s", exc)
        return []

    prev_cards = prev_data.get("cards", [])
    if not prev_cards:
        return []

    prev_by_iso3 = {c["country_iso3"]: c for c in prev_cards if "country_iso3" in c}

    alerts: list[dict[str, Any]] = []
    for card in current_scores:
        iso3 = card.get("country_iso3")
        if not iso3 or iso3 not in prev_by_iso3:
            continue

        prev_card = prev_by_iso3[iso3]
        prev_score = float(prev_card.get("combined_risk", 0))
        curr_score = float(card.get("combined_risk", 0))
        delta = curr_score - prev_score

        if abs(delta) < _THRESHOLD:
            continue

        alert_type = "ESCALATION" if delta > 0 else "DE-ESCALATION"
        signals = _identify_changed_signals(prev_card, card)

        alerts.append({
            "country": card.get("country", iso3),
            "country_iso3": iso3,
            "previous_score": round(prev_score, 1),
            "current_score": round(curr_score, 1),
            "delta": round(delta, 1),
            "alert_type": alert_type,
            "signals_changed": signals,
        })

    alerts.sort(key=lambda a: abs(a["delta"]), reverse=True)
    if alerts:
        for a in alerts:
            logger.info(
                "ALERT: %s %s %+.1f points (%.1f → %.1f)",
                a["country"], a["alert_type"], a["delta"],
                a["previous_score"], a["current_score"],
            )
    return alerts


def save_risk_scores(scores: list[dict[str, Any]], data_dir: Path) -> Path:
    """Persist risk scores to ``data/processed/risk_scores.json``.

    Uses atomic write (temp file + rename) to avoid corruption on crash.
    """
    output_path = data_dir / "processed" / "risk_scores.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "_generated_at": datetime.now(timezone.utc).isoformat(),
        "cards": scores,
    }

    # Atomic write
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(output_path.parent), suffix=".tmp"
    )
    try:
        with open(tmp_fd, "w") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        Path(tmp_path).replace(output_path)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise

    logger.info("Risk scores saved to %s", output_path.name)
    return output_path
