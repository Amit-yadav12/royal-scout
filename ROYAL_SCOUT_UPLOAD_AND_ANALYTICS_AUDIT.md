# Royal Scout upload and analytics audit

**Audit date:** 2026-11-16 (UTC)
**Working branch:** `arena/46bdbf84-royal-scout`
**Repository base:** `6486961f810d2cb27a95cada3f6628544e5ee305`
**Disposition:** **Staff permission root cause identified; local repair and tests pass, but production migration/bootstrap and full pipeline E2E remain pending.**
**Production writes/deployments:** None performed in this turn. The new database migrations have **not** been applied to Supabase.

## Executive summary

The upload path now has a staff-authenticated, server-signed direct-to-private-Storage design, a browser TUS uploader with progress/cancellation/recovery checks, and a new server-only atomic Supabase queue transition. The dashboard remains public and read-only; ingestion and staff administration are separate authenticated surfaces. Role checks fail closed, profile role self-escalation is blocked by a migration, and admin assignment is intentionally excluded from the in-app role editor.

The production pipeline is **not proven complete**. The Supabase migrations `0010_atomic_upload_jobs.sql` and `0011_protect_profile_roles.sql` must be reviewed and applied before the changed queue/profile invariants take effect. Real Supabase Storage TUS/CORS behavior, claim SQL/transaction behavior, Render queue consumption, artifact publication, and dataset activation have not been exercised together. No competition archive, signed upload, worker job, or production setting was changed in this audit. Do not describe the full upload-to-analytics path as end-to-end successful yet.

## Pipeline and control review

