# Database setup (Supabase / PostgreSQL)

Five migrations in `supabase/migrations/`, applied in filename order. They were executed
end-to-end against PostgreSQL 17 in this repository's test environment, including the
queue functions and a synthetic insert into the canonical model.

| File | Contents |
| --- | --- |
| `0001_core.sql` | extensions, `set_updated_at`, roles (`app_role`), `profiles` + auto-provision trigger, `current_role()`, `can_write()`, `projects`, `datasets`, `dataset_versions`, `uploads`, `source_files`, `archive_entries` |
| `0002_canonical_model.sql` | competitions, seasons, teams, venues, players + aliases + identity review queue, matches, innings, `ball_events` (with a generated `phase` column), `batting_innings`, `bowling_spells`, `player_matches`, metric tables, `player_scores` |
| `0003_quality_and_audit.sql` | `column_audit`, `quality_findings`, `quality_scores`, `metric_availability` (A/B/C/D), `exports`, `stability_runs`, `model_versions` |
| `0004_queue.sql` | `processing_jobs`, `processing_logs`, `claim_processing_job()` (FOR UPDATE SKIP LOCKED), `requeue_stale_jobs()`, `log_job_progress()` |
| `0005_rls.sql` | RLS on every table: authenticated read, staff write, own-profile access, identity-review resolution, storage policy template |

## Apply

```bash
# Supabase CLI
supabase link --project-ref <ref>
supabase db push

# or plain psql
for f in supabase/migrations/*.sql; do psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f"; done
```

All migrations are idempotent (`create table if not exists`, `drop policy if exists`), so a
re-run is safe during development.

## Modelling decisions worth knowing

* **Overs are never decimals.** `bowling_spells.legal_balls` is the analytic column;
  `overs_raw` keeps the provider notation and `overs_flag` records illegal notation such as
  `4.7` instead of coercing it.
* **Ball-level data is optional.** When a dataset has no deliveries, `ball_events` is empty
  and the engine reports pressure/phases as *unavailable*. There is no "0 pressure" row.
* **Metric availability is stored, not implied.** `metric_availability` publishes A
  (available), B (derivable), C (needs external verification) and D (unavailable) per
  metric, which is what the Statistical Intelligence page renders.
* **Identity merges are reviewable.** `player_aliases` has a `review_status`; ambiguous names
  land in `player_identity_reviews` rather than being merged silently.
* **Datasets are versioned.** Reprocessing writes a new `dataset_versions` row; old versions
  become `superseded` and stay queryable, so an export made in March can still be reproduced
  in June.

## Queue contract

`processing_jobs.status ∈ {queued, running, succeeded, failed, cancelled}` with
`progress numeric(5,2)`, `stage`, `detail`, `attempts/max_attempts`, `result jsonb`.
The Python worker uses an optimistic claim (`PATCH … ?status=eq.queued`); a Postgres-native
worker can use `select * from claim_processing_job();` which skips locked rows.

Stale jobs (heartbeat older than 30 minutes) are recovered with:

```sql
select public.requeue_stale_jobs();          -- default 30 minutes
select public.requeue_stale_jobs('5 minutes');
```

## Roles and RLS

`profiles.role ∈ {viewer, analyst, scout, admin}`. Policies:

* `select` for any authenticated user on analytical tables;
* `all` for `analyst`/`scout`/`admin` on projects, datasets, uploads, players, aliases,
  identity reviews, jobs and export records;
* a user may read/update only their own profile; admins manage all.

Verify as a non-admin before going live:

```sql
set role authenticated;
select count(*) from public.players;        -- allowed
insert into public.projects(id,name) values ('x','x');  -- denied for role=viewer
reset role;
```

## Storage buckets

`uploads` (raw client files, written by the worker), `artifacts` (bundles, exports — read via
signed URLs), `fixtures` (synthetic data, labelled in the UI). All private. Template policies
live at the end of `0005_rls.sql`.

## Backup / retention

Enable Postgres PITR. Keep `dataset_versions` and `exports` indefinitely (they are the audit
trail); prune `processing_logs` and staging files older than 90 days.
