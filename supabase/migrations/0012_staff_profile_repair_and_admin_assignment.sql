-- Repair existing Auth users that predate handle_new_user() and provide
-- audited, server-only staff role assignment plus a one-time owner bootstrap.

-- Profiles created after the core migration default to viewer. Backfill Auth
-- users that were already present when the profile trigger was installed.
insert into public.profiles (id, email, display_name, role)
select u.id, u.email,
       coalesce(nullif(u.raw_user_meta_data->>'full_name', ''), split_part(coalesce(u.email, ''), '@', 1)),
       'viewer'::public.app_role
  from auth.users u
  left join public.profiles p on p.id = u.id
 where p.id is null
on conflict (id) do nothing;

-- Keep profile visibility scoped by RLS; clients may edit display_name only.
-- Privileged role writes are done via the service-role-only RPC below.
revoke all on public.profiles from anon;
revoke insert, update, delete on public.profiles from public, authenticated;
revoke insert (role), update (role) on public.profiles from public, authenticated;
grant select on public.profiles to authenticated;
grant update (display_name) on public.profiles to authenticated;

-- Serialize all changes to admin membership, including one-time bootstrap.
-- No client role (including authenticated and service_role) can read/write this
-- state table directly; its functions below are narrowly granted.
create table if not exists public.staff_bootstrap_state (
  singleton boolean primary key default true check (singleton),
  completed_at timestamptz,
  completed_by uuid references auth.users(id)
);
insert into public.staff_bootstrap_state(singleton) values (true) on conflict (singleton) do nothing;
alter table public.staff_bootstrap_state enable row level security;
revoke all on public.staff_bootstrap_state from public, anon, authenticated, service_role;

create or replace function public.assign_staff_role(
  p_actor_id uuid,
  p_user_id uuid,
  p_role public.app_role
)
returns setof public.profiles
language plpgsql security definer set search_path = public as $$
declare
  actor_role public.app_role;
  target_role public.app_role;
begin
  if p_actor_id is null or p_user_id is null or p_role is null then
    raise exception 'actor, target, and role are required';
  end if;
  if p_user_id = p_actor_id then
    raise exception 'administrators cannot change their own role';
  end if;

  -- Serialize admin grants/demotions so two simultaneous requests cannot
  -- accidentally remove the final administrator.
  perform pg_advisory_xact_lock(731420250116::bigint);
  select role into actor_role from public.profiles where id = p_actor_id for update;
  if not found or actor_role <> 'admin'::public.app_role then
    raise exception 'only an existing platform administrator may assign staff roles';
  end if;
  select role into target_role from public.profiles where id = p_user_id for update;
  if not found then
    raise exception 'target staff profile is missing; run the Auth profile backfill first';
  end if;
  if target_role = 'admin'::public.app_role and p_role <> 'admin'::public.app_role
     and (select count(*) from public.profiles where role = 'admin'::public.app_role) <= 1 then
    raise exception 'the last platform administrator cannot be downgraded';
  end if;

  return query update public.profiles
     set role = p_role
   where id = p_user_id
   returning *;
end $$;

revoke all on function public.assign_staff_role(uuid, uuid, public.app_role) from public, anon, authenticated;
grant execute on function public.assign_staff_role(uuid, uuid, public.app_role) to service_role;

-- Only the trusted database owner can run this function from the Supabase SQL
-- Editor. It consumes a singleton marker, verifies the exact existing,
-- email-confirmed Auth user, and refuses to run again once an admin exists.
create or replace function public.bootstrap_first_admin(p_user_id uuid)
returns void
language plpgsql security definer set search_path = public as $$
declare
  target_confirmed_at timestamptz;
  was_bootstrapped timestamptz;
begin
  if p_user_id is null then raise exception 'provide the exact Auth user UUID'; end if;
  perform pg_advisory_xact_lock(731420250116::bigint);
  select completed_at into was_bootstrapped
    from public.staff_bootstrap_state where singleton = true for update;
  if was_bootstrapped is not null then
    raise exception 'initial administrator bootstrap has already been consumed';
  end if;
  if exists (select 1 from public.profiles where role = 'admin'::public.app_role) then
    raise exception 'an administrator already exists; use the staff administration screen';
  end if;
  select email_confirmed_at into target_confirmed_at
    from auth.users where id = p_user_id;
  if not found or target_confirmed_at is null then
    raise exception 'target must be the exact UUID of an existing email-confirmed Auth user';
  end if;
  update public.profiles set role = 'admin'::public.app_role where id = p_user_id;
  if not found then raise exception 'profile backfill is missing; run migration 0012 again'; end if;
  update public.staff_bootstrap_state
     set completed_at = now(), completed_by = p_user_id
   where singleton = true;
end $$;

revoke all on function public.bootstrap_first_admin(uuid) from public, anon, authenticated, service_role;
grant execute on function public.bootstrap_first_admin(uuid) to postgres;
