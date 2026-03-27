"""Enrich human-filed tickets with keyword-based network relevance detection."""

from __future__ import annotations

import logging
from typing import Sequence

import pandas as pd

logger = logging.getLogger(__name__)

# Multilingual keyword lists (all lowercase for case-insensitive matching)
_KEYWORDS_EN: list[str] = [
    "network",
    "dns",
    "vpn",
    "bandwidth",
    "internet",
    "connectivity",
    "wifi",
    "wi-fi",
    "firewall",
    "router",
    "switch",
    "vsat",
    "link down",
    "latency",
    "proxy",
    "slow",
    "cannot connect",
    "no access",
    "forti",
]

_KEYWORDS_FR: list[str] = [
    "réseau",
    "connexion",
    "internet",
    "lent",
    "pas de connexion",
    "problème de connexion",
    "wifi",
]

_KEYWORDS_ES: list[str] = [
    "internet",
    "red",
    "conexión",
    "lento",
    "problemas con internet",
    "vpn",
]

# Deduplicated, ordered longest-first so multi-word phrases match before substrings
_ALL_KEYWORDS: list[str] = sorted(
    set(_KEYWORDS_EN + _KEYWORDS_FR + _KEYWORDS_ES),
    key=lambda k: (-len(k), k),
)


def _match_keywords(text: str) -> list[str]:
    """Return the list of matched keywords found in *text* (case-insensitive)."""
    if not isinstance(text, str):
        return []
    lower = text.lower()
    return [kw for kw in _ALL_KEYWORDS if kw in lower]


def enrich_human(df: pd.DataFrame) -> pd.DataFrame:
    """Add ``matched_keywords`` (stringified list) and ``is_network_related``
    (bool) columns for rows where ``is_prometheus`` is False.

    Prometheus rows receive ``"[]"`` and ``False``.
    """
    matched: list[str] = []
    network_flags: list[bool] = []

    for _, row in df.iterrows():
        if row.get("is_prometheus", False):
            matched.append("[]")
            # Preserve existing network flag from prometheus enrichment
            network_flags.append(row.get("is_network_related", False))
            continue

        desc = row.get("short_description", "")
        hits = _match_keywords(desc)
        matched.append(str(hits))
        network_flags.append(len(hits) > 0)

    df = df.copy()
    df["matched_keywords"] = matched
    df["is_network_related"] = network_flags

    return df
