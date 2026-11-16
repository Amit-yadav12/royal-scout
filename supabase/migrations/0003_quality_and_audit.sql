-- ============================================================================
-- 0003_quality_and_audit.sql — data-quality, column audit and export records
--
-- The audit trail is a first-class product surface: every file, worksheet and
-- column is profiled, and each finding carries the impact it has on analysis.
-- ============================================================================

create table if not exists public.column_audit (
  id                 uuid primary key default gen_random_uuid(),
  dataset_version_id uuid not null references public.dataset_versions(id) on delete cascade,
  source_file_id     uuid references public.source_files(id) on delete set null,
  file_name          text not null,
  worksheet          text,
  column_name        text not null,
  total              integer not null default 0,
  missing            integer not null default 0,
  invalid            integer not null default 0,
  duplicate          integer not null default 0,
  status             text not null check (status in ('clean','partial','invalid','ignored')),
  note               text,
  created_at         timestamptz not null default now()
);
create index if not exists column_audit_version_idx on public.column_audit (dataset_version_id, status);

create table if not exists public.quality_findings (
  id                 uuid primary key default gen_random_uuid(),
  dataset_version_id uuid not null references public.dataset_versions(id) on delete cascade,
  code               text not null,          -- e.g. overs_illegal_notation
  severity           text not null check (severity in ('info','warning','high','critical')),
  category           text not null,          -- completeness | validity | consistency | plausibility
  message            text not null,
  impact             text,                   -- what it means for the analytics
  affected_rows      integer,
  affected_columns   jsonb not null default '[]'::jsonb,
  sample             jsonb not null default '[]'::jsonb,   -- a few offending values
  metric_impact      jsonb not null default '[]'::jsonb,   -- metric names this degrades
  resolved           boolean not null default false,
  created_at         timestamptz not null default now()
);
create index if not exists quality_findings_version_idx on public.quality_findings (dataset_version_id, severity);

create table if not exists public.quality_scores (
  id                 uuid primary key default gen_random_uuid(),
  dataset_version_id uuid not null references public.dataset_versions(id) on delete cascade,
  score              numeric(5,2) not null,
  components         jsonb not null default '{}'::jsonb,   -- per-dimension contributions
  weights            jsonb not null default '{}'::jsonb,
  computed_at        timestamptz not null default now()
);

-- Metric availability classification A/B/C/D, published so nobody has to guess
-- whether a blank cell means "zero" or "unknown".
create table if not exists public.metric_availability (
  id                 uuid primary key default gen_random_uuid(),
  dataset_version_id uuid not null references public.dataset_versions(id) on delete cascade,
  metric             text not null,
  category           char(1) not null check (category in ('A','B','C','D')),
  status             text not null check (status in ('available','derivable','requires_verification','unavailable')),
  note               text,
  unique (dataset_version_id, metric)
);

create table if not exists public.exports (
  id                 uuid primary key default gen_random_uuid(),
  dataset_version_id uuid references public.dataset_versions(id) on delete cascade,
  kind               text not null check (kind in ('csv','xlsx','pdf','audit_report','methodology_report')),
  filename           text not null,
  storage_bucket     text,
  storage_object     text,
  size_bytes         bigint,
  sha256             text,
  filters            jsonb not null default '{}'::jsonb,
  provenance         jsonb not null default '{}'::jsonb,  -- calc date, model + dataset version, limitations
  created_by         uuid references auth.users(id) on delete set null,
  created_at         timestamptz not null default now()
);
create index if not exists exports_version_idx on public.exports (dataset_version_id);

-- Ranking stability runs: which assumptions were perturbed, and how far players moved.
create table if not exists public.stability_runs (
  id                 uuid primary key default gen_random_uuid(),
  dataset_version_id uuid not null references public.dataset_versions(id) on delete cascade,
  discipline         text not null check (discipline in ('batting','bowling')),
  variant            text not null,
  config_delta       text,
  spearman           numeric(5,4),
  top30_overlap      integer,
  per_player         jsonb not null default '{}'::jsonb,
  created_at         timestamptz not null default now(),
  unique (dataset_version_id, discipline, variant)
);

-- Model/methodology registry so an export can always name the method it used.
create table if not exists public.model_versions (
  model_version      text primary key,
  metric_semantics_version text not null,
  config             jsonb not null,
  config_fingerprint text not null,
  notes              text,
  released_at        timestamptz not null default now()
);
