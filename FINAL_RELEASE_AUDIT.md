# Royal Scout — Final Release Audit

**Audit date:** 2026-11-16 (UTC)  
**Repository:** `Amit-yadav12/royal-scout`  
**Production URLs in scope:** `https://royal-scout.vercel.app` and `https://royal-scout.onrender.com`  
**Working branch:** `arena/80048bb2-royal-scout` (active; head before audit work: `5fad3d6`)  
**Release branch requested:** `release/royal-scout-final` — **BLOCKED / NOT CREATED**. This session is bound to its active Arena branch; no branch switch or extra branch was made.  
**Overall disposition: FAIL — do not declare production-ready.** Critical browser, deployment, access-control and production-workflow acceptance remains incomplete; the available E2E run failed, and a development dependency audit reports critical vulnerabilities.

## Status key

- **PASS** — executed and passed for the stated scope only.
- **FAIL** — an observed defect or failed check remains.
- **BLOCKED** — the check could not be completed because of an environment, access or prerequisite limitation.
- **NOT TESTED** — no qualifying check was performed. A local/unit result is not a substitute for production acceptance.

## Executive summary

| Area | Status | Evidence / disposition |
|---|---|---|
| Frontend typecheck, unit tests, production build | **PASS** | Typecheck passed; 42/42 Vitest tests passed; Next.js production build succeeded. |
| Backend tests and import/compile checks | **PASS** | 69/69 pytest tests passed this audit; compileall and selected imports passed. Starlette/httpx emitted a deprecation warning. |
| Dependency security | **FAIL** | Full frontend `npm audit` reports 6 development-tree vulnerabilities: 3 moderate, 1 high and 2 critical. `npm audit --omit=dev --audit-level=high` reports zero production dependency vulnerabilities. Do not use `npm audit fix --force` without a compatibility upgrade plan; it proposes Vitest 5.1.0. |
| Browser E2E | **FAIL / BLOCKED** | Last available run: 2/29 passed, 27 failed. Chromium headless shell was missing; export API checks received HTML rather than CSV. Browser-dependent coverage is blocked; CSV API behavior has an observed failure. |
| Docker image build | **BLOCKED** | Docker CLI/daemon is unavailable in this environment. |
| Supabase project health/configuration | **PASS (limited)** | Connected-app read-only check reported Auth/DB/Storage healthy, signup disabled and migrations `0001`–`0009` plus `20261116171951`. This does not prove application permissions or workflow correctness. |
| Production deployment / Vercel-to-Render | **NOT TESTED** | Vercel project/deployment lookup returned no result and domain/team access was denied for insufficient permission. These connector results do not prove the production site is down. No production end-to-end request was verified. |
| Production dataset, login, upload, queue and artifact workflow | **NOT TESTED** | No synthetic upload or mutation was made in production. Remote counts were zero for datasets, versions, uploads, upload claims and jobs during read-only inspection. |
| Release readiness | **FAIL** | Several critical acceptance paths are unverified or failing; keep release gated. |

## Verified fixes in this audit

The ball-event path had verified attribution/accounting defects: extra totals alone were being used as if all deliveries were legal; bowler runs included every extra; and every dismissal was counted as a bowler wicket. The implementation now:

1. Maps explicit extra-type labels and uses per-delivery wide/no-ball fields when supplied.
2. Distinguishes legal deliveries from batter balls (a wide is neither; a no-ball is not legal but is faced).
3. Attributes wide/no-ball runs to the bowler, but not byes/leg-byes or penalty runs.
4. Excludes run-outs and other explicitly uncredited dismissals from bowler wickets; unclassified dismissals are unknown rather than fabricated as bowler wickets.
5. Uses legal-delivery counts for run-rate/balls-remaining calculations and phase bowling/batting aggregates.
6. Propagates unknown extras/wicket attribution as unavailable values rather than silently reporting partial workload, runs or wicket metrics as complete.

Synthetic regression coverage was added for bye, wide, no-ball, run-out, caught, unknown extras and unknown dismissal types, including innings reduction, phase aggregates and bowling metric availability. All 69 backend tests pass after the change.

**Input limitation:** when a source supplies only a numeric extras total, without an extra type or separate wide/no-ball columns, legality and bowler-run attribution cannot be reconstructed safely. Affected derived metrics are now withheld/marked unknown; ingestion must capture attribution detail to produce complete records. This is safer than guessing but still requires product/UX acceptance and representative-source validation.

## Detailed acceptance matrix

### Product UI, interaction and accessibility

