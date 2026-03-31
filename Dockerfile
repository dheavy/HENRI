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
RUN uv run playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Create non-root user with no login shell
RUN useradd -m -u 1000 -s /usr/sbin/nologin henri \
    && chown -R henri:henri /app

# Copy source
COPY --chown=henri:henri . .

# Drop to non-root
USER henri

# uv: cache in writable tmpfs, skip sync at runtime (deps frozen at build)
ENV UV_CACHE_DIR=/tmp/uv-cache
ENV UV_NO_SYNC=1
ENV PYTHONPATH=/app/src

# Health check — verify Python can import the package
HEALTHCHECK --interval=300s --timeout=10s --retries=1 \
    CMD ["python", "-c", "import henri"]

# Default entry point
ENTRYPOINT [".venv/bin/python", "-m", "henri"]
