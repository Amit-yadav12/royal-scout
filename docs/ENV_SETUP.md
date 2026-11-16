# Environment setup

Use the root [`.env.example`](../.env.example) as a credential-free template. It separates Vercel, Render, and local-development settings. Never commit `.env`, `.env.local`, production keys, or shared secrets.

## Vercel

Required public values: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, and `NEXT_PUBLIC_APP_URL`. Server-only values: `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `SUPABASE_UPLOAD_BUCKET`, `SUPABASE_ARTIFACT_BUCKET`, `WORKER_API_URL`, `WORKER_SHARED_SECRET`, and `ROYAL_SCOUT_PROJECT_ID`. The legacy `SUPABASE_SERVICE_ROLE_KEY` is accepted only as a fallback. Do not pass the private API key or worker shared secret into React/browser code.

## Render

Set `RS_ENV=production`, `RS_STORAGE_ROOT=/tmp/royal-scout`, `RS_USE_SUPABASE_QUEUE=1`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, upload/artifact buckets and the same `WORKER_SHARED_SECRET` as Vercel. Configure processing limits as appropriate for the instance. Render's filesystem is ephemeral; only temporary processing data belongs there.

## Local development

Set `RS_ENV=development`, `RS_STORAGE_ROOT=./storage`, and `RS_USE_SUPABASE_QUEUE=0` to use LocalQueue and local fixture paths. To exercise Supabase, use a private key and project URL in your shell; never check them into the repository. A new `sb_secret_*` key is sent as `apikey` only. A legacy service-role JWT is sent in both `apikey` and `Authorization: Bearer`.

For readiness, use backend `/health/ready` (real database and bucket probes) and Vercel `/api/health` (Render availability). Liveness is `/health/live` and intentionally does not require external services.
