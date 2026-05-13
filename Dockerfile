# syntax=docker/dockerfile:1.7

# --- base builder ------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system deps needed to build any wheels, then prune.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

# --- runtime image -----------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

# Create unprivileged user
RUN groupadd --system repopulse && useradd --system --gid repopulse --home /app repopulse

WORKDIR /app

COPY --from=builder /install /usr/local
COPY src ./src
COPY pyproject.toml README.md ./

# Writable data directory for the SQLite database
RUN mkdir -p /app/data && chown -R repopulse:repopulse /app
USER repopulse

EXPOSE 8000

# Default env — override via docker run -e or compose.
ENV WEBHOOK_HOST=0.0.0.0 \
    WEBHOOK_PORT=8000 \
    DATABASE_PATH=/app/data/repopulse.db \
    LOG_LEVEL=INFO

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request, sys; \
import os; \
port=os.environ.get('WEBHOOK_PORT','8000'); \
urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=3).read(); \
sys.exit(0)" || exit 1

CMD ["python", "-m", "repopulse"]
