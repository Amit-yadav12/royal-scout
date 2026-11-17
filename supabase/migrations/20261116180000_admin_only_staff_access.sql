-- Collapse ingestion privileges to the bootstrapped administrator. All other
-- authenticated accounts remain read-only viewers; admin elevation stays a
-- one-time database-owner bootstrap operation.

update public.profiles
   set role = 'viewer'::public.app_role
 where role in ('analyst'::public.app_role, 'scout'::public.app_role);

alter table public.profiles
  add constraint profiles_viewer_or_admin_only
  check (role in ('viewer'::public.app_role, 'admin'::public.app_role));

-- Enforce one administrator at the database layer as well as in the UI/API.
create unique index profiles_single_platform_admin
  on public.profiles (role)
  where role = 'admin'::public.app_role;

-- Keep the server-only role RPC for demotion to read-only, but never allow it
-- to grant analyst, scout, or another admin. Admin elevation is bootstrap-only.
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
  if p_role <> 'viewer'::public.app_role then
    raise exception 'only read-only viewer access may be assigned; administrator access is bootstrap-only';
  end if;
  if p_user_id = p_actor_id then
    raise exception 'administrators cannot change their own role';
  end if;

  perform pg_advisory_xact_lock(731420250116::bigint);
  select role into actor_role from public.profiles where id = p_actor_id for update;
  if not found or actor_role <> 'admin'::public.app_role then
    raise exception 'only the existing platform administrator may manage account access';
  end if;
  select role into target_role from public.profiles where id = p_user_id for update;
  if not found then
    raise exception 'target account profile is missing; run the Auth profile backfill first';
  end if;
  if target_role = 'admin'::public.app_role
     and (select count(*) from public.profiles where role = 'admin'::public.app_role) <= 1 then
    raise exception 'the sole platform administrator cannot be downgraded';
  end if;

  return query update public.profiles
     set role = 'viewer'::public.app_role
   where id = p_user_id
   returning *;
end $$;

revoke all on function public.assign_staff_role(uuid, uuid, public.app_role) from public, anon, authenticated;
grant execute on function public.assign_staff_role(uuid, uuid, public.app_role) to service_role;
