-- ============================================================================
-- 0005_rls.sql — row level security
--
-- Posture: authenticated staff can read analytical data; only analysts/scouts/
-- admins can write; the service-role key (worker) bypasses RLS by design and is
-- never shipped to a browser. Anonymous access is denied everywhere except the
-- health check, which lives in the Next.js app rather than the database.
-- ============================================================================

do $$
declare
  t text;
  read_tables text[] := array[
    'projects','datasets','dataset_versions','uploads','source_files','archive_entries',
    'competitions','seasons','teams','venues','players','player_aliases',
    'matches','innings','ball_events','batting_innings','bowling_spells','player_matches',
    'batting_metrics','bowling_metrics','player_scores',
    'column_audit','quality_findings','quality_scores','metric_availability',
    'exports','stability_runs','model_versions','processing_jobs','processing_logs'
  ];
  write_tables text[] := array[
    'projects','datasets','uploads','players','player_aliases','player_identity_reviews',
    'processing_jobs','exports'
  ];
begin
  foreach t in array read_tables loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists "read authenticated" on public.%I', t);
    execute format($f$create policy "read authenticated" on public.%I
                      for select to authenticated using (true)$f$, t);
  end loop;

  foreach t in array write_tables loop
    execute format('drop policy if exists "write for staff" on public.%I', t);
    execute format($f$create policy "write for staff" on public.%I
                      for all to authenticated
                      using (public.can_write()) with check (public.can_write())$f$, t);
  end loop;
end $$;

-- Profiles: a user reads their own row; admins manage everybody.
alter table public.profiles enable row level security;
drop policy if exists "read own profile" on public.profiles;
create policy "read own profile" on public.profiles
  for select to authenticated using (id = auth.uid() or public.current_role() = 'admin');
drop policy if exists "update own profile" on public.profiles;
create policy "update own profile" on public.profiles
  for update to authenticated using (id = auth.uid()) with check (id = auth.uid());
drop policy if exists "admin manages profiles" on public.profiles;
create policy "admin manages profiles" on public.profiles
  for all to authenticated using (public.current_role() = 'admin') with check (public.current_role() = 'admin');

-- Identity review queue: analysts decide merges, nobody else.
alter table public.player_identity_reviews enable row level security;
drop policy if exists "read reviews" on public.player_identity_reviews;
create policy "read reviews" on public.player_identity_reviews for select to authenticated using (true);
drop policy if exists "resolve reviews" on public.player_identity_reviews;
create policy "resolve reviews" on public.player_identity_reviews
  for all to authenticated using (public.can_write()) with check (public.can_write());

-- Queue rows carry an author; keep it consistent on insert.
create or replace function public.set_job_author()
returns trigger language plpgsql as $$
begin
  if new.created_by is null then
    new.created_by := auth.uid();
  end if;
  return new;
end $$;
drop trigger if exists trg_job_author on public.processing_jobs;
create trigger trg_job_author before insert on public.processing_jobs
  for each row execute function public.set_job_author();

-- Storage buckets (create out of band, then apply these policies):
--   uploads           private  — raw client files, written by the worker/service role
--   artifacts         private  — bundles + exports, read via signed URLs
--   fixtures          private  — synthetic test data, labelled in the UI
--
-- insert into storage.buckets (id, name, public) values
--   ('uploads', 'uploads', false), ('artifacts', 'artifacts', false), ('fixtures', 'fixtures', false)
-- on conflict (id) do nothing;
--
-- create policy "staff read artifacts" on storage.objects
--   for select to authenticated using (bucket_id in ('artifacts','fixtures'));
-- create policy "staff upload" on storage.objects
--   for insert to authenticated with check (bucket_id = 'uploads');
