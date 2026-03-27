FROM python:3.13-slim

# Install system deps for Playwright and general build
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 \
    libpango-1.0-0 libcairo2 libasound2 libxshmfence1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Install Playwright browsers
RUN uv run playwright install chromium

# Create non-root user
RUN useradd -m -u 1000 henri
RUN chown -R henri:henri /app

# Copy source
COPY --chown=henri:henri . .

USER henri

# Default command
ENTRYPOINT ["uv", "run", "python", "cli.py"]
