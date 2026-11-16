"""SupeRR Selector Season 2 data-pack adapter.

Why this exists
---------------
The generic ingestion path relies on column-alias inference. The SupeRR pack uses
provider-specific names (``striker_id``, ``overid``, ``extras1_runs`` ...), a
literal ``"None"`` string for "no extra", bat-runs-only ``runs`` and no running
score. Run through the generic path it produced **zero** batting and bowling
records, which is exactly the failure this adapter removes.

The adapter reads the pack, derives match state with the audited rules in
``royalscout.superr.load`` and then hands *ball events in the engine's own
schema* to ``canonical.reduce_ball_events_to_innings`` — so the engine's own
maths still computes every batting and bowling statistic.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import polars as pl

from ..canonical import (GRANULARITY_INNINGS, CanonicalData, build_player_registry,
                         reduce_ball_events_to_innings)
from ..superr.load import (competition_labels, derive_ball_state, harmonise_identities, load_raw,
                           player_names)

SIGNATURE = ("match_id", "innings", "overid", "over_ball_num", "striker_id", "bowler_id")
PROVIDER_NAME = "superr-selector-s2"


def detect(sources: list[Path]) -> Path | None:
    """Return the folder holding a SupeRR-style ball_by_ball.csv, if there is one."""
    for src in sources:
        folder = src if src.is_dir() else src.parent
        candidate = folder / "ball_by_ball.csv"
        if not candidate.exists():
            continue
        try:
            with candidate.open(encoding="utf-8") as fh:
                header = fh.readline().strip().split(",")
        except OSError:
            continue
        if all(col in header for col in SIGNATURE):
            return folder
    return None


def _ball_events(ball: pl.DataFrame, names: dict[int, str]) -> pl.DataFrame:
    """Map the derived provider frame onto the engine's ball-event schema."""
    ev = ball.with_columns(
        # the engine uses one wicket flag for bowling credit...
        pl.col("bowler_wicket").alias("is_wicket"),
        # ...and a separate one for the batter's dismissal
        pl.col("striker_out").alias("batter_dismissed"),
        # balls faced: wides and penalties are not balls faced, no-balls are
        (~pl.col("extras_type").is_in(["wide", "Penalty"])).alias("batter_ball"),
        pl.col("is_legal").cast(pl.Boolean).alias("legal_delivery"),
        # extras charged to the bowler only (byes/leg-byes are not conceded)
        pl.when(pl.col("extras_type").is_in(["wide", "Overstep", "other"]))
          .then(pl.col("extra_runs")).otherwise(0).alias("extras"),
        (pl.col("bat_runs") + pl.col("extras1_runs").fill_null(0) + pl.col("extras_2_runs").fill_null(0)).alias("total"),
        pl.col("striker_id").replace_strict(names, default="Unknown").alias("batter"),
        pl.col("bowler_id").replace_strict(names, default="Unknown").alias("bowler"),
        pl.col("batting_team_id").cast(pl.Utf8).alias("team_batting"),
        pl.col("bowling_team_id").cast(pl.Utf8).alias("team_bowling"),
        pl.col("innings").alias("innings_number"),
        pl.col("overid").alias("over_number"),
        pl.col("over_ball_num").alias("ball_number"),
        pl.col("bat_runs").alias("batter_runs"),
        pl.col("is_four").alias("is_four"),
        pl.col("is_six").alias("is_six"),
        pl.col("dismissal_type").alias("wicket_type"),
        pl.col("comp_name").alias("competition"),
        pl.col("season"),
    ).with_columns(
        pl.when(pl.col("over_number") <= 6).then(pl.lit("powerplay"))
          .when(pl.col("over_number") <= 15).then(pl.lit("middle"))
          .otherwise(pl.lit("death")).alias("phase"),
        (pl.col("match_id").cast(pl.Utf8) + ":" + pl.col("innings").cast(pl.Utf8)).alias("match_innings_key"),
    )
    return ev


