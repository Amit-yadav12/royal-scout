# Worker setup

FastAPI and the background worker are deployed together from `engine/Dockerfile` in the Render service. The Dockerfile starts the API on the assigned `PORT` and one sequential worker; it supervises both, and failure of either process exits the container. Use [Render setup](../RENDER_SETUP.md) for exact dashboard settings.

For local development, run from `engine/`:

```bash
RS_ENV=development RS_USE_SUPABASE_QUEUE=0 RS_STORAGE_ROOT=../storage \
  python -m royalscout.cli serve --host 0.0.0.0 --port 8080
RS_ENV=development RS_USE_SUPABASE_QUEUE=0 RS_STORAGE_ROOT=../storage \
  python -m royalscout.cli worker --once --storage ../storage
```

Production queue claims use the PostgreSQL `claim_processing_job()` RPC with `FOR UPDATE SKIP LOCKED`, and progress records are in `processing_logs`. The worker invokes `requeue_stale_jobs()` at startup and checks again once per minute, so stale jobs recover without requiring a further manual restart; attempt limits are enforced by the claim RPC and retry endpoint. The Vercel status route reads the job and progress logs directly from Supabase, so status remains available if the worker API is restarting. It still checks that the signed-in user owns the job. Production jobs require private Storage bucket/object references; local filesystem paths and direct `/ingest` upload bodies are disabled in production.

Endpoints: `/health/live` reports API process liveness; `/health/ready` checks Supabase queue/table, artifact bucket, key configuration, worker shared secret and temporary storage. `/jobs` operations require the `X-Worker-Secret` header, sent only by Vercel server routes. Job status includes progress, stage and bounded retry failure state. The required bundle must upload to private Storage before a remote job succeeds.

Render Free is a demo environment: it sleeps after inactivity, uses ephemeral storage, and has limited CPU/RAM. It does not guarantee completion of long-running processing. Worker downloads are streamed, jobs run sequentially, temporary staging is cleaned, and stale jobs are requeued, but use an always-on adequately sized instance for dependable production processing.
