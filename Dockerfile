# ── Stage 1: Build React frontend ─────────────────────────────────
FROM node:22-alpine AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python backend + built frontend ─────────────────────
# Pinned base images for reproducibility and supply-chain security
FROM python:3.13-slim@sha256:739e7213785e88c0f702dcdc12c0973afcbd606dbf021a589cab77d6b00b579d AS base
FROM ghcr.io/astral-sh/uv:latest@sha256:c4f5de312ee66d46810635ffc5df34a1973ba753e7241ce3a08ef979ddd7bea5 AS uv

FROM base

LABEL org.opencontainers.image.title="HENRI" \
      org.opencontainers.image.description="Humanitarian Early-warning Network Resilience Intelligence" \
      org.opencontainers.image.vendor="ICRC"

WORKDIR /app

# Install uv from pinned image
COPY --from=uv /uv /usr/local/bin/uv

# Install Python dependencies first (layer caching)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Install Playwright headless chromium + system deps, then clean up
# (needed for ServiceNow browser-based CSV extraction)
RUN uv run playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# OpenShift-friendly: non-root user, but files owned by group root (gid 0)
# so the random UID injected by OpenShift's restricted-v2 SCC can still
# write. We pick uid 1001 to match the OpenShift UBI convention; the
# actual runtime UID will be assigned by the SCC.
RUN useradd -m -u 1001 -g 0 -s /usr/sbin/nologin henri \
    && chown -R 1001:0 /app \
    && chmod -R g=u /app

# Copy source code (group root, group-writable to match runtime UID injection)
COPY --chown=1001:0 backend/ ./backend/
COPY --chown=1001:0 templates/ ./templates/
COPY --chown=1001:0 data/fixtures/ ./data/fixtures/
COPY --chown=1001:0 data/reference/ ./data/reference/

# Copy built React frontend from stage 1
COPY --from=frontend-build --chown=1001:0 /app/frontend/dist ./frontend/dist

# Final perms pass — must be after all COPYs so group root can write everywhere
RUN chmod -R g=u /app

# Drop to non-root. OpenShift will override with an injected UID at runtime;
# this default lets the image run on plain Docker/Podman too.
USER 1001

# uv: cache in writable tmpfs, skip sync at runtime (deps frozen at build)
ENV UV_CACHE_DIR=/tmp/uv-cache
ENV UV_NO_SYNC=1
ENV PYTHONPATH=/app/backend

# FastAPI serves on port 8000
EXPOSE 8000

# Health check — hit the FastAPI health endpoint
HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"]

# Default: start the web application (FastAPI + scheduler)
# Override with "run_all" to run the pipeline CLI instead.
CMD [".venv/bin/uvicorn", "henri.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