def _enrich(records: list[dict[str, Any]], matches: pl.DataFrame, teams: pl.DataFrame,
            xi: pl.DataFrame, names: dict[int, str], role: str) -> list[dict[str, Any]]:
    match_info = {str(r["match_id"]): r for r in matches.to_dicts()}
    team_name = {str(r["team_id"]): r["team_name"] for r in teams.to_dicts()}
    order = {(str(r["match_id"]), str(r["player_id"])): r["batting_order"] for r in xi.to_dicts()
             if r.get("is_played")}
    for rec in records:
        info = match_info.get(str(rec["match_id"]), {})
        rec["match_date"] = str(info.get("match_date")) if info.get("match_date") else None
        rec["venue"] = str(info.get("venue_id")) if info.get("venue_id") is not None else None
        rec["competition"] = rec.get("competition")
        own = rec.get("team")
        other = str(info.get("away_team_id")) if str(info.get("home_team_id")) == str(own) else str(info.get("home_team_id"))
        rec["opposition"] = team_name.get(other)
        rec["team"] = team_name.get(str(own), own)
        pos = order.get((str(rec["match_id"]), None)) if False else None
        player_id = rec.get("_player_id")
        if player_id is not None:
            rec["batting_position"] = order.get((str(rec["match_id"]), str(player_id)))
        rec["granularity"] = GRANULARITY_INNINGS
        rec.setdefault("flags", []).append("provider_adapter:superr")
    return records


def build(folder: Path, cfg=None) -> CanonicalData:
    pack = load_raw(folder)
    names = player_names(pack)
    ball = derive_ball_state(pack)
    ball, merges = harmonise_identities(ball)
    labels = competition_labels(pack).select("comp_id", "comp_name", "season", "competition_kind")
    ball = ball.join(labels, on="comp_id", how="left")

    events = _ball_events(ball, names)
    bat, bowl = reduce_ball_events_to_innings(events)

    # competition + player ids on the derived records
    comp_of = {f"{r['match_id']}:{r['innings']}": (r["comp_name"], r["season"])
               for r in ball.select("match_id", "innings", "comp_name", "season").unique().to_dicts()}
    pid_of = {}
    for e in events.select("match_id", "innings_number", "batter", "bowler").unique().to_dicts():
        pid_of[(str(e["match_id"]), e["innings_number"], e["batter"])] = None
    name_to_id = {v: k for k, v in names.items()}
    for rec in bat:
        comp, season = comp_of.get(f"{rec['match_id']}:{rec['innings_number']}", (None, None))
        rec["competition"], rec["season"] = comp, season
        rec["_player_id"] = name_to_id.get(rec["player"])
    for rec in bowl:
        comp, season = comp_of.get(f"{rec['match_id']}:{rec['innings_number']}", (None, None))
        rec["competition"], rec["season"] = comp, season
        rec["_player_id"] = name_to_id.get(rec["player"])

    bat = _enrich(bat, pack.matches, pack.teams, pack.playing_eleven, names, "bat")
    bowl = _enrich(bowl, pack.matches, pack.teams, pack.playing_eleven, names, "bowl")
    for rec in bat + bowl:
        rec.pop("_player_id", None)

    matches = [{
        "match_id": str(r["match_id"]), "match_date": str(r["match_date"]),
        "competition": r.get("comp_name"), "season": r.get("season"),
        "venue": str(r.get("venue_id")), "target": r.get("revised_target"),
        "stage": r.get("stage"), "result": r.get("result"),
    } for r in pack.matches.join(labels, on="comp_id", how="left").to_dicts()]

    name_team = [(r["player_name"], r["team_name"]) for r in pack.mapping.to_dicts()]
    cd = CanonicalData(batting=bat, bowling=bowl, ball_events=events, matches=matches,
                       registry=build_player_registry(name_team))
    cd.capabilities = {
        "batting_records": bool(bat), "bowling_records": bool(bowl), "ball_by_ball": True,
        "innings_granularity_batting": True, "innings_granularity_bowling": True,
        "aggregate_only_batting": False, "phase_data": True, "actual_match_pressure": True,
        "targets_available": True, "venue_data": True, "opposition_data": True,
        "provider_adapter": True,
    }
    cd.derivations.append({"kind": "provider_adapter", "provider": PROVIDER_NAME,
                           "folder": str(folder), "identity_merges": merges,
                           "deliveries": int(ball.height), "batting_records": len(bat),
                           "bowling_records": len(bowl)})
    return cd
