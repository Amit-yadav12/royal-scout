"""Loader and match-state derivation for the SupeRR Selector Season 2 data pack.

Provider schema (as supplied):

  ball_by_ball.csv   match_id, innings, overid, over_ball_num, innings_ball_num,
                     batting_team_id, bowling_team_id, striker_id, striker_name,
                     non_striker_id, non_striker_name, bowler_id, bowler_name,
                     batting_type, bowling_type, batting_order, runs, is_four,
                     is_six, is_wicket, dismissal_type_id, dismissal_type,
                     dismissed_player_id, extras_type, extras1_runs,
                     extras_2_runs, pace_or_spin, bowl_speed, stroke,
                     delivery_style, over_or_around, on_or_off, delivery_ist_time
  matches.csv / competitions.csv / teams.csv / playing_eleven.csv /
  competition_team_player_mapping.csv

Provider quirks that must be handled explicitly (all verified against the file):

* ``extras_type`` is the *string* ``"None"`` on ordinary deliveries — not a null.
* ``runs`` holds **bat runs only**; the extra is in ``extras1_runs`` and any
  additional extra in ``extras_2_runs``. A wide therefore has ``runs == 0``.
* No running score is supplied, so the score, wickets and balls faced must be
  derived cumulatively per (match, innings).
* ``over_ball_num`` can exceed 6 (illegal deliveries are numbered), so legal
  balls must be counted from legality, never from the ball number.
* There is no target column: the chase target is innings-1 runs + 1 unless the
  match carries a ``revised_target`` (DLS).
* Six matches contain super overs, stored as innings 3 and 4.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import polars as pl

# extras that mean the delivery was not a legal ball
ILLEGAL_EXTRAS = {"wide", "Overstep", "other", "Penalty"}
# wickets that are *not* credited to the bowler
NON_BOWLER_WICKETS = {
    "runout", "retireout", "obstractingthefield", "obstructingthefield",
    "timedout", "hitballtwice", "handledtheball",
}
KNOWN_DISMISSALS = {
    "bowled", "caught", "caughtbehind", "caughtandbowled", "lbw", "legbeforewicket",
    "stumped", "hitwicket", "hitballtwice", "handledtheball", "timedout", "runout",
    "retireout", "obstructingthefield", "obstractingthefield",
}

BALLS_PER_OVER = 6
DEFAULT_INNINGS_BALLS = 120


@dataclass
class RawPack:
    ball: pl.DataFrame
    matches: pl.DataFrame
    competitions: pl.DataFrame
    teams: pl.DataFrame
    playing_eleven: pl.DataFrame
    mapping: pl.DataFrame

    @property
    def source_files(self) -> list[str]:
        required = ["ball_by_ball.csv", "matches.csv", "competitions.csv",
                    "playing_eleven.csv", "competition_team_player_mapping.csv"]
        return required + (["teams.csv"] if self.teams.height else [])


def _provider_files(root: Path) -> dict[str, Path]:
    """Resolve provider tables by basename or schema, despite staging prefixes/nesting."""
    signatures = {
        "ball": {"match_id", "innings", "overid", "striker_id", "bowler_id", "extras1_runs"},
        "matches": {"match_id", "comp_id", "match_date", "result"},
        "competitions": {"comp_id", "comp_name", "match_format"},
        "teams": {"team_id", "team_name"},
        "playing_eleven": {"match_id", "player_id", "is_played"},
        "mapping": {"player_id", "player_name", "team_id", "comp_id"},
    }
    found: dict[str, Path] = {}
    candidates = (p for p in root.rglob("*") if p.is_file() and p.suffix.lower() == ".csv")
    for path in sorted(candidates):
        try:
            header = set(pl.read_csv(path, n_rows=0).columns)
        except Exception:
            continue
        for key, required in signatures.items():
            if key not in found and required.issubset(header):
                found[key] = path
    missing = [key for key in ("ball", "matches", "competitions", "playing_eleven", "mapping")
               if key not in found]
    if missing:
        raise FileNotFoundError("SupeRR pack is missing required table(s): " + ", ".join(missing))
    return found


def load_raw(root: Path | str) -> RawPack:
    root = Path(root)
    files = _provider_files(root)
    return RawPack(
        ball=pl.read_csv(files["ball"], infer_schema_length=50_000),
        matches=pl.read_csv(files["matches"], infer_schema_length=10_000, try_parse_dates=True),
        competitions=pl.read_csv(files["competitions"]),
        teams=pl.read_csv(files["teams"]) if "teams" in files else pl.DataFrame(
            schema={"team_id": pl.Int64, "team_name": pl.Utf8}),
        playing_eleven=pl.read_csv(files["playing_eleven"]),
        mapping=pl.read_csv(files["mapping"]),
    )


# ---------------------------------------------------------------------------
# Ball-level derivation
# ---------------------------------------------------------------------------
def derive_ball_state(pack: RawPack) -> pl.DataFrame:
    """Add legality, run accounting and pre-ball match state to every delivery."""
    bb = pack.ball.with_columns(
        pl.col("extras_type").fill_null("None").alias("extras_type")
    ).with_columns(
        (pl.col("extras_type") != "None").alias("has_extra"),
        (~pl.col("extras_type").is_in(list(ILLEGAL_EXTRAS))).alias("is_legal"),
        (pl.col("runs") + pl.col("extras1_runs").fill_null(0) + pl.col("extras_2_runs").fill_null(0))
            .alias("total_runs"),
        pl.col("runs").alias("bat_runs"),
        (pl.col("extras1_runs").fill_null(0) + pl.col("extras_2_runs").fill_null(0)).alias("extra_runs"),
        pl.when(~pl.col("is_wicket").fill_null(False)).then(False)
          .when(pl.col("dismissal_type").fill_null("").str.to_lowercase()
                .str.replace_all(r"[^a-z]", "").is_in(list(NON_BOWLER_WICKETS))).then(False)
          .when(pl.col("dismissal_type").fill_null("").str.to_lowercase()
                .str.replace_all(r"[^a-z]", "").is_in(list(KNOWN_DISMISSALS))).then(True)
          .otherwise(None).alias("bowler_wicket"),
        (pl.col("is_wicket") & (pl.col("dismissed_player_id") == pl.col("striker_id")))
            .alias("striker_out"),
        # runs charged to the bowler: bat runs + wides + no-balls (not byes/leg-byes/penalty)
        (pl.col("runs") + pl.when(pl.col("extras_type").is_in(["wide", "Overstep"]))
            .then(pl.col("extras1_runs").fill_null(0) + pl.col("extras_2_runs").fill_null(0))
            .otherwise(0)).alias("bowler_conceded"),
    ).with_columns(
        pl.col("is_legal").cast(pl.Int8).alias("_legal_i"),
        pl.col("is_wicket").cast(pl.Int8).alias("_wkt_i"),
    )

    # running totals *before* this ball, within (match, innings)
    bb = bb.sort(["match_id", "innings", "overid", "over_ball_num"])
    bb = bb.with_columns(
        (pl.col("total_runs").cum_sum().over(["match_id", "innings"]) - pl.col("total_runs"))
            .alias("score_before"),
        (pl.col("_wkt_i").cum_sum().over(["match_id", "innings"]) - pl.col("_wkt_i"))
            .alias("wickets_before"),
        (pl.col("_legal_i").cum_sum().over(["match_id", "innings"]) - pl.col("_legal_i"))
            .alias("legal_balls_before"),
    )

    # innings totals and chase target
    innings_tot = bb.group_by(["match_id", "innings"]).agg(
        pl.col("total_runs").sum().alias("innings_runs"),
        pl.col("_wkt_i").sum().alias("innings_wickets"),
        pl.col("_legal_i").sum().alias("innings_legal_balls"),
    )
    first = innings_tot.filter(pl.col("innings") == 1).select(
        "match_id",
        pl.col("innings_runs").alias("first_innings_runs"),
        pl.col("innings_legal_balls").alias("first_innings_balls"),
    )
    revised = pack.matches.select(
        "match_id",
        pl.col("revised_target").cast(pl.Int64, strict=False).alias("revised_target"),
        pl.col("first_inn_revised_overs").cast(pl.Float64, strict=False).alias("first_rev_overs"),
        pl.col("second_inn_revised_overs").cast(pl.Float64, strict=False).alias("second_rev_overs"),
        pl.col("knock_out").cast(pl.Int8, strict=False).alias("knock_out"),
        pl.col("stage"),
        pl.col("match_date"),
        pl.col("comp_id"),
        pl.col("win_team_id"),
        pl.col("result"),
        pl.col("venue_id"),
        pl.col("home_team_id"),
        pl.col("away_team_id"),
    )
    bb = bb.join(first, on="match_id", how="left").join(revised, on="match_id", how="left")

    # target: explicit revised target wins, otherwise first-innings total + 1
    bb = bb.with_columns(
        pl.when(pl.col("innings") >= 2)
          .then(pl.coalesce([pl.col("revised_target"),
                             (pl.col("first_innings_runs") + 1).cast(pl.Int64)]))
          .otherwise(None).alias("target")
    )

    # innings length in balls (revised overs where supplied)
    bb = bb.with_columns(
        pl.when((pl.col("innings") == 1) & pl.col("first_rev_overs").is_not_null())
          .then((pl.col("first_rev_overs") * BALLS_PER_OVER).round().cast(pl.Int64))
          .when((pl.col("innings") == 2) & pl.col("second_rev_overs").is_not_null())
          .then((pl.col("second_rev_overs") * BALLS_PER_OVER).round().cast(pl.Int64))
          .otherwise(pl.lit(DEFAULT_INNINGS_BALLS))
          .alias("innings_balls")
    ).with_columns(
        (pl.col("innings_balls") - pl.col("legal_balls_before")).alias("balls_remaining"),
    ).with_columns(
        pl.when(pl.col("legal_balls_before") > 0)
          .then(pl.col("score_before") * 6.0 / pl.col("legal_balls_before"))
          .otherwise(0.0).alias("current_rr"),
        pl.when(pl.col("target").is_not_null() & (pl.col("balls_remaining") > 0))
          .then((pl.col("target") - pl.col("score_before")) * 6.0 / pl.col("balls_remaining"))
          .otherwise(None).alias("required_rr"),
        pl.when(pl.col("stage").fill_null("League").is_in(["League", "Others"]))
          .then(0.0).otherwise(1.0).alias("knockout"),
        (pl.col("overid") <= 6).alias("is_powerplay"),
        ((pl.col("overid") > 6) & (pl.col("overid") <= 15)).alias("is_middle"),
        (pl.col("overid") > 15).alias("is_death"),
    )
    return bb


def innings_table(ball: pl.DataFrame) -> pl.DataFrame:
    """One row per (match, innings) with derived totals and outcome context."""
    return ball.group_by(["match_id", "innings"]).agg(
        pl.col("total_runs").sum().alias("runs"),
        pl.col("_wkt_i").sum().alias("wickets"),
        pl.col("_legal_i").sum().alias("legal_balls"),
        pl.col("innings_balls").first().alias("innings_balls"),
        pl.col("batting_team_id").first().alias("batting_team_id"),
        pl.col("bowling_team_id").first().alias("bowling_team_id"),
        pl.col("target").first().alias("target"),
        pl.col("win_team_id").first().alias("win_team_id"),
        pl.col("knock_out").first().alias("knock_out"),
        pl.col("stage").first().alias("stage"),
        pl.col("match_date").first().alias("match_date"),
        pl.col("comp_id").first().alias("comp_id"),
        pl.col("overid").max().alias("last_over"),
        pl.col("is_death").sum().alias("death_balls"),
    ).with_columns(
        ((pl.col("innings") >= 2) & (pl.col("runs") >= pl.col("target"))).alias("chase_completed"),
    )


def competition_labels(pack: RawPack) -> pl.DataFrame:
    """Competition labels with a stable kind (IPL / T20I / other T20)."""
    comps = pack.competitions.select("comp_id", "comp_name", "match_format", "season")
    return comps.with_columns(
        pl.when(pl.col("comp_name").str.starts_with("IPL")).then(pl.lit("IPL"))
          .when((pl.col("match_format") == "T20I")).then(pl.lit("T20I"))
          .otherwise(pl.lit("Other T20")).alias("competition_kind")
    )


def player_names(pack: RawPack) -> dict[int, str]:
    """Authoritative player_id -> name map.

    The mapping file is the roster; ball-by-ball names are used to resolve any id
    that is missing from it. Conflicts are reported by ``validate.check_identity``.
    """
    names: dict[int, str] = {}
    for pid, name in pack.mapping.select("player_id", "player_name").iter_rows():
        if pid is not None and name:
            names.setdefault(int(pid), str(name))
    for col_id, col_name in (("striker_id", "striker_name"), ("bowler_id", "bowler_name"),
                             ("non_striker_id", "non_striker_name")):
        for pid, name in pack.ball.select(col_id, col_name).unique().iter_rows():
            if pid is not None and name and int(pid) not in names:
                names[int(pid)] = str(name)
    return names


# ---------------------------------------------------------------------------
# Identity harmonisation (duplicate-player correction)
# ---------------------------------------------------------------------------
# Player ids merged after the identity audit. Evidence is recorded in
# reports/data_audit.md; each merge requires the two ids to share a name, a team
# and a competition, and never to appear in the same playing XI.
ID_ALIASES: dict[int, int] = {
    39444: 8638,   # "Basil Hameed" (UAE): second profile created in the 2024 Emerging Teams Asia Cup
}


def harmonise_identities(ball: pl.DataFrame) -> tuple[pl.DataFrame, list[dict]]:
    """Collapse duplicate player profiles and return an audit trail of the merges."""
    trail: list[dict] = []
    if not ID_ALIASES:
        return ball, trail
    for dup, keep in ID_ALIASES.items():
        before = ball.filter((pl.col("striker_id") == dup) | (pl.col("bowler_id") == dup) |
                             (pl.col("non_striker_id") == dup) | (pl.col("dismissed_player_id") == dup))
        trail.append({"duplicate_id": dup, "merged_into": keep, "deliveries_touched": before.height,
                      "matches": before["match_id"].n_unique()})
    return ball.with_columns(
        pl.col("striker_id").replace_strict(ID_ALIASES, default=None).fill_null(pl.col("striker_id")).alias("striker_id"),
        pl.col("bowler_id").replace_strict(ID_ALIASES, default=None).fill_null(pl.col("bowler_id")).alias("bowler_id"),
        pl.col("non_striker_id").replace_strict(ID_ALIASES, default=None).fill_null(pl.col("non_striker_id")).alias("non_striker_id"),
        pl.col("dismissed_player_id").replace_strict(ID_ALIASES, default=None).fill_null(pl.col("dismissed_player_id")).alias("dismissed_player_id"),
    ), trail
