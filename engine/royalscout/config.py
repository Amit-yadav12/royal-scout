"""Central, serialisable configuration for Royal Scout.

Every threshold, weight and limit used by the analytics stack lives here so that:

1. the UI can display exactly what was used (provenance), and
2. the sensitivity / ranking-stability engine can permute them reproducibly.

Nothing in this file is a "magic number" that has not been reasoned about; the
`justification` docstrings explain the reasoning. Values are *defaults* and can be
overridden per-dataset via the API or environment.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Literal

MODEL_VERSION = "1.0.0"
METRIC_SEMANTICS_VERSION = "1.0.0"


# --------------------------------------------------------------------------
# Ingestion limits (configurable; NOT a universal unchangeable file size cap)
# --------------------------------------------------------------------------
@dataclass
class IngestionLimits:
    """Guards against archive bombs and runaway extraction.

    Defaults are conservative but generous for cricket scouting archives
    (hundreds of files / a few GB). Override via env for bigger workers.
    """

    max_files_per_upload: int = int(os.getenv("RS_MAX_FILES_PER_UPLOAD", "5000"))
    max_single_file_bytes: int = int(os.getenv("RS_MAX_FILE_BYTES", str(2 * 1024**3)))
    max_total_extracted_bytes: int = int(os.getenv("RS_MAX_EXTRACTED_BYTES", str(20 * 1024**3)))
    max_archive_entries: int = int(os.getenv("RS_MAX_ARCHIVE_ENTRIES", "5000"))
    max_compression_ratio: float = float(os.getenv("RS_MAX_COMPRESSION_RATIO", "200"))
    max_nested_archive_depth: int = int(os.getenv("RS_MAX_NESTED_DEPTH", "3"))
    max_path_depth: int = 12
    max_table_rows_per_file: int = int(os.getenv("RS_MAX_TABLE_ROWS", "50000000"))
    max_sheets_per_workbook: int = int(os.getenv("RS_MAX_SHEETS", "200"))
    allow_ocr: bool = False  # optional capability, activated only if a provider is configured
    sniff_bytes: int = 64 * 1024


# --------------------------------------------------------------------------
# Column mapping
# --------------------------------------------------------------------------
@dataclass
class MappingConfig:
    exact_alias_confidence: float = 1.0
    normalised_alias_confidence: float = 0.92
    fuzzy_floor: float = 0.72
    ambiguous_margin: float = 0.06  # two candidates within this margin => needs review
    min_record_type_score: float = 0.34  # below this, table is left unmapped for review


# --------------------------------------------------------------------------
# Eligibility gates for ranking
# --------------------------------------------------------------------------
@dataclass
class Eligibility:
    """Minimum exposure before a player may appear in a *ranked* leaderboard.

    Expressed in balls (the honest exposure denominator for rate metrics) so a
    batter who faced 40 balls cannot outrank a batter who faced 2,000. These are
    deliberately low for the *display* threshold and higher for the *ranked*
    threshold; both are reported to the user.
    """

    bat_min_balls_ranked: int = 150
    bat_min_innings_ranked: int = 3
    bat_min_balls_display: int = 1
    bowl_min_balls_ranked: int = 120
    bowl_min_innings_ranked: int = 3
    bowl_min_balls_display: int = 1
    leaderboard_size: int = 30


# --------------------------------------------------------------------------
# Statistical settings
# --------------------------------------------------------------------------
@dataclass
class StatsConfig:
    """Shrinkage + confidence settings.

    `prior_strength_balls` (k) is the number of balls at which the player's own
    rate is weighted equally with the population baseline. 240 balls is roughly
    20 T20 innings of 12 balls, i.e. the point at which a T20 batting strike
    rate begins to carry more signal than noise (see
    DATA_PROCESSING_GUIDE.md#why-k). The *sensitivity* module re-runs the whole
    pipeline for k in {60,120,240,480,960} and reports rank stability, so the
    choice is testable rather than asserted.
    """

    prior_strength_balls_bat: float = 240.0
    prior_strength_balls_bowl: float = 240.0
    prior_strength_balls_econ: float = 240.0
    # A batting average stabilises far faster in *dismissals* than in balls, so
    # the average uses its own exposure denominator and prior strength.
    prior_strength_dismissals_bat: float = 12.0
    prior_strength_wickets_bowl: float = 12.0
    min_baseline_group: int = 8  # below this, fall back to the global baseline
    bootstrap_iterations: int = 400
    bootstrap_seed: int = 20260315
    ci_level: float = 0.90
    # Confidence grades are driven by exposure *and* whether the composite is
    # fully supported by the data (coverage). Both must be met.
    grade_a_min_exposure: int = 900
    grade_b_min_exposure: int = 400
    grade_c_min_exposure: int = 150
    grade_a_min_coverage: float = 0.80
    grade_b_min_coverage: float = 0.60
    grade_volatility_penalty: float = 0.35  # >0 => wide bootstrap CI lowers the grade


# --------------------------------------------------------------------------
# Composite weights
# --------------------------------------------------------------------------
@dataclass
class BattingWeights:
    """Weights for the Reliability-Adjusted Batting Index (RABI).

    Renormalised over *available* components only; the coverage of the
    renormalisation is published with every score so a ranking built on 60% of
    the model is never mistaken for one built on 100%.
    """

    performance: float = 0.34
    consistency: float = 0.20
    reliability: float = 0.14
    pressure: float = 0.16
    role_adjusted: float = 0.08
    confidence: float = 0.08


@dataclass
class BowlingWeights:
    performance: float = 0.30
    wicket_taking: float = 0.18
    economy: float = 0.16
    consistency: float = 0.14
    pressure: float = 0.12
    confidence: float = 0.10


@dataclass
class PressureWeights:
    """Part-8 candidate weighting (initial, testable, admin-adjustable)."""

    pressure_contribution: float = 0.30
    consistency: float = 0.20
    role_execution: float = 0.20
    opposition_adjusted: float = 0.10
    match_impact: float = 0.10
    confidence: float = 0.10


# --------------------------------------------------------------------------
# Pressure scenario definitions (transparent + configurable)
# --------------------------------------------------------------------------
@dataclass
class PressureScenarios:
    """Definitions are stated in *match-situation* terms, not merely phase terms.

    A delivery is only tagged as pressure if the scoreboard situation is
    objectively difficult; death overs alone do not qualify.
    """

    chase_min_required_rate: float = 9.0        # RRR required to tag a chase ball
    chase_rate_over_current: float = 2.0        # RRR - CRR gap
    chase_balls_remaining_max: int = 42
    low_wickets_remaining: int = 4
    late_over_from: int = 15                    # depth needed for "final overs"
    final_overs_from: int = 17
    collapse_window_balls: int = 18             # window used to detect a collapse
    collapse_wickets_in_window: int = 2
    defend_low_total_max: int = 150
    high_scoring_chase_min_target: int = 180
    min_tagged_balls_for_score: int = 30        # below this, pressure = provisional


# --------------------------------------------------------------------------
# Role classification
# --------------------------------------------------------------------------
@dataclass
class RoleConfig:
    """Role inference is data-driven; we never *assert* a role we cannot see.

    A player is only labelled "all-rounder" when both batting and bowling
    exposure clear the floors below. Otherwise the strongest observable
    discipline wins and `role_basis` records how it was decided.
    """

    allrounder_min_innings_bat: int = 5
    allrounder_min_balls_bowl: int = 120
    allrounder_balance_ratio: float = 0.35  # each discipline >= 35% of the other's score
    wicketkeeper_name_hints: tuple[str, ...] = ("wk", "keeper", "(wk)")


@dataclass
class Config:
    limits: IngestionLimits = field(default_factory=IngestionLimits)
    mapping: MappingConfig = field(default_factory=MappingConfig)
    eligibility: Eligibility = field(default_factory=Eligibility)
    stats: StatsConfig = field(default_factory=StatsConfig)
    batting_weights: BattingWeights = field(default_factory=BattingWeights)
    bowling_weights: BowlingWeights = field(default_factory=BowlingWeights)
    pressure_weights: PressureWeights = field(default_factory=PressureWeights)
    scenarios: PressureScenarios = field(default_factory=PressureScenarios)
    roles: RoleConfig = field(default_factory=RoleConfig)
    ranking_metric_bat: Literal["rabi", "runs", "average", "strike_rate", "performance"] = "rabi"
    ranking_metric_bowl: Literal["rabi_bowl", "wickets", "economy", "average", "performance"] = "rabi_bowl"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["model_version"] = MODEL_VERSION
        d["metric_semantics_version"] = METRIC_SEMANTICS_VERSION
        return d

    def with_overrides(self, **kw: Any) -> "Config":
        return replace(self, **kw)

    def fingerprint(self) -> str:
        import hashlib

        blob = json.dumps(self.to_dict(), sort_keys=True, default=str).encode()
        return hashlib.sha256(blob).hexdigest()[:16]


DEFAULT_CONFIG = Config()
