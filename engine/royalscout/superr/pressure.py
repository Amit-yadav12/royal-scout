"""Pressure definition, situation tagging and per-player pressure metrics.

Design notes (these thresholds are the ones defended in the methodology report):

A delivery is a **pressure ball** when the batting side's position is materially
at stake. Five situational triggers are used; a ball is pressure if it satisfies
any one of them, and the trigger that fires is recorded so every pressure ball in
the dataset can be audited and counted by reason.

  T1  CHASE_RATE      innings >= 2, over 5 onwards, required run rate >= 11.00
  T2  CHASE_LATE      innings >= 2, over 15 onwards, required run rate >= 9.50
  T3  COLLAPSE        6 or more wickets down (<= 4 in hand) with >= 12 balls left
  T4  DEATH_FRAGILE   over 17 onwards with 4 or more wickets already down
  T5  TIGHT_FINISH    innings >= 2, <= 18 balls left, 1-30 runs needed,
                      required rate >= 8.00 (the game is live and must be finished)

Calibration (full 2022-2026 pack, regulation innings): these thresholds tag 27.0%
of deliveries (19.0% of first innings, 35.9% of chases). Pressure balls are
demonstrably harder cricket: 8.97 runs/over and 7.67 wickets per 100 balls
versus 8.31 and 4.57 outside the tagged states.

Chase triggers (T1, T2, T5) are only applied where the chase target is
trustworthy; on rain-shortened chases without a revised target the target cannot
be reconstructed, so those innings fall back to the non-chase triggers and are
counted separately.

**Stakes** are a separate multiplier, not a trigger: knockout matches
(stage other than League) and the last three overs raise intensity.

An *intensity* in [0, 1] accompanies the flag and is what the score weights by:
intensity = 1 + 0.5 * (stakes excess) applied to the strongest applicable
situation severity. It is used for weighting, never for classification, so the
pressure/no-pressure split stays auditable.
"""
from __future__ import annotations

from dataclasses import dataclass

import polars as pl

BALLS_PER_OVER = 6

# --- trigger thresholds -----------------------------------------------------
CHASE_RRR_HIGH = 11.0
CHASE_RRR_HIGH_FROM_OVER = 5
CHASE_RRR_LATE = 9.5
CHASE_LATE_FROM_OVER = 15
COLLAPSE_WICKETS = 6
COLLAPSE_MIN_BALLS_LEFT = 12
DEATH_OVER = 17
DEATH_MIN_WICKETS = 4
TIGHT_BALLS_LEFT = 18
TIGHT_RUNS_NEEDED = 30
TIGHT_MIN_RRR = 8.0

@dataclass(frozen=True)
class Thresholds:
    """Every knob of the pressure definition, so alternative definitions are explicit."""
    name: str = "v1_primary"
    chase_rrr_high: float = 11.0
    chase_rrr_high_from_over: int = 5
    chase_rrr_late: float = 9.5
    chase_late_from_over: int = 15
    chase_gap: float | None = None          # required rate minus current rate (unused in v1)
    live_chase_max_rrr: float = 18.0        # an impossible ask is not pressure, it is a formality
    chase_gap_from_over: int = 4
    collapse_wickets: int = 6
    collapse_min_balls_left: int = 12
    death_over: int = 17
    death_min_wickets: int = 4
    tight_balls_left: int = 18
    tight_runs_needed: int = 30
    tight_min_rrr: float = 8.0
    stakes_trigger: bool = False            # knockout closure counts as pressure in its own right
    stakes_from_over: int = 16


DEFAULT = Thresholds()
WIDE = Thresholds(name="v2_wide", chase_rrr_high=9.5, chase_rrr_late=8.5, death_over=17,
                  tight_runs_needed=36, tight_min_rrr=7.5, stakes_trigger=True)
GAP = Thresholds(name="v3_rate_gap", chase_rrr_high=99.0, chase_rrr_late=99.0, chase_gap=2.5)


# --- metric constants -------------------------------------------------------
MIN_PRESSURE_BALLS_BAT = 120
MIN_PRESSURE_BALLS_BOWL = 120
MIN_PRESSURE_MATCHES = 6
MIN_PRESSURE_INNINGS = 8        # innings with >= 6 pressure balls
SHRINK_K_BALLS = 120.0          # empirical-Bayes prior strength in balls
CLOSE_CONTEST_RRR = 11.0        # used only for the sensitivity universe


