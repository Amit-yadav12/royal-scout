# First Royal Scout administrator — one-time bootstrap

## Why this is needed

Read-only inspection of the connected `royal-scout` Supabase project found **one email-confirmed Auth user, zero `profiles` rows, and zero admins**. The Auth session was recently active. The database has the `handle_new_user()` trigger, but it only handles users inserted after the trigger was installed; it does not backfill older Auth users. The app had collapsed a missing profile and a database lookup error into the same `Unavailable` display.

The sole Auth user's UUID returned by Supabase is:

```text
ab897bdc-3c27-4d02-9de2-b11908cce597
```

Do not use this UUID unless it matches the intended operator's authenticated account in Supabase **Authentication → Users**. This is an identity, not a secret. Never substitute an email-domain check or a guessed UUID.

## Apply the migrations first

Apply the repository migrations in order: `0001`–`0009` as needed, then `0010_atomic_upload_jobs.sql`, `0011_protect_profile_roles.sql`, `0012_staff_profile_repair_and_admin_assignment.sql`, and `20261116180000_admin_only_staff_access.sql`. The connected production project originally reported migrations through `0009` plus `20261116171951_lock_profile_role_updates`; reconcile that existing migration history with the deployment owner before using `supabase db push --remote --include-all`. These are schema changes; review them and apply through the normal change-control process. Migration `0012` backfills missing Auth profiles as `viewer` and creates the one-time bootstrap function. The admin-only migration downgrades analyst/scout profiles to read-only, restricts roles to viewer/admin, and enforces a single administrator.

The bootstrap procedure intentionally cannot be called through the public app, the authenticated API, or the service-role REST client. Run it once from the Supabase Dashboard SQL Editor as the database owner, after checking that the UUID is the intended operator:

```sql
-- Inspect the exact Auth record first; confirm this is the intended operator.
select id, email_confirmed_at, created_at, last_sign_in_at
from auth.users
where id = 'ab897bdc-3c27-4d02-9de2-b11908cce597';

-- Confirm there is still no administrator before consuming the one-time bootstrap.
select count(*) as admin_count
from public.profiles
where role = 'admin'::public.app_role;

-- Run only after verifying the UUID and confirming admin_count = 0.
select public.bootstrap_first_admin('ab897bdc-3c27-4d02-9de2-b11908cce597');

-- Verify the resulting account and one-time marker.
select id, email, role from public.profiles
where id = 'ab897bdc-3c27-4d02-9de2-b11908cce597';
select completed_at, completed_by from public.staff_bootstrap_state where singleton = true;
```

The procedure checks that the Auth account exists and its email is confirmed, serializes against concurrent role assignments, refuses to run if an admin already exists, and records a one-use marker. It does not create an Auth user. Keep the execution record in the organisation's audit trail.

## Passwordless admin sign-in and public access

1. Public analytics, dataset selection, and CSV exports require no sign-in. Only **Data Ingestion** requires administrator authentication; there is no staff invitation flow or password sign-in.
2. The Admin sign-in page sends a single-use email link to `amiatyadav1275a@gmail.com` with account creation disabled. The Supabase `profiles.role` check grants administrator access; email address alone does not.
3. Configure a production SMTP provider in Supabase **Authentication → Settings → SMTP Settings**. The built-in sender is intended for testing and may be restricted or rate-limited. In **Authentication → URL Configuration**, allow the deployed app origin and its `/auth/callback` path so the magic link can return to the app.
4. Only the administrator can upload, process, or retry datasets. `/api/uploads/sign`, `/api/jobs`, and the retry route independently verify the authenticated administrator and return HTTP 403 otherwise. The database migration enforces one admin and prevents assigning analyst/scout/admin roles through the app.

Do not enable public sign-up to solve a missing profile. Do not modify role claims in user metadata, infer a role from email, invoke the bootstrap from the browser, or expose a Supabase secret/service-role key to the client.
