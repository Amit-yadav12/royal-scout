# Royal Scout — GitHub/Vercel Release Notes

## Changes prepared in this release

- Replaced the Vercel multipart file proxy with signed Supabase Storage uploads; Vercel receives metadata and object references only.
- Added resumable TUS uploads using 6 MB chunks and retry/offset recovery for unstable connections.
- Added private source, artifact and fixture storage bucket migration.
- Made production processing fail closed unless both worker services use the Supabase Postgres queue.
- Protected worker job reads and bundle reads with the worker shared secret; the Vercel job-status and artifact-download proxies fail closed unless the signed-in user owns the job.
- Restricted job creation to the configured project and upload bucket, preventing client-supplied bucket references from being used for worker-side object reads.
- Added authenticated 10-minute signed downloads for worker-generated CSV, Excel and PDF artefacts.
- Removed pre-generated reports from the public web directory and protected `/exports/*` paths behind authentication.
- Moved dataset scope options and comparison data into authenticated server-rendered props so the proprietary analytics bundle is not imported into a public client-side JavaScript chunk.
- Made production middleware fail closed when Supabase Auth is not configured; local development may still preview the read-only snapshot.
- Changed auction availability labels so missing verification is displayed as **unverified**, never as confirmed.
- Synchronized the Markdown Top 10 tables with the current canonical CSV selection exports.
- Added a safe bundle-publish helper and refreshed deployment/environment documentation.
- Removed redundant bundled snapshots; `web/src/data/bundle.json` is the one build-time dashboard bundle.
- Upgraded Next.js to the patched 15.5.29 release line and pinned the Node runtime floor to 20.9+ (Node 22 recommended).

## Required configuration before a live deployment

1. Create a Supabase project and apply all migrations in `supabase/migrations/` in numeric order.
2. Confirm private buckets `uploads`, `royal-scout-artifacts` and `fixtures` exist.
3. Deploy the Python worker API and job worker separately, using the same Supabase queue, persistent working storage and shared secret.
4. Set all Vercel environment variables from `.env.example` and `docs/DEPLOYMENT.md`.
5. Set Vercel Root Directory to `web` and use Node.js 22.
6. Verify `/api/health` reports `uploads_enabled: true` before accepting uploads.
7. Sign in, upload a small test file, verify its TUS upload, confirm job processing, then upload the full competition archive.
8. Confirm the new data quality report and review the 10+10 candidates against the official competition dropdown and verified auction information.
9. Publish the analysed dataset snapshot with `scripts/publish_bundle_from_storage.py` and redeploy when the user approves the new analysis.

## Verification performed in this packaging environment

- Python source compilation: passed (`python -m compileall`).
- JSON syntax checks for package manifests, analytical bundle and selection/validation artifacts: passed.
- Next.js build/typecheck: **not run** because dependencies could not be restored: package-registry requests failed with DNS `EAI_AGAIN` and npm exited before install completed. `npm ci --dry-run --offline` did accept the lockfile graph, but it is not a substitute for a full install/build.
- Python test suite: **not run to completion** because `polars` is not installed in this environment; pytest stopped during collection.
- Live Supabase, Railway/Render and Vercel integration: **not tested** because production credentials and deployed URLs were not supplied.

Do not interpret the local checks as proof of a successful production deployment. Run `npm ci`, `npm run typecheck`, `npm test`, `npm run build`, and the worker tests after restoring dependencies and configuring your own services.

## Important data and competition limitations

- The included dashboard is based on a precomputed dataset snapshot. A newly processed dataset is stored as an artifact and becomes the deployed dashboard's active snapshot only after the publish-and-redeploy step.
- Historical player participation does not prove IPL 2027 auction availability.
- The official candidate dropdown list was not included with the uploaded data pack. Import the authoritative list before treating the 10+10 output as final form selections.
- Treat the repository as private. The bundled analytics JSON and scouting reports are derived from proprietary competition data even though raw data directories are Git-ignored.

## Packaging cleanup

- Excluded local worker runtime state, queued-job JSON files and generated processing artefacts; these are recreated by the worker and belong in private storage, not source control.
- Removed an unused duplicate fixture dashboard snapshot. Synthetic test fixtures remain under `data/demo/` and the engine test fixture folder.

- Kept the original proprietary source ZIP separate from the GitHub release archive; the raw archive can be uploaded through the app without accidentally adding it to Git history.