def tag_pressure(ball: pl.DataFrame, th: Thresholds = DEFAULT) -> pl.DataFrame:
    """Add chase validity, pressure flag, reason and intensity to every delivery."""
    dls_unknown = (
        pl.col("result").fill_null("").str.contains("(?i)D/L|DLS")
        & pl.col("revised_target").is_null()
        & pl.col("second_rev_overs").is_null()
    )
    b = ball.with_columns(dls_unknown.alias("chase_target_unknown")).with_columns(
        ((pl.col("innings") == 1) | (~pl.col("chase_target_unknown") & pl.col("target").is_not_null()))
            .alias("chase_context_valid")
    )

    # a chase that cannot mathematically be completed inside the available balls
    # is no longer a contest, so it is not pressure whatever the required rate says
    chase_live = ((pl.col("target") - pl.col("score_before")) <= th.live_chase_max_rrr * pl.col("balls_remaining"))
    if "knockout" not in b.columns:
        b = b.with_columns(
            pl.when(pl.col("stage").fill_null("League").is_in(["League", "Others"]))
              .then(0.0).otherwise(1.0).alias("knockout"))
    b = b.with_columns(
        (
            (pl.col("innings") >= 2) & pl.col("chase_context_valid") & chase_live
            & (pl.col("overid") >= th.chase_rrr_high_from_over)
            & (pl.col("required_rr") >= th.chase_rrr_high)
        ).alias("t1"),
        (
            (pl.col("innings") >= 2) & pl.col("chase_context_valid") & chase_live
            & (pl.col("overid") >= th.chase_late_from_over)
            & (pl.col("required_rr") >= th.chase_rrr_late)
        ).alias("t2"),
        (
            (pl.col("wickets_before") >= th.collapse_wickets)
            & (pl.col("balls_remaining") >= th.collapse_min_balls_left)
        ).alias("t3"),
        (
            (pl.col("overid") >= th.death_over) & (pl.col("wickets_before") >= th.death_min_wickets)
        ).alias("t4"),
        (
            (pl.col("innings") >= 2) & pl.col("chase_context_valid") & chase_live
            & (pl.col("balls_remaining") <= th.tight_balls_left)
            & ((pl.col("target") - pl.col("score_before")) <= th.tight_runs_needed)
            & ((pl.col("target") - pl.col("score_before")) > 0)
            & (pl.col("required_rr") >= th.tight_min_rrr)
        ).alias("t5"),
        (
            (pl.col("innings") >= 2) & pl.col("chase_context_valid") & (th.chase_gap is not None)
            & (pl.col("overid") >= th.chase_gap_from_over)
            & ((pl.col("required_rr") - pl.col("current_rr")) >= (th.chase_gap or 0.0))
        ).alias("t6"),
        (
            (th.stakes_trigger is True) & (pl.col("knockout") > 0) & (pl.col("overid") >= th.stakes_from_over)
        ).alias("t7"),
    )

    b = b.with_columns(
        (pl.col("t1") | pl.col("t2") | pl.col("t3") | pl.col("t4") | pl.col("t5")
         | pl.col("t6") | pl.col("t7")).alias("is_pressure"),
    ).with_columns(
        pl.when(pl.col("t1")).then(pl.lit("CHASE_RATE"))
          .when(pl.col("t2")).then(pl.lit("CHASE_LATE"))
          .when(pl.col("t6")).then(pl.lit("RATE_GAP"))
          .when(pl.col("t5")).then(pl.lit("TIGHT_FINISH"))
          .when(pl.col("t3")).then(pl.lit("COLLAPSE"))
          .when(pl.col("t4")).then(pl.lit("DEATH_FRAGILE"))
          .when(pl.col("t7")).then(pl.lit("STAKES"))
          .otherwise(pl.lit("NONE")).alias("pressure_reason"),
    )
    b = b.with_columns(pl.col("knockout").cast(pl.Float64))

    # severity in [0,1]: how extreme the situation is; averaged over fired triggers
    sev_rate = ((pl.col("required_rr").fill_null(0) - CHASE_RRR_HIGH) / 6.0).clip(0, 1)
    sev_gap = ((pl.col("required_rr").fill_null(0) - CHASE_RRR_LATE) / 5.0).clip(0, 1)
    sev_collapse = ((pl.col("wickets_before") - COLLAPSE_WICKETS + 1) / 4.0).clip(0, 1)
    sev_death = (((pl.col("overid") - DEATH_OVER + 1) / 5.0) * ((pl.col("wickets_before") - 3) / 5.0)).clip(0, 1)
    sev_tight = (1.0 - ((pl.col("target") - pl.col("score_before")).fill_null(TIGHT_RUNS_NEEDED)
                        / (TIGHT_RUNS_NEEDED + 1.0))).clip(0, 1)
    b = b.with_columns(
        pl.when(pl.col("t1")).then(sev_rate)
          .when(pl.col("t2")).then(sev_gap)
          .when(pl.col("t5")).then(sev_tight)
          .when(pl.col("t3")).then(sev_collapse)
          .when(pl.col("t4")).then(sev_death)
          .otherwise(0.0).alias("situation_severity"),
    ).with_columns(
        pl.when(pl.col("is_pressure"))
          .then((0.6 + 0.4 * pl.col("situation_severity")) * (1.0 + 0.35 * pl.col("knockout")))
          .otherwise(0.0).alias("pressure_intensity")
    )
    return b


# ---------------------------------------------------------------------------
# Per-player aggregates
# ---------------------------------------------------------------------------
def batting_balls(b: pl.DataFrame) -> pl.DataFrame:
    """Balls faced by the striker (wides and penalties are not balls faced)."""
    return b.filter(~pl.col("extras_type").is_in(["wide", "Penalty"]))


