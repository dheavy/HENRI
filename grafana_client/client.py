import logging
import time
from typing import Any

import httpx
import pandas as pd

logger = logging.getLogger(__name__)


class GrafanaClient:
    """Grafana API client with rate limiting and graceful degradation."""

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

    def query_instant(self, promql: str) -> pd.DataFrame:
        """Execute instant PromQL query via Grafana datasource proxy."""
        if not self.is_available:
            logger.warning("Grafana not configured, returning empty DataFrame")
            return pd.DataFrame()
        self._rate_limit()
        client = self._get_client()
        try:
            resp = client.get(
                f"/api/datasources/proxy/{self.prometheus_ds_id}/api/v1/query",
                params={"query": promql},
            )
            resp.raise_for_status()
            return self._parse_vector(resp.json())
        except Exception as e:
            logger.warning(f"Grafana query failed: {e}")
            return pd.DataFrame()

    def query_range(self, promql: str, start: float, end: float, step: str = "1h") -> pd.DataFrame:
        """Execute range PromQL query."""
        if not self.is_available:
            logger.warning("Grafana not configured, returning empty DataFrame")
            return pd.DataFrame()
        self._rate_limit()
        client = self._get_client()
        try:
            resp = client.get(
                f"/api/datasources/proxy/{self.prometheus_ds_id}/api/v1/query_range",
                params={"query": promql, "start": start, "end": end, "step": step},
            )
            resp.raise_for_status()
            return self._parse_matrix(resp.json())
        except Exception as e:
            logger.warning(f"Grafana range query failed: {e}")
            return pd.DataFrame()

    def get_datasources(self) -> list[dict]:
        if not self.is_available:
            return []
        self._rate_limit()
        try:
            resp = self._get_client().get("/api/datasources")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"Failed to get datasources: {e}")
            return []

    def search_dashboards(self) -> list[dict]:
        if not self.is_available:
            return []
        self._rate_limit()
        try:
            resp = self._get_client().get("/api/search", params={"type": "dash-db"})
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"Failed to search dashboards: {e}")
            return []

    def get_dashboard(self, uid: str) -> dict:
        if not self.is_available:
            return {}
        self._rate_limit()
        try:
            resp = self._get_client().get(f"/api/dashboards/uid/{uid}")
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning(f"Failed to get dashboard {uid}: {e}")
            return {}

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
