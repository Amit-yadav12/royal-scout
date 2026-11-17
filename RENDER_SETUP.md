# Render setup

Create a **Docker Web Service** from this repository. Configure the existing deployment as follows:

- Root Directory: `engine`
- Dockerfile Path: `Dockerfile`
- Docker Context Directory: `.`
- Runtime: Docker
- Start Command: leave blank (the Dockerfile supervises FastAPI and the sequential worker)
- Health Check Path: `/health/ready`
- Instance: free is suitable only for demonstration/QA; use paid always-on compute for dependable long jobs.

Set the Render variables from the Render section in `.env.example`, particularly `RS_ENV=production`, `RS_STORAGE_ROOT=/tmp/royal-scout`, `RS_USE_SUPABASE_QUEUE=1`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, both bucket names, and `WORKER_SHARED_SECRET`. The secret must match Vercel exactly. Set the worker's assigned port automatically via `PORT`; do not hard-code it.

The container runs the API and one sequential queue worker as supervised child processes. Failure of either exits the container. SIGTERM requests graceful worker shutdown after its current job. Health liveness is `/health/live`; readiness verifies Supabase REST access to `processing_jobs`, Storage bucket reachability, credentials, queue configuration, shared secret presence, and writable temporary storage.

Render free services sleep after inactivity and use ephemeral filesystems. `/tmp/royal-scout` is disposable staging only. Inputs and final outputs live in private Supabase Storage. Do not promise uninterrupted processing on a free instance; long jobs can be interrupted by sleep/restarts, and stale running jobs are recovered by periodic database RPC checks from the worker. A test after cold start: open `/health/ready`, authenticate in Vercel, upload a small fixture, submit, and follow its job status until terminal. Never use `/ingest` for production large uploads.

Code changes under `engine/` and the root Docker/engine requirements trigger the Render deployment. Supabase SQL changes require applying the new migration separately before deploying code that depends on it.