| Stage | Current design / code path | Audit result and remaining proof |
|---|---|---|
| Public dashboard | Dashboard pages remain public, read-only analytics. `web/src/middleware.ts` protects `/ingestion` and `/staff` pages while allowing dashboard reads. The local preview returned HTTP 200 for `/`. | Preserves the explicit public-dashboard decision. Private Storage object URLs and the server key are not deliberately exposed by the browser flow; inspect production response payloads and hosting cache behavior during release QA. |
| Authentication and roles | Password, email-link, recovery and callback flows use Supabase Auth. New profiles default to `viewer`; ingestion requires `analyst`, `scout` or `admin`; staff operations require explicit `admin`. No public signup/domain-derived privileges were introduced. | `0011_protect_profile_roles.sql` blocks role changes made with a user JWT, including self-promotion. Trusted server-side operations and the documented owner-run bootstrap are the role-change path. Apply and test the migration before relying on this invariant. |
| Initial administrator | `supabase/ADMIN_BOOTSTRAP.md` documents an exact-UUID, email-confirmed, one-time bootstrap using the Supabase Dashboard SQL Editor. | Requires a project owner to verify identity and UUID out-of-band. No admin was created by this work. |
| Upload authorization/signing | `POST /api/uploads/sign` validates a verified session, staff role, files, names, counts and byte limits; creates dataset-scoped Storage paths and records `signed` ownership claims. Cross-origin writes are rejected. Browser code receives short-lived upload tokens, not the service key. | Code reviewed; cannot prove bucket privacy, token scope/expiry, Storage CORS allow-headers, or server-key permissions without isolated Supabase integration. Signing many files currently occurs serially and could be slow for very large file counts. |
| Browser transfer | `web/src/components/upload-panel.tsx` uploads directly to Supabase TUS in 6 MiB chunks, shows actual transfer progress, supports cancellation, retries from server-reported offsets and performs final TUS `HEAD` offset verification. UI validation restricts accepted file suffixes/count/size. | Unit tests cover validation and worker-health state only. Browser-to-Supabase TUS, response headers, resumable-session lifetime, cross-origin CORS and browser cancellation remain unverified. File extension validation is UX validation, not a content-security scanner. |
| Storage/claim verification | `POST /api/jobs` validates the current user's claimed object paths and private bucket, checks object existence and size server-side, then calls the privileged RPC. | The handler does not trust browser-supplied ownership. Storage `HEAD` content-length behavior must be confirmed on the configured Supabase version; missing/unexpected lengths fail closed. |
| Atomic queue/claim ownership | `0010_atomic_upload_jobs.sql` adds immutable claim identity, permits only `signed → uploaded → queued`, checks dataset/bucket/path/owner claims, creates one `processing_jobs` record and links claims in one transaction. RPC execution is revoked from `PUBLIC`, `anon` and `authenticated`, and granted to `service_role`. Retries of the exact already-queued set return its original job. Job deletion is restricted while claims reference it. | **Migration not applied or executed against Postgres.** Validate SQL on a disposable Supabase project, including concurrency, repeated requests, mixed/foreign/missing claims, duplicate paths, rollback, and job deletion before production. The browser cannot call the RPC directly. |
| Render worker | The worker polls the shared Supabase `processing_jobs` table, downloads private source objects, applies archive/size checks, runs the analytics pipeline, retries/requeues stale work, and publishes generated artifacts to private Storage. Worker readiness now probes the queue plus both the configured private upload bucket and artifact bucket; a missing upload bucket keeps readiness false. The web queue route inserts durable DB rows directly; it does not proxy raw bytes or depend on a synchronous heavy-processing HTTP request. | Local engine queue/worker tests pass. No Render cold-start, deployed queue polling, real Storage download, timeout, interruption, stale-job recovery, or retry integration was run. Render's current container combines API and a sequential polling worker; free-tier sleep/ephemeral-disk behavior is documented in `RENDER_SETUP.md` and cannot guarantee uninterrupted long jobs. Use always-on compute for dependable production processing. |
| Job status/retry/download | Authenticated status and artifact routes require job ownership; retry additionally requires an upload-capable staff role and same-origin request. Artifact access creates short-lived signed URLs for selected artifact extensions. | No worker API live call was run. Confirm a worker API failure stays a visible non-success state and test retry limits/ownership on an isolated deployment. |
| Dataset provenance/isolation | Each upload creates a unique dataset ID. Successful jobs are listed in project scope; the active dataset cookie is only changed by authenticated, same-origin requests after successful-dataset validation. Production bundle loading has no stale local-snapshot fallback. Existing pipeline bundle includes ingestion file summaries, hashes, quality findings, model/config versions and limitations. | Dataset switching and bundle download were not exercised against private Storage. The current worker publishes bundles/reports/artifacts; this audit did not establish that every relational provenance table (`uploads`, `source_files`, `archive_entries`, `dataset_versions`) is populated for every run. Validate that the bundle/report provenance is sufficient or add relational persistence if required. Uploaded datasets remain separate; no automatic merge/primary-source replacement was added. |
| Analytics | Existing engine modules compute batting, bowling, situation/pressure, eligibility-adjusted rankings, confidence/coverage and stability outputs. Synthetic fixtures are marked and have tests; uploaded work is queued with `is_fixture=false`. | Existing tests pass, but no independent scorecard benchmark or user competition was available. Passing unit tests is not evidence that every statistic is correct for every source schema. Do not claim analytics validation against the requested real competition data. |
| Export | CSV export requires an authenticated user and reports dataset/model/config/scope/fixture provenance. | No live export or selected private bundle test was run. |

## Authorization review

Middleware deliberately exempts `/api/` globally because each handler has a separate policy. The handlers reviewed for this change are:

- `/api/uploads/sign`: authenticated user + upload role + same-origin check.
- `/api/jobs` POST: authenticated user + upload role + same-origin + claim and Storage verification.
- `/api/jobs/[id]` GET and `/artifacts` GET: authenticated owner only.
- `/api/jobs/[id]/retry` POST: authenticated owner + upload role + same-origin.
- `/api/admin/invitations` POST and `/api/admin/staff` GET/PATCH: explicit administrator; writes require same-origin. Admin privileges cannot be selected in the staff editor.
- `/api/datasets/active` POST: authenticated user + same-origin + successful dataset validation.
- `/api/export` GET: authenticated user.
- `/api/health` GET: read-only readiness/configuration report; must not contain credential values.
- Legacy `/api/ingest` POST: retired with HTTP 410; raw upload bytes are not accepted there.

