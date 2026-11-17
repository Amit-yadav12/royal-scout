# First Royal Scout administrator — one-time bootstrap

## Why this is needed

Read-only inspection of the connected `royal-scout` Supabase project found **one email-confirmed Auth user, zero `profiles` rows, and zero admins**. The Auth session was recently active. The database has the `handle_new_user()` trigger, but it only handles users inserted after the trigger was installed; it does not backfill older Auth users. The app had collapsed a missing profile and a database lookup error into the same `Unavailable` display.

The sole Auth user's UUID returned by Supabase is:

```text
ab897bdc-3c27-4d02-9de2-b11908cce597
```

Do not use this UUID unless it matches the intended operator's authenticated account in Supabase **Authentication → Users**. This is an identity, not a secret. Never substitute an email-domain check or a guessed UUID.

## Apply the migrations first

Apply the repository migrations in order: `0001`–`0009` as needed, then `0010_atomic_upload_jobs.sql`, `0011_protect_profile_roles.sql`, and `0012_staff_profile_repair_and_admin_assignment.sql`. The connected production project currently reports migrations through `0009` plus `20261116171951 lock_profile_role_updates`; reconcile that existing migration history with the deployment owner before using `supabase db push`. These are schema changes; review them and apply through the normal change-control process. Migration `0012` safely inserts missing Auth profiles as `viewer` and creates the one-time bootstrap function.

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

## After bootstrap

1. Sign out and back in (or refresh the session) and open **Data Ingestion**. The page reads the current profile role from the server. A role-change listener refreshes access on focus and every 15 seconds; **Refresh permissions** triggers an immediate check.
2. Open **Staff Access** and invite the intended analyst/scout or change an existing verified staff account. Admin role changes and invitations are restricted to an authenticated admin and go through `assign_staff_role`; the database function re-checks the actor and prevents downgrading the last admin. Self-role changes are rejected.
3. Analyst and scout can upload/process; viewer cannot. Both `/api/uploads/sign` and `/api/jobs` independently verify the current session and role and return HTTP 403 when access is absent or insufficient.

Do not enable public sign-up to solve a missing profile. Do not modify role claims in user metadata, infer a role from email, invoke the bootstrap from the browser, or expose a Supabase secret/service-role key to the client.
