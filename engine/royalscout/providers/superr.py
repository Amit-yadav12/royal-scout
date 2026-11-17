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


def detect(sources: list[Path], search_roots: list[Path] | None = None) -> Path | None:
    """Find the provider ball table by schema, not its staged filename.

    Worker staging names are content-addressed, and archive contents may be
    nested. The ingestion layer has already safely extracted accepted entries;
    search only those roots and explicit source parents, never an arbitrary
    filesystem ancestor.
    """
    roots = list(search_roots or [])
    roots.extend(src if src.is_dir() else src.parent for src in sources)
    for root in roots:
        root = Path(root)
        if root.is_file():
            candidates = [root]
        elif root.exists():
            try:
                candidates = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() == ".csv")[:10_000]
            except OSError:
                continue
        else:
            continue
        headers: dict[Path, set[str]] = {}
        for candidate in candidates:
            try:
                headers[candidate] = set(pl.read_csv(candidate, n_rows=0).columns)
            except Exception:
                continue
        ball = next((p for p, cols in headers.items() if set(SIGNATURE).issubset(cols)), None)
        if ball is not None:
            # When the five-file pack is present under a shared upload/extraction
            # root, pass that root so the loader can resolve prefixed/nested paths.
            required = {
                "matches": {"match_id", "comp_id", "match_date", "result"},
                "competitions": {"comp_id", "comp_name", "match_format"},
                "playing_eleven": {"match_id", "player_id", "is_played"},
                "mapping": {"player_id", "player_name", "team_id", "comp_id"},
            }
            if all(any(sig.issubset(cols) for cols in headers.values()) for sig in required.values()):
                return root.resolve()
            return ball.parent.resolve()
    return None


def _ball_events(ball: pl.DataFrame, names: dict[int, str]) -> pl.DataFrame:
    """Map the derived provider frame onto the engine's ball-event schema."""
    ev = ball.with_columns(
        # the engine uses one wicket flag for bowling credit...
        pl.col("bowler_wicket").alias("is_wicket"),
        # ...and a separate one for the batter's dismissal
        pl.col("striker_out").alias("batter_dismissed"),
        pl.when(pl.col("is_wicket") & pl.col("dismissed_player_id").is_not_null())
          .then(pl.col("dismissed_player_id").replace_strict(names, default=None))
          .otherwise(None).alias("dismissed_batter"),
        # balls faced: wides and penalties are not balls faced, no-balls are
        (~pl.col("extras_type").is_in(["wide", "Penalty"])).alias("batter_ball"),
        pl.col("is_legal").cast(pl.Boolean).alias("legal_delivery"),
        # extras charged to the bowler only (byes/leg-byes are not conceded)
        pl.when(pl.col("extras_type").is_in(["wide", "Overstep"]))
          .then(pl.col("extra_runs")).otherwise(0).alias("extras"),
        pl.col("bowler_conceded").alias("bowler_runs"),
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
        resolved_team = team_name.get(str(own)) if own is not None else None
        rec["team"] = resolved_team if resolved_team is not None else (str(own) if own is not None else None)
        rec["team_identity_status"] = "resolved" if resolved_team is not None else (
            "unresolved_team_id" if own is not None else "unresolved")
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

    # The primary ratings are regulation T20 only. Super overs remain in the
    # cached, audited state table but never contaminate innings/player rates.
    events = _ball_events(ball, names).filter(pl.col("innings_number") <= 2)
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

    team_rows = {str(r["team_id"]): r["team_name"] for r in pack.teams.to_dicts()
                 if r.get("team_id") is not None and r.get("team_name")}
    if "team_name" in pack.mapping.columns:
        for r in pack.mapping.select("team_id", "team_name").unique().to_dicts():
            if r.get("team_id") is not None and r.get("team_name"):
                team_rows.setdefault(str(r["team_id"]), r["team_name"])
    enrich_teams = pl.DataFrame([{"team_id": k, "team_name": v} for k, v in team_rows.items()]) \
        if team_rows else pack.teams
    bat = _enrich(bat, pack.matches, enrich_teams, pack.playing_eleven, names, "bat")
    bowl = _enrich(bowl, pack.matches, enrich_teams, pack.playing_eleven, names, "bowl")
    for rec in bat + bowl:
        rec.pop("_player_id", None)

    matches = [{
        "match_id": str(r["match_id"]), "match_date": str(r["match_date"]),
        "competition": r.get("comp_name"), "season": r.get("season"),
        "venue": str(r.get("venue_id")), "target": r.get("revised_target"),
        "stage": r.get("stage"), "result": r.get("result"),
    } for r in pack.matches.join(labels, on="comp_id", how="left").to_dicts()]

    name_team = [(r["player_name"], team_rows.get(str(r.get("team_id"))))
                 for r in pack.mapping.to_dicts()
                 if r.get("player_name") and team_rows.get(str(r.get("team_id")))]
    cd = CanonicalData(batting=bat, bowling=bowl, ball_events=events, matches=matches,
                       registry=build_player_registry(name_team))
    cd.capabilities = {
        "batting_records": bool(bat), "bowling_records": bool(bowl), "ball_by_ball": True,
        "innings_granularity_batting": True, "innings_granularity_bowling": True,
        "aggregate_only_batting": False, "phase_data": True, "actual_match_pressure": True,
        "targets_available": True, "venue_data": True, "opposition_data": True,
        "provider_adapter": True,
    }
    used_team_ids = {str(x) for x in ball["batting_team_id"].drop_nulls().unique().to_list()} | {
        str(x) for x in ball["bowling_team_id"].drop_nulls().unique().to_list()}
    unresolved_team_ids = sorted(team_id for team_id in used_team_ids if team_id not in team_rows)
    unknown_dismissal_rows = int(ball.filter(pl.col("is_wicket") & pl.col("bowler_wicket").is_null()).height)
    cd.capabilities["team_identity_unresolved"] = bool(unresolved_team_ids)
    cd.capabilities["unknown_bowler_wicket_attribution"] = bool(unknown_dismissal_rows)
    cd.derivations.append({"kind": "provider_adapter", "provider": PROVIDER_NAME,
                           "folder": str(folder), "identity_merges": merges,
                           "deliveries": int(ball.height), "batting_records": len(bat),
                           "bowling_records": len(bowl), "unknown_dismissal_rows": unknown_dismissal_rows,
                           "team_identity": {"resolved_team_count": len(used_team_ids) - len(unresolved_team_ids),
                                             "unresolved_team_ids": unresolved_team_ids,
                                             "basis": "teams.csv or explicit mapping team_name; unresolved ids are not guessed"}})
    return cd
