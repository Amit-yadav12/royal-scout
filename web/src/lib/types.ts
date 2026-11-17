/**
 * Shapes of the analytical bundle produced by the Python engine.
 * These mirror `engine/royalscout/pipeline.py`; unknown extra keys are allowed so
 * the UI never breaks when the engine adds a field.
 */
export type Discipline = "batting" | "bowling";
export type Grade = "A" | "B" | "C" | "D";

export interface PlayerRow {
  rank?: number;
  player: string;
  teams: string[];
  competitions?: string[];
  seasons?: (string | number)[];
  records?: number | null;
  primary_role?: string | null;
  secondary_role?: string | null;
  role_basis?: string | null;
  matches?: number | null;
  innings: number;
  // batting
  runs?: number | null;
  balls_faced?: number | null;
  fours?: number | null;
  sixes?: number | null;
  boundary_pct?: number | null;
  not_outs?: number | null;
  dismissals?: number | null;
  average?: number | null;
  strike_rate?: number | null;
  runs_per_innings?: number | null;
  highest_score?: number | null;
  scores_30?: number | null;
  scores_50?: number | null;
  scores_100?: number | null;
  ducks?: number | null;
  // bowling
  overs?: string | null;
  legal_balls?: number | null;
  runs_conceded?: number | null;
  wickets?: number | null;
  economy?: number | null;
  bowling_strike_rate?: number | null;
  wickets_per_innings?: number | null;
  best_bowling?: string | null;
  multi_wicket_innings?: number | null;
  bowler_type?: string | null;
  // shared scores
  dot_pct?: number | null;
  consistency?: number | null;
  reliability?: number | null;
  performance_score?: number | null;
  pressure_score?: number | null;
  role_adjusted_score?: number | null;
  confidence_score?: number | null;
  wicket_taking_score?: number | null;
  economy_containment_score?: number | null;
  recent_form_score?: number | null;
  grade?: Grade;
  rabi?: number | null;
  rabi_bowl?: number | null;
  score_coverage?: number | null;
  exposure_balls?: number | null;
  granularity?: string;
  eligibility_reason?: string | null;
  // full metrics only (not in slim scope rows)
  confidence?: { grade: Grade; score: number; exposure: number; coverage: number; ci_width: number | null; reasons: string[] };
  consistency_detail?: Record<string, unknown>;
  pressure_detail?: Record<string, unknown>;
  role_detail?: Record<string, unknown>;
  performance_components?: Record<string, number | null>;
  component_weights_applied?: Record<string, number>;
  method?: Record<string, unknown>;
  unavailable?: Record<string, string>;
  opposition_adjusted?: { score: number | null; basis: string; coverage: number; detail?: Record<string, unknown> };
  match_impact?: { score: number | null; basis: string };
  ppi?: {
    ppi: number | null;
    coverage: number;
    discipline: string;
    components: Record<string, number | null>;
    missing_components: string[];
    applied_weights: Record<string, number>;
    interpretation: string;
  };
}

export interface ScopeDefinition {
  type: string;
  label: string;
  filter: Record<string, string[]>;
}

export interface ScopePayload {
  scope: ScopeDefinition;
  batters: PlayerRow[];
  bowlers: PlayerRow[];
  batters_evaluated: number;
  bowlers_evaluated: number;
  batters_eligible: number;
  bowlers_eligible: number;
}

export interface FileLog {
  path: string;
  display_name: string;
  size_bytes: number;
  kind: string;
  status: string;
  reason: string | null;
  sha256: string | null;
  tables_found: number;
  record_type: string | null;
  rows: number;
  origin: string | null;
}

export interface ArchiveEntryLog {
  name: string;
  size_bytes: number;
  compressed_size: number;
  is_dir: boolean;
  encrypted: boolean;
  reason: string | null;
  duplicate_of: string | null;
  nested_depth: number;
  supported: boolean;
}

export interface MappingRow {
  column: string;
  field: string;
  confidence: number;
  method: string;
  dtype: string;
  samples: string[];
  required: boolean;
  ambiguous_with: string[];
  needs_review: boolean;
  evidence: string;
}

export interface TableProfileRow {
  source_path: string;
  container: string;
  table_name: string;
  row_count: number;
  column_count: number;
  columns: string[];
  record_type: string;
  record_type_scores: { record_type: string; score: number; matched: string[]; missing: string[] }[];
  header_row: number;
  needs_review: boolean;
  notes: string[];
  meta: Record<string, unknown>;
  mapping: MappingRow[];
}

export interface QualityFinding {
  code: string;
  severity: "high" | "medium" | "low";
  message: string;
  count: number;
  impact: string;
  sample: string[];
}

export interface QualityColumn {
  file: string;
  worksheet: string;
  column: string;
  canonical_field: string;
  total_records: number;
  missing: number;
  invalid: number;
  duplicate: number;
  missing_pct: number | null;
  invalid_pct: number | null;
  status: string;
  notes: string[];
}

export interface PressureRankRow {
  rank: number;
  player_id: number;
  player_name: string | null;
  pri: number;
  p_balls: number;
  p_sr?: number | null;
  p_econ?: number | null;
  p_wk_rate?: number | null;
  rank_median?: number | null;
  rank_p05?: number | null;
  rank_p95?: number | null;
  p_top10?: number | null;
  pressure_balls?: number;
  pressure_matches?: number;
  pressure_innings?: number;
  ipl_rank?: number | null;
  t20i_rank?: number | null;
  median_rank_across_methods?: number | null;
  methods_with_top10?: number;
  methods_available?: number;
  seasons_above_baseline?: number;
  seasons_evaluated?: number;
  gate_pass?: boolean;
  confirmed?: boolean;
  [key: string]: unknown;
}