| Check | Status | Evidence / notes |
|---|---|---|
| Brand mark, favicon and logo assets | **PASS (asset/local smoke only)** | Selected Royal Scout mark, favicon, SVG lockup and brand component are present; prior local route/asset smoke checks returned HTTP 200. |
| Visual polish across all pages and breakpoints | **NOT TESTED** | No comprehensive browser visual review, screenshot comparison or mobile/tablet viewport pass was completed. |
| Responsive layout, keyboard navigation, screen-reader/accessibility behavior | **NOT TESTED** | No qualifying accessibility or multi-viewport browser audit. |
| Page interactions and error/loading/empty states | **NOT TESTED** | Build and unit tests do not verify full user-facing states. |
| Authentication and successful login | **NOT TESTED** | Signup is disabled in remote Auth configuration; no valid production login was exercised. |
| Protected routes and role enforcement | **NOT TESTED** | Local access-control unit tests pass, but no authenticated/unauthenticated browser or production-role acceptance was completed. |
| Dataset selection UI | **PASS (unit scope only)** | Four dataset-selection frontend unit tests pass; no production dataset-selection workflow was run. |
| Rankings and player-profile user workflows | **NOT TESTED** | Backend analytic tests/build cover code paths, not complete browser journeys with production data. |
| Pressure/comparison workflows | **NOT TESTED** | Unit-level pressure/ranking tests pass; full browser workflows and real-data acceptance were not run. |
| Filters and CSV construction | **PASS (unit scope only)** | Filter and CSV/provenance frontend unit tests pass. |
| Export API/browser behavior | **FAIL** | E2E API export checks received HTML instead of CSV. Investigate route/rewrite/auth/fallback behavior and rerun. |
| Squad selection workflow | **NOT TESTED** | No complete acceptance test was run. |

### Data integrity and analytics

| Check | Status | Evidence / notes |
|---|---|---|
| Synthetic fixture isolation | **PASS (local test scope)** | Tests use named synthetic fixtures and local temporary storage. No fixture was uploaded to production. |
| Source provenance/lineage and ingestion/dedup tests | **PASS (unit scope only)** | Backend test suite includes ingestion, lineage and duplicate-bundle checks; this does not prove remote dataset isolation. |
| Dataset isolation and no silent fixture/live mixing | **NOT TESTED in production** | Remote application counts were empty; no production data mutation or live acceptance workflow was performed. Preserve each uploaded dataset as a separate source of truth. |
| Batting/bowling record analytics | **PASS (unit scope, after fix)** | Existing tests pass; new synthetic tests cover ball accounting and unavailable attribution. Real-provider export coverage is still needed. |
| Ball-by-ball legal delivery, extras and wicket attribution | **PASS for explicit synthetic classifications; BLOCKED for unclassified provider data** | Explicit classifications now reduce correctly. Numeric-only/unclassified extra and dismissal records are withheld from affected derived metrics; real provider formats must be checked. |
| Ranking/statistical correctness on actual production data | **NOT TESTED** | No production dataset was present in read-only counts, and no claims about missing live statistics are made. |
| Analytics provenance and absence of fabricated statistics | **PASS (implementation review / synthetic tests only)** | Unknown attribution is now preserved as unknown in tested derived bowling metrics. Full production data review remains untested. |

### Backend, storage and infrastructure

| Check | Status | Evidence / notes |
|---|---|---|
| Backend unit tests | **PASS** | `PYTHONPATH=engine engine/.venv/bin/pytest -q engine/tests`: 69/69 passed. One Starlette/httpx deprecation warning. |
| Backend compile/import checks | **PASS** | `compileall` and imports of canonical, pressure, bowling, pipeline, API, worker and ingest passed. |
| Supabase migrations applied | **PASS (history only)** | Remote migration history reports `0001`–`0009` and `20261116171951`. No independent schema diff or rollback rehearsal performed. |
| RLS and authorization behavior | **NOT TESTED** | Catalog inspection reported RLS enabled on inspected application tables, profile updates constrained to `display_name`, queue RPC execute access limited to `service_role`, and `anon`/`authenticated` SELECT privileges on `players`. These are catalog observations, not authenticated/anonymous permission tests. |
| Private Storage buckets | **PASS (configuration only)** | `uploads`, `royal-scout-artifacts` and `fixtures` were reported private. No live unauthorized-read/write test was run. |
| Storage upload limits / MIME restrictions | **FAIL / hardening required** | Read-only bucket inspection reported no size or MIME restrictions. Define and verify suitable limits before accepting untrusted uploads. |
| Storage-object RLS policies | **NOT TESTED** | The inspection returned no Storage policies; this is not proof of effective privacy. Test as anonymous, authenticated, owner and service-role principals. |
| Queue, worker, retries and artifacts | **PASS (local unit scope only)** | Local queue/worker/artifact and storage helper tests pass. No remote job was queued or processed; production tables were empty. |
| Vercel-to-Render communication and CORS/auth | **NOT TESTED** | No deployment URL/configuration was verified through Vercel; no cross-origin production request was executed. |
| Docker build and container runtime | **BLOCKED** | Docker unavailable; image build, container health and runtime settings remain unverified. |
| Render health / production API behavior | **NOT TESTED** | No qualifying direct production health/workflow verification was completed. |

