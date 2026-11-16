-- Restrict SECURITY DEFINER queue functions to trusted server-side workers.
-- Supabase secret/service_role credentials use the service_role Postgres role.
revoke all on function public.claim_processing_job() from public, anon, authenticated;
grant execute on function public.claim_processing_job() to service_role;

revoke all on function public.requeue_stale_jobs(interval) from public, anon, authenticated;
grant execute on function public.requeue_stale_jobs(interval) to service_role;

revoke all on function public.log_job_progress(text, text, text, numeric) from public, anon, authenticated;
grant execute on function public.log_job_progress(text, text, text, numeric) to service_role;
