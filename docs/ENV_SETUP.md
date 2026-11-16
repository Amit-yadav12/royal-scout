# Environment setup

Two runtimes, two sets of variables. `.env.example` at the repository root is the
template — copy it and **never commit real values**.

* **web** (`Vercel`) → `web/.env.local`
* **worker** (`Railway` / `Render`) → service environment variables

Variables are read at runtime on the server. Anything prefixed `NEXT_PUBLIC_` is compiled
into the browser bundle: only the Supabase URL and publishable key may live there.

---

## Web (Vercel)

| Variable | Required | Purpose |
| --- | --- | --- |
| `NEXT_PUBLIC_SUPABASE_URL` | for auth/uploads | Supabase project URL. |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | for auth/uploads | Public publishable/anon key used by browser Storage TUS requests and auth middleware. |
| `NEXT_PUBLIC_APP_URL` | recommended | Absolute origin used for magic-link redirects. |
| `SUPABASE_SERVICE_ROLE_KEY` | for signed uploads | Server-only key used to mint signed upload tokens. Never expose. |
| `SUPABASE_UPLOAD_BUCKET` | for uploads | Private source-file bucket. Defaults to `uploads`. |
| `SUPABASE_ARTIFACT_BUCKET` | for private downloads | Private worker-export bucket. Defaults to `royal-scout-artifacts`. |
| `WORKER_API_URL` | for uploads | Base URL of the FastAPI worker. Unset ⇒ uploads are disabled. |
| `WORKER_SHARED_SECRET` | for uploads | Secret sent as `X-Worker-Secret`; must match the worker's value. |
| `ROYAL_SCOUT_PROJECT_ID` | optional | Project id used for uploads; defaults to `royal-scout`. |
| `RS_MAX_FILES_PER_UPLOAD` | optional | Maximum number of files in one upload batch. |
| `RS_MAX_UPLOAD_FILE_BYTES` | optional | Maximum browser-selected file size in bytes; must not exceed the bucket/provider limit. |
| `RS_MAX_UPLOAD_TOTAL_BYTES` | optional | Maximum combined upload batch size in bytes. |

In local development, the dashboard can be previewed without Supabase as a read-only snapshot. In production, middleware fails closed and redirects to `/login` until Supabase URL and publishable key are configured. Secure uploads additionally require the service-role key, private buckets, worker URL and shared secret.

## Worker (Railway / Render)

| Variable | Required | Purpose |
| --- | --- | --- |
| `SUPABASE_URL` | yes (prod) | Project URL for the queue, Storage and metadata. |
| `SUPABASE_SERVICE_ROLE_KEY` | yes (prod) | Server-side only. Bypasses RLS by design. |
| `SUPABASE_ARTIFACT_BUCKET` | recommended | Bucket for bundles and exports (private). Default `royal-scout-artifacts`. |
| `SUPABASE_UPLOAD_BUCKET` | yes (uploads) | Private source-file bucket. Default `uploads`. |
| `RS_STORAGE_ROOT` | yes | Working directory for staging/extraction. Needs free disk ≥ the extraction limit. |
| `RS_USE_SUPABASE_QUEUE` | default `1` | `0` forces the JSON file queue (local development). |
| `RS_ENV` | required in production | Set to `production`; disables local queue fallback. |
| `WORKER_SHARED_SECRET` | yes | Authenticates protected `/ingest`, `/jobs`, `/jobs/{id}` and bundle-read endpoints. Unset ⇒ the API refuses submissions (`503`) instead of running unauthenticated. |
| `RS_MAX_FILE_BYTES` | default 2 GiB | Reject a single oversized file. |
| `RS_MAX_EXTRACTED_BYTES` | default 20 GiB | Total extraction budget per job. |
| `RS_MAX_ARCHIVE_ENTRIES` | default 5000 | Entry count ceiling (zip-bomb defence). |
| `RS_MAX_FILES_PER_UPLOAD` | default 5000 | Upload ceiling per request. |
| `RS_MAX_NESTED_DEPTH` | default 3 | Nested archive recursion limit. |
| `RS_MAX_COMPRESSION_RATIO` | default 200 | Per-entry expansion ratio ceiling. |

Optional PDF support needs `pdfplumber`; 7z needs `py7zr`. Both are in
`engine/requirements.txt`. If a library is missing the engine raises a named
`IngestionError` — it never silently skips a file.

---

## Generating secrets

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # WORKER_SHARED_SECRET
```

Rotate the worker secret by updating both sides at once; jobs are unaffected because the
secret only authenticates HTTP calls, it is not stored with job payloads.

## Verifying configuration

```bash
curl -s http://localhost:3000/api/health | jq
```

```json
{
  "web": "ok",
  "worker": "ok",
  "configured": {
    "supabase_url": false,
    "supabase_publishable_key": false,
    "supabase_service_role": false,
    "worker_api_url": true,
    "worker_shared_secret": true,
    "app_url": false
  }
}
```

The health route never echoes a key — only booleans — and distinguishes ready, degraded, unreachable and not-configured states. `uploads_enabled` is true only when the full signed-upload and worker configuration is present and the worker is ready.
