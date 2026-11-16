# Production environment templates

Copy the matching section in `.env.example` into deployment secret settings; do not commit `.env`, `.env.local`, or actual credential values. Vercel and Render must use the same Supabase project, bucket names, and `WORKER_SHARED_SECRET`. Set the preferred `SUPABASE_SECRET_KEY=sb_secret_...`; the old `SUPABASE_SERVICE_ROLE_KEY` remains a legacy fallback only. The preferred key wins if both exist.

Render uses `RS_ENV=production`, `RS_STORAGE_ROOT=/tmp/royal-scout` and `RS_USE_SUPABASE_QUEUE=1`. Vercel's `SUPABASE_SECRET_KEY` and `WORKER_SHARED_SECRET` must be server-only. Production analytics load the selected successful bundle from private Storage at request time; the checked-in `web/src/data/bundle.json` is only an explicitly labelled local-development fallback. Long-lived inputs/outputs belong in private Storage; Render disk is ephemeral.

The `.env.example` includes Vercel, Render, and local-development sections. Its values are examples only. Local development can choose LocalQueue; production fails closed rather than silently using a per-instance local queue.
