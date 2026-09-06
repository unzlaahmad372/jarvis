# ── Stage 1: build dependencies ───────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY app/ app/

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -e "." --target /build/deps

# ── Stage 2: runtime ───────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# Non-root user for security
RUN groupadd -r jarvis && useradd -r -g jarvis jarvis

# Copy installed packages
COPY --from=builder /build/deps /usr/local/lib/python3.12/site-packages/
COPY --from=builder /build/app ./app

# Data directories
RUN mkdir -p data/database data/indexes data/documents data/inbox data/backups data/cache \
    && chown -R jarvis:jarvis /app

USER jarvis

ENV JARVIS_RUNTIME_MODE=container \
    JARVIS_HOST=0.0.0.0 \
    JARVIS_PORT=8000 \
    JARVIS_DATA_DIR=/app/data \
    JARVIS_DATABASE_URL=sqlite+aiosqlite:////app/data/database/jarvis.db

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live')"

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-config", "none"]
