"""HENRI FastAPI application.

Serves the JSON API at ``/api/v1/`` and the React SPA as static files.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from .api.router import api_router
from .db import init_db
from .scheduler import start_scheduler, stop_scheduler
from henri.logging import setup_logging, new_correlation_id

load_dotenv()
setup_logging()

logger = logging.getLogger(__name__)
_request_logger = logging.getLogger("henri.web.requests")

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

    # Request logging middleware — logs every API call with timing
    class RequestLoggingMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # Skip logging for static assets and health checks
            path = request.url.path
            if path.startswith("/assets") or path == "/api/health":
                return await call_next(request)

            # Set correlation ID from header or generate new one
            cid = request.headers.get("X-Correlation-ID") or new_correlation_id()

            start = time.time()
            response = await call_next(request)
            duration_ms = round((time.time() - start) * 1000, 1)

            _request_logger.info(
                "%s %s %d %.1fms",
                request.method, path, response.status_code, duration_ms,
                extra={
                    "method": request.method,
                    "path": path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                    "client_ip": request.client.host if request.client else None,
                },
            )
            response.headers["X-Correlation-ID"] = cid
            return response

    app.add_middleware(RequestLoggingMiddleware)

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
        async def serve_spa(full_path: str):
            """Serve top-level static files from dist/, else fall back to
            index.html for client-side routing.

            Without this, requests like /favicon.svg or /ICRC-hand-line-*.svg
            (assets that Vite copies to dist/ root, NOT dist/assets/) match
            this catch-all and get index.html back with text/html content
            type. The browser then renders HTML in place of an image — no
            404 surfaces, but the image is broken.
            """
            if ".." in full_path:
                return JSONResponse({"error": "Invalid path"}, status_code=400)

            # If the path resolves to a real file under dist/, serve it
            # directly. FileResponse infers the correct media_type from the
            # extension via mimetypes.
            if full_path:
                candidate = _FRONTEND_DIST / full_path
                try:
                    candidate_resolved = candidate.resolve()
                    dist_resolved = _FRONTEND_DIST.resolve()
                    # Path traversal guard: must stay inside dist/.
                    if (
                        candidate_resolved.is_file()
                        and dist_resolved in candidate_resolved.parents
                    ):
                        return FileResponse(str(candidate_resolved))
                except (OSError, RuntimeError):
                    pass

            # Fall through to SPA: index.html for client-side routing.
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
