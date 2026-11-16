# Royal Scout worker — Python analytics + ingestion engine
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    RS_STORAGE_ROOT=/data/storage

WORKDIR /app

# libpq is only needed if you switch the queue to psycopg; kept lean otherwise.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY royalscout ./royalscout

RUN useradd --create-home --uid 10001 worker \
    && mkdir -p /data/storage && chown -R worker:worker /data /app
USER worker

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-8080}/health" || exit 1

# Two processes: the HTTP API (for job submission/status) and the polling worker.
CMD ["sh", "-c", "python -m royalscout.cli serve --host 0.0.0.0 --port ${PORT:-8080} & python -m royalscout.cli worker --storage ${RS_STORAGE_ROOT} --interval 5"]