### Security and release engineering

| Check | Status | Evidence / notes |
|---|---|---|
| Production dependency audit | **PASS** | `npm audit --omit=dev --audit-level=high`: zero vulnerabilities. |
| Full frontend dependency audit | **FAIL** | 6 dev-tree advisories (3 moderate, 1 high, 2 critical). Upgrade only after evaluating compatible versions and rerunning the full suite; `--force` proposes a breaking Vitest major. |
| Secret leakage checks | **PASS (automated/local scope)** | Backend health/auth/storage tests assert private secret values are not exposed. No secret values are included in this report. |
| Production secret/environment configuration | **NOT TESTED** | No production environment values were read or disclosed; deployment configuration could not be independently verified. |
| CORS, CSRF, rate limits, abuse limits and upload threat model | **NOT TESTED** | No security penetration or permission-boundary test was performed. |
| Branch and release commit | **BLOCKED** | The active branch is `arena/80048bb2-royal-scout`; `release/royal-scout-final` was not created because the session is bound to its active branch. Changes must be reviewed and promoted through the repository's release workflow. |

## Test and inspection record

- Frontend `npm run typecheck`: **PASS**.
- Frontend `npm test`: **PASS**, 42/42 tests across 7 files.
- Frontend `npm run build`: **PASS**, Next.js production build.
- Frontend `npm audit --omit=dev --audit-level=high`: **PASS**, 0 vulnerabilities.
- Frontend full `npm audit --audit-level=moderate`: **FAIL**, 6 dev dependency vulnerabilities; force fix not applied.
- Backend `PYTHONPATH=engine engine/.venv/bin/pytest -q engine/tests`: **PASS**, 69/69 tests.
- Backend `compileall`, selected imports and `git diff --check`: **PASS**.
- Browser E2E latest recorded run: **FAIL**, 2/29 passed, 27 failed; Chromium headless shell absent and exports returned HTML instead of CSV.
- Docker image build: **BLOCKED**, Docker executable unavailable.
- Supabase connector read-only inspection: Auth/DB/Storage healthy; signup disabled; inspected app tables reported RLS enabled; private buckets reported; no remote datasets/uploads/claims/jobs. Catalog checks do not validate runtime authorization.
- Vercel connector: project search/deployment list returned no project/deployment; domain/team access denied. Production deployment status is **NOT VERIFIED**, not assumed down.
- Local smoke checks previously returned HTTP 200 for `/`, `/login` and brand assets; the preview has been stopped.

## Required before release approval

1. Fix the export API response path so export requests return CSV rather than the HTML application shell; run the API and browser export tests.
2. Install/enable the correct Playwright browser and rerun the full E2E suite. Resolve all failures and add mobile/responsive, login/protected-route, dataset-selection, profile, comparison, squad and export acceptance paths.
3. Evaluate patched compatible frontend test/build dependency versions. Remove all critical/high advisories without an untested breaking upgrade; rerun typecheck, unit tests, build, E2E and audits.
4. Build and run the Docker image in a Docker-capable CI environment; record image/build/runtime results.
5. Verify Vercel project/deployment and Vercel-to-Render API connectivity with authorized read-only checks. Confirm the deployed frontend and API versions/configuration.
6. Test Supabase RLS and private Storage permissions using isolated non-production principals and a dedicated synthetic project/dataset. Test anonymous, authenticated non-owner, owner and service-role paths, including object listing, read, write and delete.
7. Add Storage upload size/MIME controls and validate them; verify queue leases/retries, worker processing and artifact access on isolated test data.
8. Run the complete ingestion-to-artifact workflow only in a non-production isolated environment; verify dataset scoping, source lineage, deduplication, rankings and exports. Do not upload synthetic fixtures to production or mix them into live datasets.
9. Complete production visual/accessibility/responsive review and a successful authorized login/protected-route acceptance test. Do not use production uploads as test input.
10. After the session branch restriction is resolved through the approved workflow, create/review the requested release branch and promote only after every critical item passes.

**Release decision:** **FAIL — not production-ready on the evidence available.** This report distinguishes local checks from unverified production behavior and does not treat unavailable infrastructure/browser tests as passes.
