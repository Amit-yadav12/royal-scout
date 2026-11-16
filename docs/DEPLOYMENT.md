# Production Deployment — Royal Scout

Royal Scout is a small Next.js application plus a separate Python ingestion/analytics worker. Vercel serves the dashboard and signs short-lived upload URLs. Browser file bytes go **directly to private Supabase Storage**; the Vercel Functions receive only small JSON metadata. The worker reads storage objects, processes files, and publishes analytical artefacts back to private Storage.

```text
Browser ───────────────► Supabase Storage (private `uploads` bucket)
   │                     ▲
   │ small JSON          │ signed URL minted by server
   ▼                     │
Vercel / Next.js ─────────┘
   │ POST /api/jobs (small storage references)
   ▼
Worker API ──► Supabase Postgres queue ──► Worker process
                                             │
                                             ├─ download private source objects
                                             ├─ extract / validate / analyse
                                             └─ publish bundle + exports
                                                  to `royal-scout-artifacts`
```

This design keeps large upload bodies away from Vercel Functions, whose documented request/response payload limit is 4.5 MB. Supabase Storage signed uploads are used so the browser never receives the service-role key. See the [Vercel Function limits](https://vercel.com/docs/functions/limitations) and [Supabase signed upload documentation](https://supabase.com/docs/reference/javascript/file-buckets-createsigneduploadurl).

## 1. Supabase setup

1. Create a Supabase project.
2. Apply every SQL migration in `supabase/migrations/` in numeric order, including `0006_private_storage_buckets.sql`.
3. Confirm these private buckets exist:
   - `uploads`
   - `royal-scout-artifacts`
   - `fixtures`
4. In Storage settings, set an upload file-size limit appropriate for your Supabase plan and expected archive size. The application defaults are 2 GB per file and 10 GB per batch, but provider/project limits can be lower.
5. Enable the authentication method you intend to use and create authorised staff accounts. Upload signing and job creation require a valid signed-in user.
6. Copy the project URL, publishable/anon key and service-role key. Keep the service-role key server-side only.

The bucket policies are intentionally private. Vercel checks the user session and mints short-lived signed upload tokens with the service-role key. The browser transfers large files directly to Supabase Storage using the signed TUS resumable-upload endpoint (6 MB chunks with retries); smaller files use the same direct storage path. The browser never receives the service-role key. The worker uses the service-role key to download sources and publish outputs.

## 2. Worker deployment (Railway or Render)

Use `engine/Dockerfile` and the included Railway configuration as the starting point. Run two services from the same image:

| Service | Start command | Purpose |
| --- | --- | --- |
| `worker-api` | `python -m royalscout.cli serve --port $PORT` | Health, job creation and job status |
| `worker-jobs` | `python -m royalscout.cli worker --interval 5` | Claims jobs and runs ingestion/analytics |

Set these environment variables on **both** services:

```env
RS_ENV=production
RS_STORAGE_ROOT=/data/storage
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY
SUPABASE_ARTIFACT_BUCKET=royal-scout-artifacts
SUPABASE_UPLOAD_BUCKET=uploads
RS_USE_SUPABASE_QUEUE=1
WORKER_SHARED_SECRET=LONG_RANDOM_SECRET_SHARED_WITH_VERCEL
RS_MAX_FILE_BYTES=2147483648
RS_MAX_EXTRACTED_BYTES=21474836480
RS_MAX_ARCHIVE_ENTRIES=5000
RS_MAX_FILES_PER_UPLOAD=200
```

Attach persistent storage to the **worker-jobs** service at `/data/storage` for extracted files, intermediate Parquet and output artefacts. The queue and original upload objects are in Supabase, so the API and jobs services do not need to share a local filesystem. The API service also needs a writable `RS_STORAGE_ROOT` for health checks and temporary runtime files.

In production the worker refuses to fall back to a local JSON queue. `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` and `RS_USE_SUPABASE_QUEUE=1` are required so both services use the same Postgres queue.

Health check: `GET https://YOUR_WORKER_DOMAIN/health`. It must report `ready: true`, `queue: SupabaseQueue`, `storage_writable: true` and `shared_secret_configured: true`.

## 3. Vercel deployment

1. Push the project to a **private GitHub repository**. The project includes a proprietary competition dataset snapshot and derived scouting results. Do not make the repository public unless you have explicit permission to disclose those materials.
2. Import the repository into Vercel.
3. Set **Root Directory** to `web`.
4. Set the Vercel Node.js runtime to **22.x** (the package requires Node 20.9+).
5. Framework preset: Next.js. Build command: `npm run build` (or the Vercel default). Install command: `npm ci`.
6. Add the following Vercel environment variables for Production and Preview as appropriate:

```env
NEXT_PUBLIC_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=YOUR_PUBLISHABLE_OR_ANON_KEY
NEXT_PUBLIC_APP_URL=https://YOUR_VERCEL_DOMAIN
SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY
SUPABASE_UPLOAD_BUCKET=uploads
SUPABASE_ARTIFACT_BUCKET=royal-scout-artifacts
WORKER_API_URL=https://YOUR_WORKER_API_DOMAIN
WORKER_SHARED_SECRET=THE_SAME_LONG_RANDOM_SECRET_AS_THE_WORKER
ROYAL_SCOUT_PROJECT_ID=royal-scout
RS_MAX_FILES_PER_UPLOAD=200
RS_MAX_UPLOAD_FILE_BYTES=2147483648
RS_MAX_UPLOAD_TOTAL_BYTES=10737418240
```

Never prefix the service-role key or worker secret with `NEXT_PUBLIC_`. They must never appear in browser code. Production routes fail closed when the public Supabase URL or publishable key is missing; do not enable an unauthenticated read-only mode for this proprietary data snapshot.

7. Deploy. Open `/api/health`; it must report `worker: "ok"` and `uploads_enabled: true` before uploads are enabled.
8. Sign in using an authorised Supabase Auth user.

## 4. Verify uploads and processing

1. Open Data Ingestion while signed in.
2. Upload a small CSV first.
3. Confirm its bytes upload directly to the private `uploads` bucket.
4. Confirm `/api/jobs` queues the object references in Supabase Postgres.
5. Confirm the worker downloads the objects, processes the job and reports progress.
6. Confirm the job ends in `succeeded` and `result.uploads` reports successful artefact publication.
7. Test the original competition ZIP after the small-file test passes.

The old multipart `/api/ingest` endpoint is deliberately disabled. Do not route file bytes through Vercel Functions. Uploads use signed resumable TUS requests; Supabase recommends TUS for files over 6 MB and supports signed tokens through the `x-signature` header.

## 5. Publish a processed dataset as the dashboard snapshot

The dashboard pages currently consume a **build-time analytical snapshot** at `web/src/data/bundle.json`. A successful ingestion creates and stores a new bundle in Supabase Storage, but does not mutate the deployed Vercel build at runtime. This is intentional: Vercel deployments are immutable and should not write into the application filesystem.

To publish a completed dataset:

```bash
# Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in your local shell.
python scripts/publish_bundle_from_storage.py \
  --project royal-scout \
  --dataset ds_YOUR_DATASET_ID \
  --dry-run

# After the dry run validates the dataset ID and real-data flag:
python scripts/publish_bundle_from_storage.py \
  --project royal-scout \
  --dataset ds_YOUR_DATASET_ID

git add web/src/data/bundle.json
git commit -m "Publish analysed scouting dataset"
git push
```

Vercel will build and deploy the updated dashboard snapshot. The script backs up the previous bundle, checks the dataset ID and refuses to publish a synthetic fixture. It does not update the competition-specific final 10+10 selection file; rerun and review the dedicated SupeRR pressure-ranking analysis before publishing new player picks.

## 6. Troubleshooting

| Symptom | Check |
| --- | --- |
| `/api/health` says worker degraded | Worker health, shared secret, Supabase queue and writable worker storage |
| Secure upload is disabled | Supabase URL, publishable key, service-role key, upload bucket, worker URL and shared secret |
| Sign-in redirect loop | Supabase Auth URL allow-list and `NEXT_PUBLIC_APP_URL` |
| Upload URL signing fails | `uploads` bucket exists; service-role key is correct; bucket/project file-size setting permits the file |
| Storage upload fails | Signed URL expiry, provider size limit, network and bucket availability |
| Job cannot be queued | `processing_jobs` migration, worker API logs, shared secret and Postgres connectivity |
| Job cannot download input | `SUPABASE_URL`, service-role key, correct bucket/path and Storage object presence |
| Job succeeds but page still shows the old metrics | Publish the new stored bundle and redeploy (section 5) |
| Vercel build runs out of memory | Set `NODE_OPTIONS=--max-old-space-size=1300` if the build environment supports it |

## 7. Rollback

The current `web/src/data/bundle.json` remains in the Git history (in the private repository). Restore the previous bundle commit and redeploy. Worker jobs and dataset artefacts are versioned under `project_id/dataset_id`; never overwrite the original upload objects during analysis.
