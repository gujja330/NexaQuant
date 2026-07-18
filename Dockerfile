# AEGIS · Production Image
#
# Multi-purpose Python image that can run any of:
#   - scripts/aegis_daily_v2.py     (daily orchestrator)
#   - ux/dashboard/frontend/serve.py (dashboard)
#   - scripts/aegis_health_check.py  (health probe)
#
# The default CMD serves the dashboard on port 8765.
# Override CMD for one-shot orchestrator runs (see docker-compose.yml).

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONIOENCODING=utf-8 \
    TZ=Asia/Kolkata

# System packages: git for code_sha stamps, tzdata for IST clock
RUN apt-get update && apt-get install --no-install-recommends -y \
        git tzdata ca-certificates \
    && ln -fs /usr/share/zoneinfo/$TZ /etc/localtime \
    && dpkg-reconfigure --frontend noninteractive tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first for layer caching
COPY requirements.txt ./
COPY requirements-dashboard.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -r requirements-dashboard.txt

# Source
COPY . .

# Non-root user
RUN useradd -m -u 1000 aegis \
    && chown -R aegis:aegis /app
USER aegis

EXPOSE 8765

# Default: serve the dashboard
CMD ["python", "ux/dashboard/frontend/serve.py"]
