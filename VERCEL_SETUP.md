# Vercel setup

Create a Next.js project with Root Directory `web`, Framework Preset `Next.js`, Install Command `npm ci`, and Build Command `npm run build`. Install/build settings can remain default if Vercel detects the lockfile. Configure the Vercel variables in `.env.example`: public Supabase URL/publishable key and app URL, plus server-only `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, upload/artifact bucket names, Render `WORKER_API_URL`, the matching `WORKER_SHARED_SECRET`, and `ROYAL_SCOUT_PROJECT_ID`.

Only `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, and `NEXT_PUBLIC_APP_URL` are browser-safe. Never prefix private values with `NEXT_PUBLIC_`. Next server routes verify the Supabase user session, create signed uploads/downloads using the project secret, and proxy job operations to Render with `X-Worker-Secret`. Browser code never receives that worker secret or the Supabase project secret. Current large uploads use direct resumable TUS browser-to-Storage transfer; file bytes do not transit Vercel functions.

Deploys are triggered by changes under `web/` or Vercel environment/build configuration. `/api/health` checks Render `/health/ready`; sleeping or unavailable Render is reported as unavailable/degraded rather than claiming processing is enabled.
