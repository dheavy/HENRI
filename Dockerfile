FROM python:3.13-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files and install deps first (layer caching)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Install Playwright and its system dependencies
RUN uv run playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 henri \
    && chown -R henri:henri /app

# Copy source
COPY --chown=henri:henri . .

USER henri

# Default command
ENTRYPOINT ["uv", "run", "python", "-m", "henri"]
