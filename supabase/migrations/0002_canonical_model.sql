-- ============================================================================
-- 0002_canonical_model.sql — the canonical cricket model
--
-- Raw provider data is normalised into this shape before any metric is computed.
-- Every ball-level row is optional: when a dataset only contains aggregates the
-- ball_events table is simply empty and the engine reports the corresponding
-- metrics as unavailable instead of guessing.
-- ============================================================================

-- ------------------------------------------------------- reference entities
create table if not exists public.competitions (
  id            uuid primary key default gen_random_uuid(),
  project_id    text not null references public.projects(id) on delete cascade,
  name          text not null,
  short_name    text,
  level         text,                       -- international | domestic | franchise
  created_at    timestamptz not null default now(),
  unique (project_id, name)
);

create table if not exists public.seasons (
  id            uuid primary key default gen_random_uuid(),
  competition_id uuid not null references public.competitions(id) on delete cascade,
  label         text not null,              -- e.g. '2025'
  start_date    date,
  end_date      date,
  unique (competition_id, label)
);

create table if not exists public.teams (
  id            uuid primary key default gen_random_uuid(),
  project_id    text not null references public.projects(id) on delete cascade,
  name          text not null,
  short_name    text,
  home_venue    text,
  created_at    timestamptz not null default now(),
  unique (project_id, name)
);

create table if not exists public.venues (
  id            uuid primary key default gen_random_uuid(),
  project_id    text not null references public.projects(id) on delete cascade,
  name          text not null,
  city          text,
  country       text,
  unique (project_id, name)
);

-- -------------------------------------------------------------- player identity
-- Identity resolution is explicit and reviewable: the engine never silently merges
-- two spellings of a name. `review_status` drives the review queue in the UI.
create table if not exists public.players (
  id             uuid primary key default gen_random_uuid(),
  project_id     text not null references public.projects(id) on delete cascade,
  canonical_name text not null,
  batting_hand   text check (batting_hand in ('right','left','unknown')),
  bowling_style  text,
  primary_role   text,                     -- batter | bowler | all-rounder | wicketkeeper
  date_of_birth  date,
  is_overseas    boolean,
  declared_attributes boolean not null default false,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  unique (project_id, canonical_name)
);
drop trigger if exists trg_players_updated on public.players;
create trigger trg_players_updated before update on public.players
  for each row execute function public.set_updated_at();

create table if not exists public.player_aliases (
  id             uuid primary key default gen_random_uuid(),
  player_id      uuid not null references public.players(id) on delete cascade,
  alias          text not null,
  alias_norm     text not null,            -- lowercased, punctuation-stripped
  source         text,                     -- which file/column introduced the alias
  confidence     numeric(4,3) not null default 1.0 check (confidence between 0 and 1),
  review_status  text not null default 'auto'
                 check (review_status in ('auto','pending','accepted','rejected')),
  reviewed_by    uuid references auth.users(id) on delete set null,
  reviewed_at    timestamptz,
  created_at     timestamptz not null default now(),
  unique (player_id, alias_norm)
);
create index if not exists player_aliases_norm_idx on public.player_aliases (alias_norm);

create table if not exists public.player_identity_reviews (
  id             uuid primary key default gen_random_uuid(),
  project_id     text not null references public.projects(id) on delete cascade,
  raw_name       text not null,
  candidate_player uuid references public.players(id) on delete set null,
  score          numeric(4,3),
  reason         text,
  status         text not null default 'open' check (status in ('open','merged','kept_separate','ignored')),
  resolved_by    uuid references auth.users(id) on delete set null,
  resolved_at    timestamptz,
  created_at     timestamptz not null default now()
);

-- -------------------------------------------------------------------- matches
create table if not exists public.matches (
  id              text primary key,        -- provider match id, or a synthetic key
  project_id      text not null references public.projects(id) on delete cascade,
  competition_id  uuid references public.competitions(id) on delete set null,
  season_id       uuid references public.seasons(id) on delete set null,
  venue_id        uuid references public.venues(id) on delete set null,
  match_date      date,
  team_a_id       uuid references public.teams(id) on delete set null,
  team_b_id       uuid references public.teams(id) on delete set null,
  winner_id       uuid references public.teams(id) on delete set null,
  result_text     text,
  format          text,                    -- T20 | ODI | Test | other
  balls_per_innings integer,
  source_file_id  uuid references public.source_files(id) on delete set null,
  created_at      timestamptz not null default now()
);
create index if not exists matches_project_idx on public.matches (project_id, match_date desc);

create table if not exists public.innings (
  id              uuid primary key default gen_random_uuid(),
  match_id        text not null references public.matches(id) on delete cascade,
  innings_number  integer not null check (innings_number between 1 and 4),
  batting_team_id uuid references public.teams(id) on delete set null,
  bowling_team_id uuid references public.teams(id) on delete set null,
  runs            integer,
  wickets         integer,
  legal_balls     integer,                 -- overs are NOT stored as decimals
  target          integer,
  created_at      timestamptz not null default now(),
  unique (match_id, innings_number)
);

