"""Grafana API client with rate limiting, retry, and graceful degradation."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx
import pandas as pd

logger = logging.getLogger(__name__)


def _retry_config() -> tuple[bool, int, int]:
    """Read retry config from env vars."""
    enabled = os.getenv("GRAFANA_RETRY_ENABLED", "0") == "1"
    wait = int(os.getenv("GRAFANA_RETRY_WAITING_TIME", "180"))
    times = int(os.getenv("GRAFANA_RETRY_TIMES", "5"))
    return enabled, wait, times


class GrafanaClient:
    """Grafana API client with rate limiting, retry, and graceful degradation."""

    def __init__(self, base_url: str, api_token: str, prometheus_ds_id: str = "1"):
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.prometheus_ds_id = prometheus_ds_id
        self._last_request_time = 0.0
        self._min_interval = 0.5  # max 2 req/s
        self._client: httpx.Client | None = None

    @property
    def is_available(self) -> bool:
        return bool(self.base_url and self.api_token)

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_token}"},
                timeout=30.0,
            )
        return self._client

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

    def _request_with_retry(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        label: str = "Grafana request",
    ) -> httpx.Response | None:
        """Execute an HTTP request with configurable retry logic.

        Returns the response on success, or None if all attempts fail.
        """
        retry_enabled, retry_wait, retry_times = _retry_config()
        max_attempts = retry_times if retry_enabled else 1

        for attempt in range(1, max_attempts + 1):
            self._rate_limit()
            try:
                client = self._get_client()
                if method == "GET":
                    resp = client.get(path, params=params)
                else:
                    resp = client.post(path, data=params)

                if resp.status_code == 200:
                    return resp

                # Non-200: log and potentially retry
                logger.debug("%s returned %d (attempt %d/%d)", label, resp.status_code, attempt, max_attempts)

                if attempt < max_attempts:
                    logger.info("%s failed (HTTP %d), retrying in %ds (%d/%d)",
                                label, resp.status_code, retry_wait, attempt, max_attempts)
                    time.sleep(retry_wait)
                    # Reset client in case of stale connection
                    self.close()
                    continue

            except httpx.RequestError as e:
                logger.debug("%s network error: %s (attempt %d/%d)", label, e, attempt, max_attempts)
                if attempt < max_attempts:
                    logger.info("%s network error, retrying in %ds (%d/%d)",
                                label, retry_wait, attempt, max_attempts)
                    time.sleep(retry_wait)
                    self.close()
                    continue

        logger.warning("%s failed after %d attempt(s)", label, max_attempts)
        return None

    def query_instant(self, promql: str) -> pd.DataFrame:
        """Execute instant PromQL query via Grafana datasource proxy."""
        if not self.is_available:
            logger.warning("Grafana not configured, returning empty DataFrame")
            return pd.DataFrame()

        resp = self._request_with_retry(
            "GET",
            f"/api/datasources/proxy/{self.prometheus_ds_id}/api/v1/query",
            params={"query": promql},
            label="Grafana instant query",
        )
        if resp is None:
            return pd.DataFrame()
        try:
            return self._parse_vector(resp.json())
        except Exception:
            return pd.DataFrame()

    def query_range(self, promql: str, start: float, end: float, step: str = "1h") -> pd.DataFrame:
        """Execute range PromQL query."""
        if not self.is_available:
            logger.warning("Grafana not configured, returning empty DataFrame")
            return pd.DataFrame()

        resp = self._request_with_retry(
            "GET",
            f"/api/datasources/proxy/{self.prometheus_ds_id}/api/v1/query_range",
            params={"query": promql, "start": start, "end": end, "step": step},
            label="Grafana range query",
        )
        if resp is None:
            return pd.DataFrame()
        try:
            return self._parse_matrix(resp.json())
        except Exception:
            return pd.DataFrame()

    def get_datasources(self) -> list[dict]:
        if not self.is_available:
            return []
        resp = self._request_with_retry("GET", "/api/datasources", label="Grafana datasources")
        if resp is None:
            return []
        return resp.json()

    def search_dashboards(self) -> list[dict]:
        if not self.is_available:
            return []
        resp = self._request_with_retry("GET", "/api/search", params={"type": "dash-db"},
                                         label="Grafana dashboard search")
        if resp is None:
            return []
        return resp.json()

    def get_dashboard(self, uid: str) -> dict:
        if not self.is_available:
            return {}
        resp = self._request_with_retry("GET", f"/api/dashboards/uid/{uid}",
                                         label="Grafana dashboard fetch")
        if resp is None:
            return {}
        return resp.json()

    def _parse_vector(self, data: dict) -> pd.DataFrame:
        results = data.get("data", {}).get("result", [])
        if not results:
            return pd.DataFrame()
        rows = []
        for r in results:
            row = dict(r.get("metric", {}))
            row["value"] = float(r["value"][1])
            row["timestamp"] = float(r["value"][0])
            rows.append(row)
        return pd.DataFrame(rows)

    def _parse_matrix(self, data: dict) -> pd.DataFrame:
        results = data.get("data", {}).get("result", [])
        if not results:
            return pd.DataFrame()
        rows = []
        for r in results:
            metric = r.get("metric", {})
            for ts, val in r.get("values", []):
                row = dict(metric)
                row["timestamp"] = float(ts)
                row["value"] = float(val)
                rows.append(row)
        return pd.DataFrame(rows)

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