This is source review, not a penetration test. Recheck every newly added API route when routes are added later; the middleware exemption means no route inherits a global session policy.

## Validation performed

- Web unit tests: **66 passed** across 12 Vitest files, including new tests confirming viewer denial at upload signing/job creation and visibility of missing-profile status.
- Web TypeScript check: **passed** (`npm run typecheck`).
- Web production build: **passed** (`npm run build`). It emits the existing warning that the Supabase browser package references `process.version` through the middleware dependency graph; verify deployed Edge/runtime behavior even though the build succeeds.
- Python engine tests and local Next.js smoke checks were not rerun in this turn; prior results are historical, not validation of this patchset.
- `git diff --check`: **passed**.
- Full authenticated browser TUS, worker processing, artifact publication, and dataset activation E2E are still pending; no live migration/bootstrap/deployment was performed.
- Earlier Playwright coverage in this repository was blocked for most tests by missing Chromium. This change has not been run through a complete browser E2E suite.
- `npm ci` reports **6 dependency advisories** (3 moderate, 1 high, 2 critical); no forced dependency upgrade was attempted in this task.

## Release blockers / required follow-up

1. Review and apply migrations `0010_atomic_upload_jobs.sql` and `0011_protect_profile_roles.sql` to a disposable Supabase project; test grants, trigger behavior and transaction rollback. Only then schedule the reviewed migrations for production through the normal change-control process.
2. Confirm Auth self-signup and anonymous Auth remain disabled; verify the initial administrator through the one-time bootstrap procedure and test a viewer/analyst/scout/admin permission matrix.
3. In a non-production project, verify the `uploads` bucket is private, configure TUS CORS/allowed headers, and test actual signed upload creation, interrupted-chunk recovery, final `HEAD`, object-size mismatch rejection, and unauthorised access denial.
4. Configure and verify the same server-only Supabase key and `WORKER_SHARED_SECRET` in Vercel and Render. Ensure `RS_ENV=production`, `RS_USE_SUPABASE_QUEUE=1`, durable DB queue, correct storage bucket names and Render health path `/health/ready`. Do not put service-role/secret keys in `NEXT_PUBLIC_*` variables.
5. Queue a small **synthetic isolated fixture** in a staging environment. Verify the exact job row, source ownership, worker logs, retry/recovery behavior, private artifact upload, successful bundle retrieval, dataset selector activation, and CSV provenance. Verify failure modes do not report success or select an unrelated snapshot.
6. Run browser E2E with installed Chromium, including public read-only dashboard, unauthenticated route denial, role denial, admin management, TUS retry/cancel, and successful/failed job UI.
7. For a real competition dataset, compare parsed source records and calculated outputs against independently checked scorecards before making scouting recommendations. Do not add proprietary raw files to Git or public storage.

## Files added or materially changed

- `supabase/migrations/0010_atomic_upload_jobs.sql`
- `supabase/migrations/0011_protect_profile_roles.sql`
- `supabase/ADMIN_BOOTSTRAP.md`
- `engine/royalscout/api.py` (readiness probe now includes the configured upload bucket)
- `engine/tests/test_health.py`
- `web/src/app/api/jobs/route.ts`
- `web/src/app/api/uploads/sign/route.ts`
- `web/src/components/upload-panel.tsx`
- `web/src/middleware.ts`
- `web/src/app/api/admin/staff/route.ts`
- `web/src/components/staff-role-manager.tsx`
- `web/src/lib/request-security.ts`
- `web/src/lib/upload-validation.ts`
- `web/src/lib/worker-health.ts`

## Final status

This change is a **staging candidate**, not a verified production repair. The implementation avoids public processing writes, cross-user object claims, automatic role elevation, direct browser service keys, Vercel file-byte proxying and automatic dataset merging. Production remains unchanged. End-to-end success remains unproven until the migrations and isolated Storage → queue → Render worker → artifact → dataset-selection tests above pass.
