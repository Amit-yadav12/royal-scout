-- Profile self-service updates may change display metadata, never access level.
-- Trusted server-side service-role administration remains responsible for role
-- changes; authenticated admins may manage roles through audited admin tooling.
create or replace function public.guard_profile_role_changes()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  if new.role is distinct from old.role and auth.uid() is not null then
    raise exception 'staff roles can only be changed by trusted server-side administrator operations';
  end if;
  return new;
end $$;

drop trigger if exists trg_guard_profile_role_changes on public.profiles;
create trigger trg_guard_profile_role_changes before update on public.profiles
  for each row execute function public.guard_profile_role_changes();

-- Avoid an update policy accidentally granting privilege changes to the row's
-- owner: the trigger above is the invariant, independent of future policies.
