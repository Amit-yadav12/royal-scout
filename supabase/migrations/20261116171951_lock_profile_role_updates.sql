-- Users may edit their own display name, but must never be able to grant
-- themselves a privileged role through the profiles table. Role changes are
-- reserved for the trusted Supabase/admin provisioning workflow.
revoke update on table public.profiles from authenticated;
grant update (display_name) on table public.profiles to authenticated;

comment on column public.profiles.role is
  'Privileged staff role; never user-editable. Grant changes only through trusted admin provisioning.';
