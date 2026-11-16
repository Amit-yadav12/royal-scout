# Worker setup

The worker is where all heavy work happens: staged uploads, safe archive extraction, table
detection, canonicalisation, analytics, exports. Vercel only ever enqueues and polls.

## Processes

```bash
# 1) HTTP API — accepts uploads, creates jobs, serves status to the dashboard
WORKER_SHARED_SECRET=… python3 -m royalscout.cli serve --port 8080

# 2) Job worker — claims queued jobs and runs the pipeline
python3 -m royalscout.cli worker --interval 5

# 3) One-shot (CI / smoke test): process at most one job then exit
python3 -m royalscout.cli worker --once --max-jobs 1
```

Both processes share the queue (`LocalQueue` on disk, or `SupabaseQueue` when
`SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` + `RS_USE_SUPABASE_QUEUE=1` are set).

## API surface

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/health` | none | status, storage writability, queue backend, limits |
| `POST` | `/ingest` | `X-Worker-Secret` | multipart upload → staged files → job |
| `POST` | `/jobs` | `X-Worker-Secret` | create a job from existing storage/local paths |
| `GET` | `/jobs` | `X-Worker-Secret` | recent jobs (optionally by project) |
| `GET` | `/jobs/{id}` | `X-Worker-Secret` | job record incl. logs and progress |
| `POST` | `/jobs/{id}/retry` | `X-Worker-Secret` | reset a failed job to `queued` |
| `GET` | `/datasets/{project}/{dataset}/bundle` | `X-Worker-Secret` | the analytical bundle JSON |
| `POST` | `/analyse` | `X-Worker-Secret` | synchronous analysis of stored paths (small jobs only) |

If `WORKER_SHARED_SECRET` is unset the API **refuses** submissions with `503` rather than
running unauthenticated — verified in this repository's smoke tests.

## Job lifecycle

```
queued ──claim──► running ──pipeline──► succeeded
                    │                      ▲
                    └──exception──► failed ┘ (retried while attempts < max_attempts)
```

* `attempts` increments on every claim; `max_attempts` defaults to 3.
* Progress is written back on each pipeline stage (`queue.log`) and to `processing_logs`, so
  the dashboard's progress bar reflects real work, not a timer.
* A crashed worker leaves a `running` row; `requeue_stale_jobs()` in SQL, or the same rule in
  `db.py`, returns it to `queued`.
* Failures keep the traceback in `error` and the last stage in `detail`; nothing is swallowed.

Observed run on the fixture dataset:

```
[job job_9673a5aef02d4731]  22.0% reading files: 3 of 7 files read
[job job_9673a5aef02d4731]  89.0% testing ranking stability: perturbing weights, priors and eligibility floors
[job job_9673a5aef02d4731] 100.0% complete: 30 batters / 29 bowlers ranked
[worker] job job_9673a5aef02d4731 succeeded
```

## Scaling notes

* Workers are stateless apart from `RS_STORAGE_ROOT`; run N replicas, the claim is atomic.
* Cap concurrency by memory: one Polars job peaks near 300 MB for a mid-sized archive. On a
  1 GB worker run a single replica.
* Keep `RS_MAX_EXTRACTED_BYTES` below the volume size, and mount the volume at
  `RS_STORAGE_ROOT` so a restart does not silently lose staging files mid-job.
* The pipeline is deterministic: the same inputs + same `config_fingerprint` produce the same
  bundle, which is what makes exports reproducible.

## Operations runbook

| Symptom | Check | Action |
| --- | --- | --- |
| `/api/ingest` returns 503 | `WORKER_API_URL` set on Vercel? | set it, redeploy |
| 401 from worker | secrets differ | rotate both sides to the same value |
| job stuck at `running` | worker crashed? | `requeue_stale_jobs()`, then check worker logs |
| job `failed` with `IngestionError: pdfplumber` | PDF support missing | `pip install pdfplumber` (never patch around it) |
| disk full | `df -h $RS_STORAGE_ROOT` | raise the volume, prune `staging/` |
| rankings empty after a run | eligibility floors not met | expected: the UI lists every excluded player with the reason |

## Local test recipe (no Supabase)

```bash
cd engine
python3 - <<'PY'
from pathlib import Path
from royalscout.db import LocalQueue, Job
q = LocalQueue(Path('../storage/queue'))
q.create(Job(id='job_local_1', project_id='royal-scout-demo', dataset_id='ds_local',
             dataset_name='Local smoke', sources=[{"local_path": str(Path('../data/demo/fixture_ball_by_ball.csv').resolve())}],
             is_fixture=True))
PY
python3 -m royalscout.cli worker --once --storage ../storage --max-jobs 1
```