-- --------------------------------------------------------- ball-by-ball layer
-- Optional, but it is the only source of true pressure/phases. Absence is
-- recorded as a capability flag on the dataset version, never as zeros.
create table if not exists public.ball_events (
  id              bigserial primary key,
  dataset_version_id uuid references public.dataset_versions(id) on delete cascade,
  match_id        text not null references public.matches(id) on delete cascade,
  innings_number  integer not null,
  over_number     integer not null,        -- 1-based
  ball_in_over    integer not null,        -- 1..6 legal, extras keep their position
  batter          text not null,
  bowler          text not null,
  team_batting    text,
  team_bowling    text,
  runs_batter     integer not null default 0,
  runs_extras     integer not null default 0,
  extra_type      text,
  is_wicket       boolean not null default false,
  wicket_type     text,
  is_legal        boolean not null default true,
  phase           text generated always as (
                    case when over_number <= 6 then 'powerplay'
                         when over_number <= 15 then 'middle'
                         else 'death' end) stored,
  score_before    integer,
  wickets_before  integer,
  target          integer,
  created_at      timestamptz not null default now()
);
create index if not exists ball_events_match_idx on public.ball_events (match_id, innings_number, over_number);
create index if not exists ball_events_batter_idx on public.ball_events (batter);
create index if not exists ball_events_bowler_idx on public.ball_events (bowler);

-- ------------------------------------------------ player-match / performance
create table if not exists public.batting_innings (
  id              uuid primary key default gen_random_uuid(),
  dataset_version_id uuid references public.dataset_versions(id) on delete cascade,
  player_id       uuid references public.players(id) on delete set null,
  match_id        text not null references public.matches(id) on delete cascade,
  innings_number  integer not null,
  position        integer,
  runs            integer not null default 0,
  balls_faced     integer,
  fours           integer default 0,
  sixes           integer default 0,
  dot_balls       integer,
  is_not_out      boolean,
  dismissal_type  text,
  dismissal_bowler text,
  balls_derived   boolean not null default false,  -- true when back-calculated
  source_file_id  uuid references public.source_files(id) on delete set null
);
create index if not exists batting_innings_player_idx on public.batting_innings (player_id);
create unique index if not exists batting_innings_unique on public.batting_innings (dataset_version_id, match_id, innings_number, player_id);

create table if not exists public.bowling_spells (
  id              uuid primary key default gen_random_uuid(),
  dataset_version_id uuid references public.dataset_versions(id) on delete cascade,
  player_id       uuid references public.players(id) on delete set null,
  match_id        text not null references public.matches(id) on delete cascade,
  innings_number  integer not null,
  legal_balls     integer,                 -- converted from overs notation, never decimal
  runs_conceded   integer,
  wickets         integer default 0,
  dot_balls       integer,
  wides           integer,
  no_balls        integer,
  overs_raw       text,                    -- original notation, kept for audit
  overs_flag      text,                    -- set when the source notation was illegal
  source_file_id  uuid references public.source_files(id) on delete set null
);
create index if not exists bowling_spells_player_idx on public.bowling_spells (player_id);
create unique index if not exists bowling_spells_unique on public.bowling_spells (dataset_version_id, match_id, innings_number, player_id);

create table if not exists public.player_matches (
  id              uuid primary key default gen_random_uuid(),
  dataset_version_id uuid references public.dataset_versions(id) on delete cascade,
  player_id       uuid references public.players(id) on delete set null,
  match_id        text not null references public.matches(id) on delete cascade,
  team_id         uuid references public.teams(id) on delete set null,
  opposition_id   uuid references public.teams(id) on delete set null,
  played          boolean not null default true,
  unique (dataset_version_id, player_id, match_id)
);

-- ------------------------------------------------------- computed analytics
create table if not exists public.batting_metrics (
  id              uuid primary key default gen_random_uuid(),
  dataset_version_id uuid references public.dataset_versions(id) on delete cascade,
  player_id       uuid references public.players(id) on delete cascade,
  metric          text not null,
  value           numeric,
  percentile      numeric,
  shrunk_value    numeric,
  sample          integer,                 -- the denominator actually used
  confidence      text check (confidence in ('A','B','C','D')),
  coverage        numeric(4,3),
  unavailable_reason text,                 -- populated instead of a fake number
  unique (dataset_version_id, player_id, metric)
);

create table if not exists public.bowling_metrics (
  id              uuid primary key default gen_random_uuid(),
  dataset_version_id uuid references public.dataset_versions(id) on delete cascade,
  player_id       uuid references public.players(id) on delete cascade,
  metric          text not null,
  value           numeric,
  percentile      numeric,
  shrunk_value    numeric,
  sample          integer,
  confidence      text check (confidence in ('A','B','C','D')),
  coverage        numeric(4,3),
  unavailable_reason text,
  unique (dataset_version_id, player_id, metric)
);

create table if not exists public.player_scores (
  id              uuid primary key default gen_random_uuid(),
  dataset_version_id uuid references public.dataset_versions(id) on delete cascade,
  player_id       uuid references public.players(id) on delete cascade,
  discipline      text not null check (discipline in ('batting','bowling')),
  scope_label     text not null default 'All data',
  components      jsonb not null default '{}'::jsonb,
  applied_weights jsonb not null default '{}'::jsonb,
  missing_components jsonb not null default '[]'::jsonb,
  coverage        numeric(4,3),
  grade           text check (grade in ('A','B','C','D')),
  score           numeric,
  global_rank     integer,
  scoped_rank     integer,
  unique (dataset_version_id, player_id, discipline, scope_label)
);
