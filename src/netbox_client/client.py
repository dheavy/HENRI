"""NetBox REST API client with paginated fetching."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class NetBoxClient:
    """Thin wrapper around the NetBox REST API.

    Auth via ``Authorization: Token <token>`` header.
    Uses ``limit=0`` to fetch all records in a single request
    (NetBox returns everything when limit=0).
    """

    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._client: httpx.Client | None = None
        self._last_request = 0.0
        self._min_interval = 0.5  # max 2 req/s

    @property
    def is_available(self) -> bool:
        return bool(self.base_url and self.token)

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Token {self.token}"},
                timeout=30.0,
            )
        return self._client

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_request
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request = time.time()

    def get_all(self, endpoint: str, **params: Any) -> list[dict]:
        """Fetch all records from *endpoint* using ``limit=0``.

        Returns the ``results`` list, or ``[]`` on error.
        """
        if not self.is_available:
            logger.warning("NetBox not configured")
            return []

        self._rate_limit()
        params.setdefault("limit", 0)
        try:
            resp = self._get_client().get(endpoint, params=params)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            logger.info("Fetched %d records from %s", len(results), endpoint)
            return results
        except Exception as e:
            logger.debug("NetBox request error: %s", e)
            logger.warning("NetBox request to %s failed", endpoint)
            return []

    def get_sites(self) -> list[dict]:
        return self.get_all("/api/dcim/sites/")

    def get_devices(self) -> list[dict]:
        return self.get_all("/api/dcim/devices/")

    def get_circuits(self) -> list[dict]:
        return self.get_all("/api/circuits/circuits/")

    def get_providers(self) -> list[dict]:
        return self.get_all("/api/circuits/providers/")

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
