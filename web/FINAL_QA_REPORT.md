# Royal Scout — Public Dashboard QA Report

**Date:** 2026-11-16 UTC  
**Current branch:** `arena/29a95198-royal-scout` (active; based on `0b6824adfadbed5274811cf871905217f2961d84`)  
**Access mode requested and implemented:** public, no-login, read-only dashboard  
**Production deployment:** not performed in this turn  
**Status:** **CODE CHECKS PASS; browser QA and production rollout remain unverified.**

## What changed for no-login access

- Dashboard pages are open without a Supabase session; middleware no longer redirects the dashboard to a login page.
- `/login` is retained only as a compatibility redirect to `/` and displays no sign-in form.
- The shell no longer shows Sign out or administrator controls. The staff administration page is unavailable in the public dashboard.
- The ingestion page presents processed-source history read-only. Upload controls are removed from the public navigation/page; upload, job, retry and invitation APIs continue to require authorization.
- Analytics CSV exports now work without a user session and include the existing provenance metadata.
- Dataset selection is available without an account and still validates IDs against the successful datasets (or the one bundled snapshot when live storage is not configured).
- If Supabase server-side storage configuration is absent, the site uses the versioned bundle embedded with the deployment and labels it **EMBEDDED SNAPSHOT**. If live storage is configured but fails, the application shows an error rather than silently substituting the old snapshot.
- The shell clearly identifies the experience as a **public read-only dashboard** and says uploads and staff administration are disabled.

**Important exposure:** Anyone on the internet can now inspect dashboard analytics, player information, public CSV exports, and the currently selected dataset content. The user explicitly selected public dashboard/no login after being warned about exposure. Do not deploy this mode if the scouting dataset is confidential or not approved for public release.

## Access and configuration boundaries

- Public signup and anonymous Supabase Auth remain disabled in the Supabase project. This application does not require a Supabase anonymous-auth session for public dashboard viewing.
- Upload signing, queueing, retries, job ownership, private artifact downloads and administrator invitations retain their server-side session/role checks. These operations are intentionally unavailable from the no-login UI.
- No production Supabase setting, Vercel setting, user account, dataset, or worker job was changed.
- Vercel connector project search returned no project matching `royal-scout`; production deployment was therefore not attempted. The current working branch remains the active Arena branch, not `main`.

## Verification

| Check | Result | Evidence |
|---|---|---|
| TypeScript typecheck | **PASS** | `npm run typecheck` |
| Frontend unit tests | **PASS** | `npm test`: 55/55 tests across 8 files |
| Next.js production build | **PASS** | `npm run build`; analytics and public export routes built successfully |
| E2E API tests without browser | **PASS** | Targeted public CSV/provenance and anonymous invitation-denial tests: 2/2 passed |
| Full Playwright E2E | **BLOCKED** | 6/33 passed; the 27 browser-driven tests failed to launch because Playwright Chromium headless shell is not installed. All 6 request-only tests passed, including both unauthenticated CSV export tests. |
| Local production-mode HTTP smoke | **PASS (limited)** | `/`, `/players`, `/exports`, and `/ingestion` returned 200 and contained the public-mode notice. `/login` resolved to `/`. Anonymous batting export returned 200 `text/csv` and included dataset provenance. |
| Invitation endpoint smoke | **DENIED** | An anonymous POST returned 403 at the origin guard; this verifies no invitation was created but is not a full authenticated-role test. |
| Backend Python tests | **PASS (prior run)** | 69/69 engine tests passed in the preceding QA turn; no Python code changed in this public-mode update. |
| Python compile check | **PASS (prior run)** | `compileall` passed in the preceding QA turn; no Python code changed in this public-mode update. |
| Docker image build | **BLOCKED** | Docker executable is unavailable in this workspace. |
| Production browser/deployment smoke | **NOT RUN** | No matching Vercel project was returned by the connected Vercel project search; no deployment was created. |
| Dependency audit | **Prior findings remain** | Full development dependency audit previously reported six advisories (3 moderate, 1 high, 2 critical); production-only audit reported zero high-level findings. No dependency change was made here. |

## Remaining work before calling it complete

1. Install Chromium and run all 33 Playwright tests; visually inspect desktop/mobile layouts and console errors.
2. Confirm public data-release approval for the embedded bundle and current live dataset before production rollout.
3. Test production Vercel-to-Supabase data loading and exports through an authorized deployment owner. Production remains unchanged.
4. If public uploads or public processing are desired, design a separate abuse-resistant intake workflow (rate limits, quotas, malware/archive limits, moderation and cost controls). Do **not** make the current upload/queue APIs anonymous.
5. Keep the dependency audit findings on the remediation list and resolve them with compatible upgrades.

## Scope note

This report supersedes the earlier private-login release decision for the dashboard UI: the user's latest decision is **public access with no login**. It does not claim that anonymous upload, worker control, staff invitation, or administrator operations are enabled.
