# Deployment

The canonical deployment instructions are now split by platform:

- [Render setup](../RENDER_SETUP.md)
- [Vercel setup](../VERCEL_SETUP.md)
- [Supabase setup](../SUPABASE_SETUP.md)
- [Production environment](../PRODUCTION_ENVIRONMENT.md)
- [Troubleshooting](../DEPLOYMENT_TROUBLESHOOTING.md)
- [Architecture](../DOCUMENTED_ARCHITECTURE.md)

Render's required configuration is Root Directory `engine`, Dockerfile Path `Dockerfile`, Docker Context `.`, Docker runtime, blank Start Command, and readiness path `/health/ready`. The image supervises API plus one sequential worker. Render Free sleeps and has ephemeral storage; use `/tmp/royal-scout` only for processing temp files, not persistent output.

Vercel uses Root Directory `web`, Next.js, `npm ci`, and `npm run build`. Large files upload directly from the authenticated browser to private Supabase Storage over resumable TUS. Server routes verify ownership via `upload_claims` and forward small object references to Render using `X-Worker-Secret`.

Apply Supabase migrations `0001` through `0009` and `20261116171951_lock_profile_role_updates` before enabling production processing. `SUPABASE_SECRET_KEY` is preferred; the legacy `SUPABASE_SERVICE_ROLE_KEY` JWT remains a fallback. New `sb_secret_*` credentials must not be used as Bearer tokens. Never commit credential files or expose server-only secrets under `NEXT_PUBLIC_` names.

Production dashboard requests query the latest successful processing job (or the staff-selected historical dataset) and fetch its `bundle.json` from the private `royal-scout-artifacts` bucket using server-only credentials. Every analytics route and CSV export uses that same request-time selection. The selector is backed by successful `processing_jobs` rows; failed/running jobs are not selectable. `web/src/data/bundle.json` is used only as a visibly labelled local-development fallback. Production does not fall back to it when live configuration or an artifact is missing.
