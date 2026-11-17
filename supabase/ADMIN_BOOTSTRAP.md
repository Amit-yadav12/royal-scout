# One-time initial administrator bootstrap

Use this only when the project has no existing administrator. It does not enable public sign-up and must be run by a trusted project owner in the Supabase Dashboard SQL Editor (never from browser code or a public endpoint).

1. In the Supabase Dashboard, use **Authentication → Users → Invite user** to provision the intended operator (the in-app staff invitation endpoint cannot be used until an administrator already exists). Confirm the person controls the email and has accepted the invite. Do not create an account from a public sign-up form.
2. Copy the exact UUID from that authenticated user's Auth record. Verify the email and UUID out-of-band with the organisation owner.
3. In SQL Editor, replace the UUID literal below with that exact Auth user UUID, inspect the statement, and run it once:

```sql
begin;
do $$
declare
  target_user uuid := 'REPLACE_WITH_VERIFIED_AUTH_USER_UUID';
begin
  if not exists (
    select 1 from auth.users
    where id = target_user and email_confirmed_at is not null
  ) then
    raise exception 'Target must be an existing email-confirmed Auth user';
  end if;
  update public.profiles
     set role = 'admin'
   where id = target_user;
  if not found then
    raise exception 'Profile row missing; repair profile provisioning before bootstrap';
  end if;
end $$;
commit;
```

4. Verify the exact account and role in the SQL Editor:

```sql
select id, email, role from public.profiles
where id = 'REPLACE_WITH_VERIFIED_AUTH_USER_UUID';
```

5. Sign in through `/login`, open **Staff Access**, and invite a second trusted administrator by using the external Supabase administrative process only. The in-app staff form intentionally cannot grant or alter `admin` roles. Keep the SQL execution record in the organisation's audit trail.

Never bootstrap by email domain, user-supplied metadata, an unauthenticated HTTP request, or a client-side service key. If the profile is missing or the UUID cannot be independently confirmed, stop rather than guessing.
