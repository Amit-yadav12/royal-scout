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

Apply Supabase migrations in numeric order (`0001` through `0009`) before enabling production processing. `SUPABASE_SECRET_KEY` is preferred; the legacy `SUPABASE_SERVICE_ROLE_KEY` JWT remains a fallback. New `sb_secret_*` credentials must not be used as Bearer tokens. Never commit credential files or expose server-only secrets under `NEXT_PUBLIC_` names.

The dashboard's checked-in `web/src/data/bundle.json` remains a display snapshot. Production processing publishes bundles and outputs to private Supabase Storage; replacing the build-time snapshot is a separate reviewed release operation.
