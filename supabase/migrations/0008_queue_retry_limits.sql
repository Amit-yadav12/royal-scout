-- Ensure queued rows cannot bypass the configured attempt limit (including
-- manual retries after the final allowed attempt).
create or replace function public.claim_processing_job()
returns setof public.processing_jobs
language plpgsql security definer set search_path = public as $$
declare
  claimed public.processing_jobs;
begin
  select * into claimed
    from public.processing_jobs
   where attempts < max_attempts
     and (status = 'queued' or status = 'failed')
   order by created_at
   for update skip locked
   limit 1;
  if not found then
    return;
  end if;
  update public.processing_jobs
     set status = 'running', attempts = claimed.attempts + 1,
         started_at = coalesce(claimed.started_at, now()),
         finished_at = null, stage = 'starting', error = null
   where id = claimed.id
  returning * into claimed;
  return next claimed;
end $$;
revoke all on function public.claim_processing_job() from public, anon, authenticated;
grant execute on function public.claim_processing_job() to service_role;

create or replace function public.requeue_stale_jobs(stale_after interval default interval '30 minutes')
returns integer language plpgsql security definer set search_path = public as $$
declare moved integer;
begin
  with stale as (
    update public.processing_jobs
       set status = case when attempts >= max_attempts then 'failed' else 'queued' end,
           detail = 'requeued after stale heartbeat',
           error = coalesce(error, 'worker heartbeat lost'),
           finished_at = case when attempts >= max_attempts then now() else null end
     where status = 'running' and updated_at < now() - stale_after
     returning 1
  ) select count(*) into moved from stale;
  return moved;
end $$;
revoke all on function public.requeue_stale_jobs(interval) from public, anon, authenticated;
grant execute on function public.requeue_stale_jobs(interval) to service_role;