export interface PressureRankingPool {
  batters: PressureRankRow[];
  bowlers: PressureRankRow[];
}

export interface PressureRankings {
  facts: {
    provider: string;
    primary_competitions: string[];
    deliveries_source: number;
    regulation_deliveries: number;
    primary_deliveries: number;
    other_t20_sensitivity_deliveries: number;
    matches_primary: number;
    matches_with_ball_data: number;
    super_over_deliveries_excluded: number;
    unknown_dismissal_attribution_rows: number;
    pressure_deliveries_primary: number;
    pressure_share_primary: number | null;
    pressure_wickets_per_100: number | null;
    nonpressure_wickets_per_100: number | null;
    pressure_runs_per_over: number | null;
    nonpressure_runs_per_over: number | null;
    eligibility: { pressure_balls: number; pressure_matches: number; pressure_innings: number; baseline_balls: number };
    eligible_primary: { batters: number; bowlers: number };
    robustness: Record<string, { alternative_methods: number; rank_columns: number; final_candidates: number; confirmed_candidates: number }>;
    bootstrap_resamples: number;
    ranked_output_limit: number;
    identity_merges: Record<string, unknown>[];
  };
  primary: PressureRankingPool;
  final: PressureRankingPool;
  robustness: Record<string, Record<string, unknown>[]>;
  ipl_robustness: PressureRankingPool;
  t20i_robustness: PressureRankingPool;
  other_t20_sensitivity: PressureRankingPool;
}

export interface Bundle {
  meta: {
    project_id: string;
    dataset_id: string;
    name: string;
    dataset_version: number;
    created_at: string;
    model_version: string;
    config_fingerprint: string;
    config: Record<string, any>;
    is_fixture: boolean;
    processing_seconds: number | null;
    limitations: string[];
    data_source_note: string;
  };
  ingestion: {
    summary: Record<string, number>;
    files: FileLog[];
    archive_entries: ArchiveEntryLog[];
    originals: { name: string; stored_as: string; bytes: number; sha256: string }[];
    duplicates: { file: string; duplicate_of: string; sha256: string }[];
    duration_seconds: number;
  };
  schema: {
    tables: TableProfileRow[];
    capabilities: Record<string, boolean>;
    unmapped_tables: { source_path: string; table: string; rows: number; columns: string[]; reason: string }[];
    players: {
      players: { player: string; aliases: string[]; teams: string[] }[];
      suggested_merges: { a: string; b: string; similarity: number; shared_team: boolean; action_required: string }[];
      identity_conflicts: { player: string; issue: string; teams: string[]; resolution: string }[];
      auto_merged_variants: number;
    };
    derivations: { kind: string; player?: string; reason: string; lineage?: Record<string, unknown> }[];
    derivations_total: number;
    player_attributes: Record<string, { declared_role?: string; batting_hand?: string; bowling_style?: string }>;
  };
  quality: {
    score: number;
    components: Record<string, number>;
    summary: Record<string, number>;
    columns: QualityColumn[];
    findings: QualityFinding[];
  };
  roles: Record<string, {
    primary_role: string;
    secondary_role: string | null;
    role_basis: string;
    keeper_confidence: string;
    batting_innings: number;
    balls_faced: number;
    legal_balls_bowled: number;
    wickets: number;
    notes: string[];
    eligibility_warning: string | null;
  }>;
  batting: {
    players: Record<string, PlayerRow>;
    splits: Record<string, Record<string, Record<string, number | null>>>;
    leaderboard: { rows: PlayerRow[]; excluded_sample: { player: string; reason: string }[]; scope: ScopeDefinition };
  };
  bowling: {
    players: Record<string, PlayerRow>;
    splits: Record<string, Record<string, Record<string, number | null>>>;
    leaderboard: { rows: PlayerRow[]; excluded_sample: { player: string; reason: string }[]; scope: ScopeDefinition };
  };
  leaderboards: {
    global: {
      batters: PlayerRow[];
      bowlers: PlayerRow[];
      batters_eligible: number;
      bowlers_eligible: number;
      batters_evaluated: number;
      bowlers_evaluated: number;
      batters_excluded: { player: string; reason: string; exposure: number; innings: number }[];
      bowlers_excluded: { player: string; reason: string; exposure: number; innings: number }[];
    };
    scopes: ScopePayload[];
  };
  pressure_rankings?: PressureRankings | null;
  scope_precomputation?: { budget: number; generated: number; potential: number; truncated: boolean };
  pressure: {
    phases: {
      batting: Record<string, Record<string, any>>;
      bowling: Record<string, Record<string, any>>;
      available: boolean;
    } | null;
    scenarios: { id: string; label: string; definition: string }[];
    basis: string;
    batting: Record<string, { score: number | null; basis: string; detail: Record<string, any> }>;
    bowling: Record<string, { score: number | null; basis: string; detail: Record<string, any> }>;
    ppi_batting: Record<string, any>;
    ppi_bowling: Record<string, any>;
    phases_available: boolean;
  };
  stability: {
    batting: StabilityReport;
    bowling: StabilityReport;
  };
  metric_availability: { metric: string; category: string; status: string; note: string }[];
  settings: Record<string, any>;
  counts: Record<string, number>;
}

export interface StabilityReport {
  discipline: string;
  variants: {
    variant: string;
    spearman_vs_baseline: number | null;
    top30_overlap: number;
    top30_changes: number;
    players_ranked: number;
    config_delta: string;
  }[];
  per_player: {
    player: string;
    baseline_rank: number | null;
    min_rank: number;
    max_rank: number;
    rank_spread: number;
    stability_score: number;
    assessments: number;
  }[];
  mean_spearman: number | null;
  min_spearman: number | null;
  interpretation: string;
}
