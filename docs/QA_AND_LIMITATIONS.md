# QA, data flow, and deployment readiness

## Runtime dataset selection

Production analytics use the authenticated Next.js server to query the latest successfully completed `processing_jobs` records for `ROYAL_SCOUT_PROJECT_ID`, validate the recorded `bundle_object`, and read the matching `bundle.json` from the private `SUPABASE_ARTIFACT_BUCKET` in Supabase Storage. The same request-scoped dataset is used by the overview, player pages, rankings, analytics, Data Center and server-generated CSV export.

The dataset selector stores only a validated dataset ID in an HttpOnly, same-site cookie. History lists distinct successful jobs with published bundles (up to 50). A newly completed upload is selected after job success. Failed/running jobs and paths that do not match the worker's project/dataset bundle convention are excluded. A missing/stale selection or missing artifact produces an explicit error; production never silently falls back to an unrelated bundle. The checked-in `web/src/data/bundle.json` remains a visibly identified, local-development-only fallback.

`/pressure-audit` is a fixed, separately audited shortlist for dataset `ds_superr_s2_real`; it intentionally hides its results when a different dataset is active. It is not recalculated from an arbitrary active dataset.

## Auth and authorization

- `/login` has its own public route layout; dashboard routes remain protected by Supabase SSR session validation.
- Password, non-registration magic-link, recovery, and callback-code exchange flows set/persist sessions through SSR cookies. `next` redirects are restricted to local paths. Public self-registration is disabled in the Supabase Auth configuration; email-link sign-in uses `shouldCreateUser: false`.
- Authenticated `viewer` users can read the dashboard. Only `analyst`, `scout`, and `admin` profiles can sign upload URLs, queue jobs, or retry jobs.
- `supabase/migrations/20261116171951_lock_profile_role_updates.sql` removes table-wide profile updates and grants only `display_name` updates to `authenticated`; role promotion stays in the trusted admin provisioning workflow.
- Upload bytes continue to use direct resumable TUS transfers to private Storage. The legacy `/api/ingest` endpoint is deliberately public and returns HTTP 410; it never accepts file bodies.

Production setup requires the matching Vercel server-only Supabase key, project URL, artifact bucket, `ROYAL_SCOUT_PROJECT_ID`, worker URL/secret, and the Supabase Auth callback allow-list. See `SUPABASE_SETUP.md`, `VERCEL_SETUP.md`, `RENDER_SETUP.md`, and `DEPLOYMENT_TROUBLESHOOTING.md`.

## Checks run in this workspace

| Check | Result |
| --- | --- |
| `cd web && npm ci` | Passed |
| `npm run typecheck` | Passed |
| `npm test` | 42 tests passed |
| `npm run build` | Passed; dashboard routes are request-dynamic, login is static/public |
| `npm audit --omit=dev --audit-level=high` | Passed; zero production dependency advisories |
| `PYTHONPATH=. .venv/bin/pytest` in `engine/` | 68 passed |
| Local development HTTP smoke | Login and all dashboard routes returned 200; local snapshot banner displayed; `/api/ingest` returned 410 |
| Production-mode auth-lock smoke (no Supabase env) | `/` redirected to `/login?setup=required`; `/login` and health returned 200; `/api/ingest` returned 410 |
| `git diff --check` | Passed |

The initial Playwright run was not a valid authenticated E2E pass: the environment has no Chromium executable or provisioned staff test session, and protected production routes correctly redirected to login. The legacy ingestion assertion was updated to expect the deliberate 410 response. Re-run `npm run e2e` with Chromium installed and an authorized test account/storage state to verify password/magic/recovery, data switching, exports and uploads against real services.

The full development dependency audit still reports advisories in the existing Vitest/Vite/tinypool toolchain (including critical tinypool advisories); no forced major test-runner upgrade was made. Runtime dependencies are clean. Docker/Podman is not installed in this workspace, so the Render-context image build was not run. No authorized test account or Vercel project was available here; full Supabase Storage → Render worker → Vercel rendering, real CSV export, and email delivery remain integration checks, not claimed as verified.

## Production checks performed

Read-only Supabase checks confirmed the connected `royal-scout` project was active/healthy and migration history contained `0001`–`0009`. The new `lock_profile_role_updates` migration was then applied as migration version `20261116171951`; a read-only privilege query confirmed `authenticated` can update `display_name` but not `role` and has no table-wide update privilege. Supabase Auth was configured with public signup disabled and exact callback allow-list entries for `https://royal-scout.vercel.app/auth/callback` and local `http://localhost:3000/auth/callback`. No production scouting rows, files, or secrets were changed.

The Vercel connector returned no matching `royal-scout` project, so deployment settings, environment variables and live deployment status remain unverified. No deployment was started from this branch.
