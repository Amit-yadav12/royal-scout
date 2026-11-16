# Royal Scout Intelligence Hub

> **Every Player. Every Metric. Every Insight.**

Royal Scout is a Next.js scouting dashboard paired with a Python ingestion and cricket analytics engine. It analyses batting, bowling, match situations, consistency, reliability and statistical uncertainty, then produces independent batting and bowling leaderboards.

**Important data notice:** this project contains a proprietary competition dataset snapshot and derived scouting outputs. Keep the GitHub repository private unless you have explicit permission to publish the supplied data and derived analysis. The raw source ZIP is deliberately distributed separately from this GitHub release archive; keep it outside the repository or place it locally under `data/private/` (Git-ignored) before using the upload flow. Extracted files under `data/real/` are also ignored by Git. The local-development snapshot in `web/src/data/bundle.json` contains derived player analytics and must also be treated as restricted. Production access fails closed unless Supabase Auth is configured; local development can preview the read-only snapshot.

## What the project contains

| Area | Implementation |
| --- | --- |
| Web application | Next.js 15 App Router, React and TypeScript |
| Data ingestion | CSV, TSV, spreadsheets, JSON, XML, Parquet, Feather, PDF/DOCX tables and nested archives where supported |
| Cricket data model | Match, innings, ball-event, batting and bowling records with source provenance |
| Analytics | Batting/bowling metrics, phase and competition splits, pressure scenarios, confidence and stability analysis |
| Rankings | Separate batter and bowler leaderboards, with eligibility and sample-size rules |
| Storage | Supabase Postgres and private Supabase Storage buckets |
| Background work | FastAPI worker API plus a separate processing worker |
| Deployment | Next.js frontend on Vercel; Python worker on Railway or Render |
| Exports | Authenticated live CSV exports and short-lived signed downloads for worker-generated CSV, Excel and PDF artefacts |

Production analytics load the selected successfully processed job's bundle directly from private Supabase Storage at request time. The dataset selector/history reads the existing Supabase processing queue, and a completed upload can become active without rebuilding Vercel. `web/src/data/bundle.json` is retained only as an explicitly labelled local-development snapshot; production fails closed rather than silently substituting it. Generated downloads use authenticated access or short-lived signed URLs; worker files are never placed in a public web folder.

Auction availability is not inferred from historical match participation. Player eligibility and future auction availability must be checked against the official candidate list and current verified auction information before a final submission is made.

## Repository layout

```text
engine/                 Python ingestion, cricket analytics, API and worker
  royalscout/           Canonical model, metrics, pressure, rankings and exports
  tests/                Unit and integration tests
web/                    Next.js application (Vercel root directory)
  src/app/              Dashboard pages and API routes
  src/components/       Tables, charts, upload flow and UI components
  src/data/bundle.json  Local-development snapshot only (not used for production data selection)
supabase/migrations/    Database schema, queue, RLS and private storage buckets
data/demo/              Clearly labelled synthetic fixtures for tests/demo
data/private/           Optional local-only folder for the original ZIP; ignored by Git and not shipped
reports/                Analysis outputs and methodology material
scripts/                Dataset helpers and local scripts
docs/                    Database, environment, worker, processing and deployment guides
```

## Local dashboard quickstart

Requires Node.js 20.9+ (Node 22 LTS recommended) and npm compatible with the lockfile. The Next.js dependency is pinned to 15.5.29, the patched 15.x maintenance release selected for this package.

```bash
cd web
npm ci
npm run typecheck
npm test
npm run build
npm start
```

Open `http://localhost:3000`. Local development without Supabase Auth can preview the read-only snapshot. A production deployment remains locked behind `/login` until Supabase Auth is configured; secure uploads also require the worker stack.

## Python analytics quickstart

Use Python 3.11+ (check the pinned package compatibility for your environment).

```bash
cd engine
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements-dev.txt
PYTHONPATH=. python -m pytest tests -q
```

To run a local analysis from local files:

```bash
cd engine
PYTHONPATH=. python -m royalscout.cli ingest \
  --paths ../data/demo/fixture_scouting_archive.zip ../data/demo/fixture_ball_by_ball.csv \
  --project royal-scout-demo --dataset-id ds_fixture_demo \
  --name "RR Scouting — Synthetic Demonstration Dataset" --fixture
```

Synthetic fixtures are for testing only. They must never be mixed into production player rankings or presented as actual scouting evidence.

## Production deployment

Follow the complete instructions in [`GITHUB_AND_VERCEL_QUICKSTART.md`](GITHUB_AND_VERCEL_QUICKSTART.md) and [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md). The deployment is split deliberately:

1. Supabase: Auth, Postgres queue and private Storage.
2. Railway/Render: Python worker API and background worker.
3. Vercel: Next.js dashboard with **Root Directory `web`**.

Large file bytes are uploaded by the browser directly to a short-lived signed Supabase Storage URL. Vercel receives only file metadata and storage paths; it does not proxy the file body through a Function.

## Checks before releasing

- Apply all migrations through `0006_private_storage_buckets.sql`.
- Confirm `/api/health` reports `uploads_enabled: true` after production environment variables are configured.
- Sign in with an authorised Supabase Auth account. Do not share the Vercel deployment until authentication/protection is enabled; without Supabase configuration the viewer runs in read-only demo mode.
- Upload a small test file, verify it lands in the private bucket, then verify that the worker job succeeds.
- Validate the real-data processing output and data-quality report.
- Verify that the deployed bundle has the intended `dataset_id` and `is_fixture: false`.
- Confirm the final 10+10 names against the official competition dropdown; historical dataset membership does not prove auction availability.

## Security

Never commit `.env`, `.env.local`, database passwords, Supabase service-role keys, worker secrets, or private access tokens. Do not expose the service-role key through a `NEXT_PUBLIC_` variable. Keep proprietary dataset and derived scouting outputs in a private repository and a private Vercel deployment unless disclosure is expressly permitted.