def bowling_balls(b: pl.DataFrame) -> pl.DataFrame:
    """Deliveries charged to the bowler.

    The *denominator* of every bowling rate is legal balls only, but the
    *numerator* must include the runs from wides and no-balls — they are the
    bowler's runs even though they are not balls. Reference filtering here is
    therefore not legal-only; the legal count is summed separately.
    """
    return b


def _agg_batting(df: pl.DataFrame, prefix: str) -> pl.DataFrame:
    return df.group_by("striker_id").agg(
        pl.len().alias(f"{prefix}_balls"),
        pl.col("bat_runs").sum().alias(f"{prefix}_runs"),
        pl.col("striker_out").sum().alias(f"{prefix}_outs"),
        pl.col("is_four").sum().alias(f"{prefix}_fours"),
        pl.col("is_six").sum().alias(f"{prefix}_sixes"),
        pl.col("match_id").n_unique().alias(f"{prefix}_matches"),
    )


def _agg_bowling(df: pl.DataFrame, prefix: str) -> pl.DataFrame:
    return df.group_by("bowler_id").agg(
        pl.col("_legal_i").sum().alias(f"{prefix}_balls"),
        pl.col("bat_runs").sum().alias(f"{prefix}_bat_runs"),
        pl.col("bowler_conceded").sum().alias(f"{prefix}_conceded"),
        pl.col("bowler_wicket").sum().alias(f"{prefix}_wickets"),
        pl.col("match_id").n_unique().alias(f"{prefix}_matches"),
    )


def player_tables(b: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Batting and bowling tables split by pressure / non-pressure exposure."""
    bat_balls = batting_balls(b)
    bowl_balls = bowling_balls(b)

    bat = (
        _agg_batting(bat_balls.filter(pl.col("is_pressure")), "p")
        .join(_agg_batting(bat_balls.filter(~pl.col("is_pressure")), "b"), on="striker_id", how="full")
        .rename({"striker_id": "player_id"})
    )
    bowl = (
        _agg_bowling(bowl_balls.filter(pl.col("is_pressure")), "p")
        .join(_agg_bowling(bowl_balls.filter(~pl.col("is_pressure")), "b"), on="bowler_id", how="full")
        .rename({"bowler_id": "player_id"})
    )
    return bat, bowl


def innings_consistency(b: pl.DataFrame, bat: pl.DataFrame, bowl: pl.DataFrame,
                        min_balls_in_innings: int = 6) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Share of pressure innings in which a player beat their own baseline.

    Baseline per player is the non-pressure rate. Only innings with at least
    ``min_balls_in_innings`` pressure balls count, so a two-ball cameo cannot
    flatter or damage a consistency score.
    """
    base_sr = bat.select("player_id", (pl.col("b_runs") * 100 / pl.col("b_balls")).alias("base_sr"))
    pin = batting_balls(b).filter(pl.col("is_pressure")).group_by(["striker_id", "match_id", "innings"]).agg(
        pl.len().alias("balls"), pl.col("bat_runs").sum().alias("runs")).filter(
        pl.col("balls") >= min_balls_in_innings).join(
        base_sr, left_on="striker_id", right_on="player_id", how="left").with_columns(
        (pl.col("runs") * 100 / pl.col("balls")).alias("sr")
    ).with_columns((pl.col("sr") > pl.col("base_sr")).alias("beat"))
    bat_cons = pin.group_by("striker_id").agg(
        pl.len().alias("p_innings"), pl.col("beat").sum().alias("p_innings_won"),
        pl.col("match_id").n_unique().alias("p_matches"),
    ).rename({"striker_id": "player_id"})

    base_econ = bowl.select("player_id", (pl.col("b_conceded") * 6 / pl.col("b_balls")).alias("base_econ"))
    pinb = bowling_balls(b).filter(pl.col("is_pressure")).group_by(["bowler_id", "match_id", "innings"]).agg(
        pl.col("_legal_i").sum().alias("balls"), pl.col("bowler_conceded").sum().alias("conceded"),
        pl.col("bowler_wicket").sum().alias("wkts")).filter(
        pl.col("balls") >= min_balls_in_innings).join(
        base_econ, left_on="bowler_id", right_on="player_id", how="left").with_columns(
        (pl.col("conceded") * 6 / pl.col("balls")).alias("econ")
    ).with_columns((pl.col("econ") < pl.col("base_econ")).alias("beat"))
    bowl_cons = pinb.group_by("bowler_id").agg(
        pl.len().alias("p_innings"), pl.col("beat").sum().alias("p_innings_won"),
        pl.col("match_id").n_unique().alias("p_matches"),
    ).rename({"bowler_id": "player_id"})
    return bat_cons, bowl_cons


def pressure_reason_mix(b: pl.DataFrame, id_col: str) -> pl.DataFrame:
    """Counts of pressure balls by trigger reason per player (audit trail)."""
    return b.filter(pl.col("is_pressure")).group_by([pl.col(id_col).alias("player_id"),
                                                     "pressure_reason"]).agg(
        pl.len().alias("balls")).pivot(on="pressure_reason", index="player_id", values="balls")
