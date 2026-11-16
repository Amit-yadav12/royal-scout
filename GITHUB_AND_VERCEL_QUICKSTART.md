# GitHub + Vercel quick start

## Before you upload

- Keep the GitHub repository **private**. The included `web/src/data/bundle.json`, reports and selection exports contain derived proprietary scouting information.
- The raw proprietary source ZIP is provided separately from this release archive. Upload it through the app from your local machine, or place it locally under `data/private/` (Git-ignored). The `data/real/` extracted raw files are also ignored. Do not force-add either directory.
- Do not share the deployed dashboard until Supabase Auth or Vercel Deployment Protection is enabled.

## 1. Create a private GitHub repository

Extract this project ZIP. Open a terminal in the extracted `royal-scout` folder and run:

```bash
git init
git add .
git status --short
```

Review the staged file list. Confirm that no `.env`, service-role key, worker secret, `data/private/`, or `data/real/` file is staged. Then:

```bash
git commit -m "Prepare Royal Scout dashboard for deployment"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_PRIVATE_REPOSITORY.git
git push -u origin main
```

Create the GitHub repository as **Private** before pushing.

## 2. Deploy the dashboard to Vercel

1. Import the private GitHub repository into Vercel.
2. Set **Root Directory** to `web`.
3. Select the **Next.js** framework preset.
4. Select **Node.js 22.x**.
5. Use `npm ci` as the install command and `npm run build` as the build command.
6. Add the Vercel variables documented in `.env.example` and `docs/ENV_SETUP.md`.
7. Deploy and check `/api/health`.

In production, the dashboard stays locked at `/login` until the Supabase URL and publishable key are configured. Upload and processing remain disabled until the full worker configuration is complete. Do not deploy this proprietary snapshot as an unauthenticated public site.

## 3. Enable secure uploads and processing

1. Create a Supabase project and run all SQL files in `supabase/migrations/` in numerical order.
2. Confirm private buckets `uploads`, `royal-scout-artifacts`, and `fixtures` exist.
3. Deploy the Python API and background worker from `engine/Dockerfile` using the two start commands in `docs/DEPLOYMENT.md`.
4. Configure the same `WORKER_SHARED_SECRET` on Vercel and both worker services.
5. Configure Supabase URL and the service-role key on the server/worker only. Never use `NEXT_PUBLIC_` for a secret.
6. Configure Vercel `WORKER_API_URL`, `WORKER_SHARED_SECRET`, `SUPABASE_UPLOAD_BUCKET`, and `SUPABASE_ARTIFACT_BUCKET`.
7. Confirm `/api/health` returns `uploads_enabled: true`.
8. Sign in, upload a small test CSV, verify its job succeeds, and verify artifact links appear. Only then upload the full cricket source ZIP.

File bytes travel directly from the browser to private Supabase Storage through resumable TUS uploads. They do not pass through Vercel Functions.

## 4. Publish a newly analysed dataset

A successful processing job stores the analytical bundle in private Storage. The authenticated dashboard selects the newly completed dataset at request time and offers processed dataset history; no bundle copy, Git commit, or Vercel rebuild is required. Review the data-quality report and 10+10 shortlist before using any recommendation. The fixed audited shortlist is shown only when its source dataset ID is selected.

The official SupeRR Selector candidate dropdown was not present in the uploaded source archive. Import that exact candidate list and verify auction availability before treating the final 10+10 as submission-ready.

## 5. Local checks

From the project root:

```bash
cd web
npm ci
npm run typecheck
npm test
npm run build
```

In another terminal:

```bash
cd engine
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements-dev.txt
PYTHONPATH=. python -m pytest tests -q
```

Live deployment still requires your own Supabase, worker-host and Vercel accounts/credentials. No external service is preconfigured by this ZIP.
