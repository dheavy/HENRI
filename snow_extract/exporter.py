from __future__ import annotations

import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from playwright.async_api import async_playwright, BrowserContext

from .config import SnowConfig

logger = logging.getLogger(__name__)


class SnowExporter:
    """Playwright-based ServiceNow CSV extraction."""

    def __init__(self, config: SnowConfig) -> None:
        self.config = config
        self.raw_dir: Path = config.data_dir / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self._storage_state_path: Path = config.data_dir / ".snow_session.json"
        self._last_run_path: Path = config.data_dir / ".last_run"
        self._playwright = None
        self._browser = None
        self._context: Optional[BrowserContext] = None

    # -- async context manager -------------------------------------------------

    async def __aenter__(self) -> SnowExporter:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        storage = str(self._storage_state_path) if self._storage_state_path.exists() else None
        self._context = await self._browser.new_context(storage_state=storage)
        logger.info("Browser context created (storage_state reuse: %s)", storage is not None)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser resources released.")

    # -- authentication --------------------------------------------------------

    async def authenticate(self) -> None:
        """Login to ServiceNow via login.do and persist the session."""
        assert self._context is not None, "Use SnowExporter as an async context manager."

        page = await self._context.new_page()
        login_url = f"{self.config.instance_url.rstrip('/')}/login.do"
        logger.info("Authenticating to ServiceNow...")
        await page.goto(login_url, wait_until="networkidle")

        await page.fill("#user_name", self.config.username)
        await page.fill("#user_password", self.config.password)
        await page.click("#sysverb_login")
        await page.wait_for_load_state("networkidle")

        await self._context.storage_state(path=str(self._storage_state_path))
        self._storage_state_path.chmod(0o600)
        logger.info("Authenticated and session saved.")
        await page.close()

    # -- incident export (full range, batched by month) ------------------------

    async def export_incidents(self, start: date, end: date) -> list[Path]:
        """Export incidents in monthly batches to stay under the 10k row limit.

        Returns a list of paths to the saved CSV files.
        """
        assert self._context is not None, "Use SnowExporter as an async context manager."

        saved: list[Path] = []
        current = start.replace(day=1)

        while current < end:
            # Compute the last day of the current month
            if current.month == 12:
                month_end = date(current.year + 1, 1, 1)
            else:
                month_end = date(current.year, current.month + 1, 1)

            if month_end > end:
                month_end = end

            csv_path = await self._download_incident_csv(current, month_end)
            saved.append(csv_path)
            logger.info("Saved %s", csv_path)

            current = month_end

        self._write_last_run(datetime.utcnow())
        return saved

    # -- incremental export ----------------------------------------------------

    async def export_incidents_incremental(self, last_run: Optional[datetime] = None) -> Path:
        """Export incidents updated since *last_run* (or the stored timestamp)."""
        assert self._context is not None, "Use SnowExporter as an async context manager."

        if last_run is None:
            last_run = self._read_last_run()
        if last_run is None:
            raise ValueError(
                "No last_run timestamp provided and no stored timestamp found. "
                "Run a full export first."
            )

        ts = last_run.strftime("%Y-%m-%d %H:%M:%S")
        query = f"sys_updated_on>={ts}"
        filename = f"incidents_incremental_{last_run.strftime('%Y%m%d%H%M%S')}.csv"
        csv_path = self.raw_dir / filename

        await self._download_csv("incident", query, csv_path)
        self._write_last_run(datetime.utcnow())
        logger.info("Incremental export saved to %s", csv_path)
        return csv_path

    # -- location export -------------------------------------------------------

    async def export_locations(self) -> Path:
        """One-time export of the cmn_location table."""
        assert self._context is not None, "Use SnowExporter as an async context manager."

        csv_path = self.raw_dir / "locations.csv"
        location_fields = "sys_id,name,street,city,state,country,latitude,longitude"
        query = ""
        url = (
            f"{self.config.instance_url.rstrip('/')}/cmn_location_list.do"
            f"?CSV&sysparm_fields={location_fields}"
        )
        if query:
            url += f"&sysparm_query={query}"

        await self._download_to_file(url, csv_path)
        logger.info("Locations export saved to %s", csv_path)
        return csv_path

    # -- private helpers -------------------------------------------------------

    async def _download_incident_csv(self, start: date, end: date) -> Path:
        """Download a single month's incident CSV."""
        start_str = start.strftime("%Y-%m-%d")
        end_str = end.strftime("%Y-%m-%d")
        query = f"opened_at>={start_str}^opened_at<{end_str}"
        filename = f"incidents_{start.strftime('%Y-%m')}.csv"
        csv_path = self.raw_dir / filename

        await self._download_csv("incident", query, csv_path)
        return csv_path

    async def _download_csv(self, table: str, query: str, dest: Path) -> None:
        """Build a CSV export URL for *table* with *query* and download it."""
        url = (
            f"{self.config.instance_url.rstrip('/')}/{table}_list.do"
            f"?CSV&sysparm_fields={quote(self.config.export_fields, safe=',')}"
            f"&sysparm_query={quote(query, safe='')}"
        )
        await self._download_to_file(url, dest)

    async def _download_to_file(self, url: str, dest: Path) -> None:
        """Navigate to a CSV download URL and save the response body."""
        assert self._context is not None

        page = await self._context.new_page()
        logger.debug("Downloading %s", url)
        try:
            response = await page.goto(url, wait_until="networkidle")
            if response is None:
                raise RuntimeError(f"No response received for {url}")
            body = await response.body()
            dest.write_bytes(body)
            dest.chmod(0o600)
        finally:
            await page.close()

    # -- last-run bookkeeping --------------------------------------------------

    def _write_last_run(self, ts: datetime) -> None:
        self._last_run_path.write_text(ts.isoformat())
        self._last_run_path.chmod(0o600)
        logger.debug("Last run timestamp written: %s", ts.isoformat())

    def _read_last_run(self) -> Optional[datetime]:
        if not self._last_run_path.exists():
            return None
        raw = self._last_run_path.read_text().strip()
        return datetime.fromisoformat(raw)
