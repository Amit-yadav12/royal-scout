# Royal Scout worker — Python analytics + ingestion engine
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    RS_STORAGE_ROOT=/tmp/royal-scout
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates bash && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY royalscout ./royalscout
RUN useradd --create-home --uid 10001 worker \
    && mkdir -p /tmp/royal-scout && chown -R worker:worker /tmp/royal-scout /app
USER worker
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-8080}/health/live" || exit 1
# Supervise both long-running processes. If either exits, stop the sibling and
# exit non-zero so Render restarts the service rather than silently degrading.
CMD ["bash", "-c", "set -m; python -m royalscout.cli serve --host 0.0.0.0 --port ${PORT:-8080} & api=$!; python -m royalscout.cli worker --storage ${RS_STORAGE_ROOT:-/tmp/royal-scout} --interval 5 & worker=$!; trap 'kill -TERM $api $worker 2>/dev/null || true; wait' TERM INT; wait -n $api $worker; code=$?; kill -TERM $api $worker 2>/dev/null || true; wait $api $worker 2>/dev/null || true; exit $code"]
