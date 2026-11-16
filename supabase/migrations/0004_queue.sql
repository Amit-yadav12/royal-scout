-- ============================================================================
-- 0004_queue.sql — database-backed job queue consumed by the worker
--
-- The web tier only inserts rows here; the worker (Railway/Render) claims them.
-- No heavy work ever happens inside a serverless request, and a crashed worker
-- leaves a stale `running` row that the recovery function below can requeue.
-- ============================================================================

create table if not exists public.processing_jobs (
  id            text primary key default ('job_' || encode(gen_random_bytes(8), 'hex')),
  project_id    text not null,
  dataset_id    text not null,
  dataset_name  text not null default 'dataset',
  sources       jsonb not null default '[]'::jsonb,  -- [{bucket,path}] or [{local_path}]
  status        text not null default 'queued'
                check (status in ('queued','running','succeeded','failed','cancelled')),
  progress      numeric(5,2) not null default 0 check (progress between 0 and 100),
  stage         text not null default 'queued',
  detail        text not null default '',
  attempts      integer not null default 0,
  max_attempts  integer not null default 3,
  is_fixture    boolean not null default false,
  result        jsonb not null default '{}'::jsonb,
  error         text,
  created_by    uuid references auth.users(id) on delete set null,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  started_at    timestamptz,
  finished_at   timestamptz
);
create index if not exists processing_jobs_status_idx on public.processing_jobs (status, created_at);
create index if not exists processing_jobs_project_idx on public.processing_jobs (project_id, created_at desc);

drop trigger if exists trg_jobs_updated on public.processing_jobs;
create trigger trg_jobs_updated before update on public.processing_jobs
  for each row execute function public.set_updated_at();

create table if not exists public.processing_logs (
  id         bigserial primary key,
  job_id     text not null references public.processing_jobs(id) on delete cascade,
  stage      text not null,
  message    text not null,
  progress   numeric(5,2),
  created_at timestamptz not null default now()
);
create index if not exists processing_logs_job_idx on public.processing_logs (job_id, created_at);

-- Atomic claim used by a Postgres-native worker variant: skips locked rows so
-- several workers can run in parallel without double processing.
create or replace function public.claim_processing_job()
returns setof public.processing_jobs language plpgsql security definer set search_path = public as $$
declare
  claimed public.processing_jobs;
begin
  select * into claimed
    from public.processing_jobs
   where status = 'queued' or (status = 'failed' and attempts < max_attempts)
   order by created_at
   for update skip locked
   limit 1;
  if not found then
    return;
  end if;
  update public.processing_jobs
     set status = 'running', attempts = claimed.attempts + 1,
         started_at = coalesce(claimed.started_at, now()), stage = 'starting'
   where id = claimed.id
  returning * into claimed;
  return next claimed;
end $$;

-- Requeue jobs whose worker died mid-flight (heartbeat older than 30 minutes).
create or replace function public.requeue_stale_jobs(stale_after interval default interval '30 minutes')
returns integer language plpgsql security definer set search_path = public as $$
declare moved integer;
begin
  with stale as (
    update public.processing_jobs
       set status = case when attempts >= max_attempts then 'failed' else 'queued' end,
           detail = 'requeued after stale heartbeat',
           error = coalesce(error, 'worker heartbeat lost')
     where status = 'running' and updated_at < now() - stale_after
     returning 1
  ) select count(*) into moved from stale;
  return moved;
end $$;

-- Progress heartbeats and terminal states are recorded as log lines too, so the
-- UI can replay exactly what happened during a run.
create or replace function public.log_job_progress(
  p_job_id text, p_stage text, p_message text, p_progress numeric default null)
returns void language plpgsql security definer set search_path = public as $$
begin
  insert into public.processing_logs (job_id, stage, message, progress)
  values (p_job_id, p_stage, p_message, p_progress);
  update public.processing_jobs
     set stage = p_stage, detail = p_message,
         progress = coalesce(p_progress, progress),
         finished_at = case when p_stage in ('complete','failed') then now() else finished_at end
   where id = p_job_id;
end $$;
