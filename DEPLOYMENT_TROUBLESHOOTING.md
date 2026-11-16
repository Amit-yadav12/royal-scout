# Deployment troubleshooting

- **Supabase 401 / invalid API key:** confirm the project URL and server key belong to the same project, remove whitespace, set `SUPABASE_SECRET_KEY` (or legacy service-role JWT), and redeploy. New `sb_secret_*` values are sent as `apikey` only. Publishable keys are rejected by server helpers. Logs report only key type, never key contents.
- **403:** check server key role and that migration/RPC grants are applied. Do not expose the key or broaden anonymous RLS.
- **404 `processing_jobs`:** apply the complete ordered migration set. Readiness reports queue inaccessible without exposing upstream response bodies.
- **Missing Storage bucket / object:** verify private bucket IDs match environment variables and the signed upload completed before submitting. A missing source fails the job; the worker does not treat zero downloads as success.
- **Queue unavailable / worker unavailable:** inspect Render logs and `/health/ready`; verify shared-secret presence and matching server-side Vercel value. Browser requests must not contain `X-Worker-Secret`.
- **Render timeout / sleeping free service:** allow cold start, then retry `/api/health`. Free services sleep and have ephemeral storage; do not use them for guaranteed long-running processing.
- **Failed job:** status includes stage/error and logs; retry only after fixing source/configuration. Max attempts are tracked in PostgreSQL. The final bundle must upload successfully before success is recorded.
- **Upload issues:** confirm auth session, private `uploads` bucket, file-size constraints, and browser-to-Supabase TUS connectivity/CORS. Vercel routes issue signatures only; large bytes must not be posted to Vercel.
