-- Bind signed private Storage uploads to the authenticated user, project, and
-- dataset before allowing a server-side job to consume the object references.
create table if not exists public.upload_claims (
  id uuid primary key default gen_random_uuid(),
  project_id text not null,
  dataset_id text not null,
  dataset_name text not null,
  storage_bucket text not null,
  storage_object text not null unique,
  filename text not null,
  size_bytes bigint not null check (size_bytes >= 0),
  created_by uuid not null references auth.users(id) on delete cascade,
  status text not null default 'signed' check (status in ('signed','uploaded','queued')),
  job_id text references public.processing_jobs(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists upload_claims_owner_dataset_idx
  on public.upload_claims (created_by, project_id, dataset_id, status);
drop trigger if exists trg_upload_claims_updated on public.upload_claims;
create trigger trg_upload_claims_updated before update on public.upload_claims
  for each row execute function public.set_updated_at();
alter table public.upload_claims enable row level security;
-- No user-facing policies: only trusted server key endpoints may inspect claims.
revoke all on public.upload_claims from anon, authenticated;
grant all on public.upload_claims to service_role;
