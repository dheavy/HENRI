"""HENRI FastAPI application.

Serves the JSON API at ``/api/v1/`` and the React SPA as static files.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api.router import api_router
from .db import init_db
from .scheduler import start_scheduler, stop_scheduler

load_dotenv()

logger = logging.getLogger(__name__)

_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    init_db()
    if os.getenv("HENRI_SCHEDULER_ENABLED", "0") == "1":
        start_scheduler()
        logger.info("Background scheduler enabled")
    yield
    stop_scheduler()


def create_app() -> FastAPI:
    app = FastAPI(
        title="HENRI",
        description="Humanitarian Early-warning Network Resilience Intelligence",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=_lifespan,
    )

    # CORS — allow local dev origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # Global exception handler — no stack traces in production
    @app.exception_handler(Exception)
    async def _unhandled_exception(request: object, exc: Exception) -> JSONResponse:
        logger.error("Unhandled exception: %s", type(exc).__name__)
        return JSONResponse({"error": "Internal server error"}, status_code=500)

    # API routes
    app.include_router(api_router, prefix="/api/v1")

    # Health check
    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok", "service": "henri"}

    # Report file endpoints (must be before SPA catch-all)
    _reports_dir = Path(os.getenv("DATA_DIR", "./data")) / "reports"

    @app.get("/api/v1/reports")
    async def list_reports() -> dict:
        """List available HTML reports."""
        if not _reports_dir.is_dir():
            return {"reports": []}
        files = sorted(
            [f.name for f in _reports_dir.glob("*.html")],
            reverse=True,
        )
        return {"reports": files}

    def _resolve_report(filename: str) -> Path | None:
        if ".." in filename or "/" in filename or not filename.endswith(".html"):
            return None
        path = _reports_dir / filename
        if path.is_symlink():
            return None
        resolved = path.resolve()
        if not resolved.exists() or not resolved.is_relative_to(_reports_dir.resolve()):
            return None
        return resolved

    @app.get("/api/v1/reports/{filename}")
    async def view_report(filename: str) -> FileResponse:
        """Serve a report HTML file inline (for iframe embedding)."""
        path = _resolve_report(filename)
        if not path:
            return JSONResponse({"error": "Not found"}, status_code=404)
        return FileResponse(str(path), media_type="text/html")

    @app.get("/api/v1/reports/{filename}/download")
    async def download_report(filename: str) -> FileResponse:
        """Serve a report HTML file as a download attachment."""
        path = _resolve_report(filename)
        if not path:
            return JSONResponse({"error": "Not found"}, status_code=404)
        return FileResponse(str(path), media_type="text/html", filename=filename)

    # Serve React build if it exists
    if _FRONTEND_DIST.is_dir():
        assets_dir = _FRONTEND_DIST / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str) -> FileResponse:
            """Catch-all: serve index.html for client-side routing."""
            if ".." in full_path:
                return JSONResponse({"error": "Invalid path"}, status_code=400)
            index = _FRONTEND_DIST / "index.html"
            if index.exists():
                return FileResponse(str(index))
            return JSONResponse({"error": "Frontend not built"}, status_code=404)
    else:
        @app.get("/")
        async def no_frontend() -> dict:
            return {
                "service": "HENRI API",
                "docs": "/api/docs",
                "health": "/api/health",
                "note": "Frontend not built. Run: cd frontend && npm run build",
            }

    return app


app = create_app()
