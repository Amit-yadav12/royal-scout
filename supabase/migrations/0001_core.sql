-- ============================================================================
-- 0001_core.sql — project, dataset, upload and identity scaffolding
--
-- Design rules enforced here:
--   * gameplay/analytics data is append-only per dataset version — a "reprocess"
--     creates a new dataset_versions row, it never mutates history;
--   * every ingested object is traceable to an upload, a SHA-256 hash and the
--     archive entry (if any) it came from;
--   * soft references only between raw sources collected from external providers.
-- ============================================================================

create extension if not exists "pgcrypto";
create extension if not exists "citext";

-- ---------------------------------------------------------------- primitives
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end $$;

-- Roles live in a separate table so RLS policies can read them without recursion
-- on public.profiles.
do $$ begin
  create type public.app_role as enum ('viewer','analyst','scout','admin');
exception when duplicate_object then null; end $$;

create table if not exists public.profiles (
  id            uuid primary key references auth.users(id) on delete cascade,
  email         citext,
  display_name  text,
  role          public.app_role not null default 'viewer',
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
drop trigger if exists trg_profiles_updated on public.profiles;
create trigger trg_profiles_updated before update on public.profiles
  for each row execute function public.set_updated_at();

-- Auto-provision a profile for every new auth user. New users start as viewer;
-- elevation is an explicit admin action, never inferred from an email domain.
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
begin
  insert into public.profiles (id, email, display_name)
  values (new.id, new.email, coalesce(new.raw_user_meta_data->>'full_name', split_part(new.email,'@',1)))
  on conflict (id) do nothing;
  return new;
end $$;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

create or replace function public.current_role()
returns public.app_role language sql stable security definer set search_path = public as $$
  select coalesce((select role from public.profiles where id = auth.uid()), 'viewer'::public.app_role);
$$;

create or replace function public.can_write()
returns boolean language sql stable as $$
  select public.current_role() in ('analyst','scout','admin');
$$;

-- ------------------------------------------------------------------ projects
create table if not exists public.projects (
  id           text primary key,
  name         text not null,
  description  text,
  created_by   uuid references auth.users(id) on delete set null,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
drop trigger if exists trg_projects_updated on public.projects;
create trigger trg_projects_updated before update on public.projects
  for each row execute function public.set_updated_at();

-- ------------------------------------------------------- datasets + versions
create table if not exists public.datasets (
  id                  text primary key,               -- ds_xxxxxxxx
  project_id          text not null references public.projects(id) on delete cascade,
  name                text not null,
  description         text,
  is_fixture          boolean not null default false, -- synthetic test data flag
  active_version      integer,
  created_by          uuid references auth.users(id) on delete set null,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);
create index if not exists datasets_project_idx on public.datasets (project_id);
drop trigger if exists trg_datasets_updated on public.datasets;
create trigger trg_datasets_updated before update on public.datasets
  for each row execute function public.set_updated_at();

create table if not exists public.dataset_versions (
  id                 uuid primary key default gen_random_uuid(),
  dataset_id         text not null references public.datasets(id) on delete cascade,
  version            integer not null,
  status             text not null default 'processing'
                     check (status in ('processing','ready','failed','superseded')),
  model_version      text,
  config_fingerprint text,
  quality_score      numeric(5,2),
  record_counts      jsonb not null default '{}'::jsonb,
  limitations        jsonb not null default '[]'::jsonb,
  bundle_object      text,        -- storage object path for the analytical bundle
  created_at         timestamptz not null default now(),
  published_at       timestamptz,
  unique (dataset_id, version)
);
create index if not exists dataset_versions_lookup_idx on public.dataset_versions (dataset_id, version desc);

-- ------------------------------------------------------------ uploaded files
create table if not exists public.uploads (
  id            uuid primary key default gen_random_uuid(),
  project_id    text not null references public.projects(id) on delete cascade,
  dataset_id    text references public.datasets(id) on delete cascade,
  job_id        text,
  filename      text not null,
  storage_bucket text,
  storage_object text,
  size_bytes    bigint,
  sha256        text,
  created_by    uuid references auth.users(id) on delete set null,
  created_at    timestamptz not null default now()
);
create index if not exists uploads_dataset_idx on public.uploads (dataset_id);
create index if not exists uploads_sha_idx on public.uploads (sha256);

-- One row per file the engine actually inspected, including archive members.
-- A file is never silently skipped: status is always explicit.
create table if not exists public.source_files (
  id                uuid primary key default gen_random_uuid(),
  dataset_version_id uuid references public.dataset_versions(id) on delete cascade,
  upload_id         uuid references public.uploads(id) on delete set null,
  path              text not null,
  display_name      text not null,
  origin            text,                -- upload | archive:<name> | nested:<depth>
  kind              text not null,       -- csv|tsv|excel|json|xml|parquet|pdf|docx|archive|unknown
  size_bytes        bigint,
  sha256            text,
  status            text not null check (status in ('processed','failed','unsupported','empty','duplicate')),
  reason            text,                -- always populated when status <> 'processed'
  tables_found      integer not null default 0,
  record_type       text,
  row_count         integer,
  created_at        timestamptz not null default now()
);
create index if not exists source_files_version_idx on public.source_files (dataset_version_id);

create table if not exists public.archive_entries (
  id                 uuid primary key default gen_random_uuid(),
  dataset_version_id uuid references public.dataset_versions(id) on delete cascade,
  archive_path       text not null,
  entry_name         text not null,
  size_bytes         bigint,
  compressed_bytes   bigint,
  is_dir             boolean not null default false,
  encrypted          boolean not null default false,
  depth              integer not null default 1,
  extracted          boolean not null default false,
  rejected_reason    text,
  created_at         timestamptz not null default now()
);
create index if not exists archive_entries_version_idx on public.archive_entries (dataset_version_id);
