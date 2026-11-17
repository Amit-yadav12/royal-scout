-- Atomic, ownership-bound transition from verified uploads to a shared Supabase queue.
-- The browser and anon/authenticated roles cannot execute this RPC.

create or replace function public.enforce_upload_claim_transition()
returns trigger language plpgsql as $$
begin
  if (new.project_id, new.dataset_id, new.dataset_name, new.storage_bucket, new.storage_object,
      new.filename, new.size_bytes, new.created_by)
     is distinct from
     (old.project_id, old.dataset_id, old.dataset_name, old.storage_bucket, old.storage_object,
      old.filename, old.size_bytes, old.created_by) then
    raise exception 'upload claim identity fields are immutable';
  end if;
  if new.status = old.status then
    if old.status = 'queued' and new.job_id is distinct from old.job_id then
      raise exception 'queued upload claim job ownership is immutable';
    end if;
    return new;
  end if;
  if not ((old.status = 'signed' and new.status = 'uploaded') or
          (old.status = 'uploaded' and new.status = 'queued' and new.job_id is not null)) then
    raise exception 'invalid upload claim state transition: % -> %', old.status, new.status;
  end if;
  return new;
end $$;

drop trigger if exists trg_upload_claim_transition on public.upload_claims;
create trigger trg_upload_claim_transition before update on public.upload_claims
  for each row execute function public.enforce_upload_claim_transition();

-- A queued claim is durable evidence linking the source to its job. Deleting a
-- job must not silently null that evidence or make the object queueable again.
alter table public.upload_claims drop constraint if exists upload_claims_job_id_fkey;
alter table public.upload_claims add constraint upload_claims_job_id_fkey
  foreign key (job_id) references public.processing_jobs(id) on delete restrict;

create or replace function public.queue_verified_uploads(
  p_project_id text,
  p_dataset_id text,
  p_dataset_name text,
  p_bucket text,
  p_created_by uuid,
  p_sources jsonb
)
returns setof public.processing_jobs
language plpgsql security definer set search_path = public as $$
declare
  source_count integer;
  claim_count integer;
  queued_count integer;
  distinct_jobs integer;
  existing_job_id text;
  new_job public.processing_jobs;
begin
  if p_project_id is null or p_project_id !~ '^[A-Za-z0-9_-]{1,64}$' or
     p_dataset_id is null or p_dataset_id !~ '^ds_[a-f0-9]{16}$' or
     p_dataset_name is null or length(btrim(p_dataset_name)) not between 1 and 200 or
     p_bucket is null or p_bucket !~ '^[A-Za-z0-9_-]{1,64}$' or p_created_by is null or
     p_sources is null or jsonb_typeof(p_sources) <> 'array' then
    raise exception 'invalid project, dataset, bucket, owner, or source payload';
  end if;
  source_count := jsonb_array_length(p_sources);
  if source_count < 1 or source_count > 200 then
    raise exception 'source count is outside the allowed range';
  end if;
  if exists (
    select 1 from jsonb_array_elements(p_sources) as s(value)
     where jsonb_typeof(s.value) <> 'object'
        or coalesce(s.value->>'bucket', '') <> p_bucket
        or coalesce(s.value->>'path', '') = ''
        or (s.value->>'path') !~ ('^' || p_project_id || '/' || p_dataset_id || '/[^/]+$')
        or position('..' in (s.value->>'path')) > 0
        or position(E'\\' in (s.value->>'path')) > 0
  ) then
    raise exception 'one or more source references are outside the claimed project/dataset/bucket';
  end if;
  if (select count(distinct s.value->>'path') from jsonb_array_elements(p_sources) as s(value)) <> source_count then
    raise exception 'duplicate source object references are not allowed';
  end if;

  -- Lock all matching claims before checking state. Concurrent submissions for
  -- these objects serialize; a repeated all-queued request returns the original job.
  perform c.id
    from public.upload_claims c
   where c.created_by = p_created_by
     and c.project_id = p_project_id
     and c.dataset_id = p_dataset_id
     and c.dataset_name = btrim(p_dataset_name)
     and c.storage_bucket = p_bucket
     and c.storage_object in (select s.value->>'path' from jsonb_array_elements(p_sources) as s(value))
   for update;

  select count(*), count(*) filter (where c.status = 'queued'), count(distinct c.job_id), min(c.job_id)
    into claim_count, queued_count, distinct_jobs, existing_job_id
    from public.upload_claims c
   where c.created_by = p_created_by
     and c.project_id = p_project_id
     and c.dataset_id = p_dataset_id
     and c.dataset_name = btrim(p_dataset_name)
     and c.storage_bucket = p_bucket
     and c.storage_object in (select s.value->>'path' from jsonb_array_elements(p_sources) as s(value));
  if claim_count <> source_count then
    raise exception 'one or more files have no matching authenticated upload claim';
  end if;
  if queued_count = source_count then
    if distinct_jobs <> 1 or existing_job_id is null then
      raise exception 'queued upload claims do not resolve to exactly one job';
    end if;
    return query select j.* from public.processing_jobs j
      where j.id = existing_job_id and j.project_id = p_project_id and
            j.dataset_id = p_dataset_id and j.created_by = p_created_by;
    if not found then raise exception 'existing queued job ownership does not match upload claims'; end if;
    return;
  end if;
  if queued_count <> 0 or exists (
    select 1 from public.upload_claims c
     where c.created_by = p_created_by and c.project_id = p_project_id
       and c.dataset_id = p_dataset_id and c.dataset_name = btrim(p_dataset_name) and c.storage_bucket = p_bucket
       and c.storage_object in (select s.value->>'path' from jsonb_array_elements(p_sources) as s(value))
       and c.status not in ('signed','uploaded')
  ) then
    raise exception 'files are already queued or have an invalid ownership state';
  end if;

  update public.upload_claims c set status = 'uploaded'
   where c.created_by = p_created_by and c.project_id = p_project_id
     and c.dataset_id = p_dataset_id and c.dataset_name = btrim(p_dataset_name) and c.storage_bucket = p_bucket
     and c.storage_object in (select s.value->>'path' from jsonb_array_elements(p_sources) as s(value))
     and c.status = 'signed';

  insert into public.processing_jobs (project_id, dataset_id, dataset_name, sources,
                                      status, stage, detail, is_fixture, created_by)
  values (p_project_id, p_dataset_id, btrim(p_dataset_name), p_sources,
          'queued', 'queued', 'verified uploaded files queued for worker processing', false, p_created_by)
  returning * into new_job;

  update public.upload_claims c set status = 'queued', job_id = new_job.id
   where c.created_by = p_created_by and c.project_id = p_project_id
     and c.dataset_id = p_dataset_id and c.dataset_name = btrim(p_dataset_name) and c.storage_bucket = p_bucket
     and c.storage_object in (select s.value->>'path' from jsonb_array_elements(p_sources) as s(value))
     and c.status = 'uploaded';
  get diagnostics claim_count = row_count;
  if claim_count <> source_count then
    raise exception 'not all upload claims transitioned to queued; transaction rolled back';
  end if;
  return next new_job;
end $$;

revoke all on function public.queue_verified_uploads(text, text, text, text, uuid, jsonb) from public, anon, authenticated;
grant execute on function public.queue_verified_uploads(text, text, text, text, uuid, jsonb) to service_role;
