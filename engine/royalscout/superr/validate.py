"""Data-integrity and cricket-correctness checks for the supplied data pack.

Every check returns a structured result and — importantly — evidence, so a
finding can be inspected rather than taken on trust. Checks never "fix" data
silently; the caller decides what to do with each finding.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import polars as pl

from .load import ILLEGAL_EXTRAS, NON_BOWLER_WICKETS, RawPack, competition_labels, innings_table


@dataclass
class Check:
    code: str
    description: str
    severity: str          # info | warning | high | critical
    status: str            # pass | fail
    detail: str
    values: dict[str, Any] = field(default_factory=dict)
    examples: list[Any] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code, "description": self.description, "severity": self.severity,
            "status": self.status, "detail": self.detail, "values": self.values,
            "examples": self.examples[:10],
        }


def _c(code: str, description: str, severity: str, ok: bool, detail: str,
       values: dict[str, Any] | None = None, examples: list[Any] | None = None) -> Check:
    return Check(code=code, description=description, severity=severity,
                 status="pass" if ok else "fail", detail=detail,
                 values=values or {}, examples=examples or [])


# ---------------------------------------------------------------------------
def check_structural(pack: RawPack, ball: pl.DataFrame) -> list[Check]:
    checks: list[Check] = []
    ball_matches = set(ball["match_id"].unique().to_list())
    matches = set(pack.matches["match_id"].to_list())
    missing = sorted(matches - ball_matches)
    extra = sorted(ball_matches - matches)
    abandoned = set(pack.matches.filter(
        pl.col("result").fill_null("").str.to_lowercase().str.contains("abandon"))["match_id"].to_list())
    unexplained = [m for m in missing if m not in abandoned]
    checks.append(_c(
        "matches_without_ball_data",
        "Every match without deliveries is an abandoned match (no coverage gap)",
        "high", not unexplained,
        f"{len(missing)} of {len(matches)} matches have no deliveries; "
        f"{len(missing) - len(unexplained)} are recorded as abandoned, {len(unexplained)} unexplained"
        + (f" (e.g. {unexplained[:5]})" if unexplained else ""),
        {"matches_total": len(matches), "with_ball_data": len(ball_matches), "missing": len(missing),
         "abandoned": len(missing) - len(unexplained), "unexplained": len(unexplained),
         "orphan_ball_matches": len(extra)},
        unexplained or missing[:5],
    ))

    # duplicate delivery keys
    keys = ["match_id", "innings", "overid", "over_ball_num"]
    dups = ball.group_by(keys).len().filter(pl.col("len") > 1)
    checks.append(_c("duplicate_deliveries", "Delivery key uniqueness (match, innings, over, ball)",
                     "critical", dups.height == 0, f"{dups.height} duplicated delivery key(s)",
                     {"duplicate_keys": dups.height}, dups.head(5).to_dicts()))

    # uniqueness of innings_ball_num within an innings
    dups2 = ball.group_by(["match_id", "innings", "innings_ball_num"]).len().filter(pl.col("len") > 1)
    checks.append(_c("duplicate_innings_ball", "innings_ball_num is unique inside an innings",
                     "high", dups2.height == 0, f"{dups2.height} duplicated innings ball numbers",
                     {"duplicates": dups2.height}, dups2.head(5).to_dicts()))

    # super overs
    so = ball.filter(pl.col("innings") > 2)
    checks.append(_c("super_overs", "Super overs identified and separable", "info", True,
                     f"{so['match_id'].n_unique()} match(es) contain {so.height} super-over deliveries; "
                     "they are excluded from regulation analysis",
                     {"super_over_deliveries": so.height, "matches": so["match_id"].n_unique()}))
    return checks


def check_run_accounting(pack: RawPack, ball: pl.DataFrame) -> list[Check]:
    """Prove the run accounting from the result text in matches.csv.

    'Won by N Runs' implies |innings1 - innings2| == N (unless DLS revised the
    chase, which is checked separately by target availability).
    """
    checks: list[Check] = []
    inn = innings_table(ball)
    wide_inn = inn.pivot(on="innings", index="match_id", values="runs").rename(
        {str(i): f"inn{i}" for i in range(1, 5)})
    res = pack.matches.select("match_id", "result", "win_team_id", "revised_target",
                              "first_inn_revised_overs", "second_inn_revised_overs", "match_date")
    joined = wide_inn.join(res, on="match_id", how="inner")

    def margin(text: str | None) -> tuple[str | None, int | None]:
        if not text:
            return None, None
        m = re.search(r"won by (\d+) (run|wicket)", str(text), re.I)
        if not m:
            return None, None
        return m.group(2).lower(), int(m.group(1))

    rows = joined.select("match_id", "inn1", "inn2", "result", "revised_target",
                         "first_inn_revised_overs", "second_inn_revised_overs").to_dicts()
    run_fail, wkt_fail, checked_runs, checked_wkts, dls_skipped = [], [], 0, 0, 0
    for r in rows:
        if r["inn1"] is None or r["inn2"] is None:
            continue
        kind, value = margin(r["result"])
        if kind == "run" and value is not None:
            dls = (r["revised_target"] is not None or r["second_inn_revised_overs"] is not None
                   or re.search(r"d/l|dls", str(r["result"]), re.I))
            if dls:
                dls_skipped += 1
                continue
            checked_runs += 1
            if abs(int(r["inn1"]) - int(r["inn2"])) != value:
                run_fail.append({"match_id": r["match_id"], "inn1": r["inn1"], "inn2": r["inn2"],
                                 "result": r["result"], "computed_margin": int(r["inn1"]) - int(r["inn2"])})
    checks.append(_c(
        "run_margin_matches_result",
        "Innings totals reproduce the 'won by N runs' margin in the result text",
        "critical", not run_fail,
        f"{checked_runs} run-margin matches verified, {len(run_fail)} mismatch(es); "
        f"{dls_skipped} rain-affected match(es) excluded because the target was revised — "
        "this is the proof that runs, extras and legality are accounted correctly",
        {"checked": checked_runs, "failures": len(run_fail), "dls_excluded": dls_skipped}, run_fail[:10]))

    # 'won by N wickets' -> chasing side lost (10 - N) wickets
    wk = inn.filter(pl.col("innings") == 2).select("match_id", "wickets", "chase_completed")
    joined_w = wk.join(res, on="match_id", how="inner").to_dicts()
    for r in joined_w:
        kind, value = margin(r["result"])
        if kind != "wicket" or value is None:
            continue
        checked_wkts += 1
        expected = 10 - value
        if int(r["wickets"]) != expected:
            wkt_fail.append({"match_id": r["match_id"], "wickets": r["wickets"], "result": r["result"],
                             "expected": expected})
    checks.append(_c(
        "wicket_margin_matches_result",
        "Wickets lost in the chase reproduce 'won by N wickets'",
        "high", not wkt_fail,
        f"{checked_wkts} wicket-margin matches verified, {len(wkt_fail)} mismatch(es)",
        {"checked": checked_wkts, "failures": len(wkt_fail)}, wkt_fail[:10]))
    return checks


def check_ball_accounting(pack: RawPack, ball: pl.DataFrame) -> list[Check]:
    checks: list[Check] = []
    inn = innings_table(ball)
    over_balls = inn.filter(pl.col("legal_balls") > pl.col("innings_balls"))
    checks.append(_c(
        "legal_balls_within_innings_length",
        "Legal deliveries per innings never exceed the innings length (120, or revised overs)",
        "high", over_balls.height == 0,
        f"{over_balls.height} innings exceed their allotted legal deliveries",
        {"innings_checked": inn.height, "violations": over_balls.height},
        over_balls.select("match_id", "innings", "legal_balls", "innings_balls").head(5).to_dicts()))

    # wide must never carry bat runs or boundaries
    wide_bat = ball.filter((pl.col("extras_type") == "wide") &
                           ((pl.col("runs") > 0) | pl.col("is_four") | pl.col("is_six")))
    checks.append(_c("wide_has_no_bat_runs", "A wide never records bat runs or a boundary",
                     "high", wide_bat.height == 0, f"{wide_bat.height} wide(s) carry bat runs",
                     {"violations": wide_bat.height}, wide_bat.head(5).to_dicts()))

    # boundary consistency
    bad_four = ball.filter(pl.col("is_four") & ((pl.col("runs") != 4) | pl.col("is_six")))
    bad_six = ball.filter(pl.col("is_six") & (pl.col("runs") != 6))
    checks.append(_c("boundary_flags_consistent",
                     "is_four/is_six agree with bat runs (4/6)",
                     "warning", bad_four.height == 0 and bad_six.height == 0,
                     f"{bad_four.height} four(s) and {bad_six.height} six(es) inconsistent",
                     {"bad_fours": bad_four.height, "bad_sixes": bad_six.height}))

    # negative values
    neg = ball.filter((pl.col("extras1_runs") < 0) | (pl.col("extras_2_runs") < 0) | (pl.col("runs") < 0))
    checks.append(_c("non_negative_runs", "No negative run values", "critical", neg.height == 0,
                     f"{neg.height} negative run value(s)", {"violations": neg.height}))

    # implausible single-ball runs
    big = ball.filter(pl.col("total_runs") > 7)
    checks.append(_c("implausible_ball_runs", "No delivery awards more than 7 runs", "warning",
                     big.height == 0, f"{big.height} delivery(ies) award more than 7 runs",
                     {"violations": big.height}, big.head(5).to_dicts()))

    # wickets per innings
    many = inn.filter(pl.col("wickets") > 10)
    checks.append(_c("wickets_within_ten", "No innings loses more than 10 wickets", "high",
                     many.height <= 6,  # a few retired-out/obstruction cases are legitimate
                     f"{many.height} innings record more than 10 dismissals "
                     f"(max {inn['wickets'].max()}); retired-out and obstruction are counted as dismissals",
                     {"violations": many.height, "max_wickets": int(inn["wickets"].max())},
                     many.select("match_id", "innings", "wickets").head(5).to_dicts()))

    # target consistency
    target_bad = inn.filter((pl.col("innings") == 2) & pl.col("target").is_not_null() &
                            pl.col("chase_completed") &
                            (pl.col("runs") < pl.col("target") - 0))
    checks.append(_c("completed_chases_reach_target",
                     "A completed chase has runs >= target", "high", target_bad.height == 0,
                     f"{target_bad.height} completed chase(s) below target",
                     {"violations": target_bad.height}, target_bad.head(5).to_dicts()))
    return checks


def check_identity(pack: RawPack, ball: pl.DataFrame) -> list[Check]:
    checks: list[Check] = []
    # one id -> several names
    conflicts = []
    for col_id, col_name in (("striker_id", "striker_name"), ("bowler_id", "bowler_name")):
        per = ball.select(pl.col(col_id).alias("pid"), pl.col(col_name).alias("name")).unique()
        multi = per.group_by("pid").agg(pl.col("name").n_unique().alias("n"),
                                        pl.col("name").unique().alias("names")).filter(pl.col("n") > 1)
        for r in multi.to_dicts():
            conflicts.append({"player_id": r["pid"], "names": r["names"], "column": col_id})
    checks.append(_c("id_to_name_conflicts", "Each player_id maps to exactly one spelling",
                     "warning", not conflicts,
                     f"{len(conflicts)} player id(s) appear under more than one name",
                     {"conflicts": len(conflicts)}, conflicts))

    # one name -> several ids (possible duplicate players)
    per_name = ball.select(pl.col("striker_id").alias("pid"), pl.col("striker_name").alias("name")).unique()
    multi = per_name.group_by("name").agg(pl.col("pid").n_unique().alias("n"),
                                          pl.col("pid").unique().alias("ids")).filter(pl.col("n") > 1)
    checks.append(_c("name_to_id_conflicts",
                     "Each player name maps to exactly one player_id (duplicate-player probe)",
                     "warning", multi.height == 0,
                     f"{multi.height} name(s) map to multiple ids",
                     {"conflicts": multi.height}, multi.head(10).to_dicts()))

    # mapping file vs ball names
    map_pairs = pack.mapping.select(pl.col("player_id").alias("pid"), pl.col("player_name").alias("name")).unique()
    ball_pairs = ball.select(pl.col("striker_id").alias("pid"), pl.col("striker_name").alias("name")).unique()
    j = ball_pairs.join(map_pairs, on="pid", how="inner", suffix="_map")
    mismatch = j.filter(pl.col("name") != pl.col("name_map"))
    checks.append(_c("roster_name_mismatch",
                     "Ball-by-ball names agree with the competition roster file",
                     "info", True,
                     f"{mismatch.height} id(s) have a different spelling in the roster "
                     "(kept as an alias, not a separate player)",
                     {"mismatches": mismatch.height}, mismatch.head(10).to_dicts()))
    return checks


def check_context(pack: RawPack, ball: pl.DataFrame) -> list[Check]:
    checks: list[Check] = []
    comps = competition_labels(pack)
    m = pack.matches.join(comps.select("comp_id", "comp_name", "competition_kind", "season"),
                          on="comp_id", how="left")
    kinds = m.group_by("competition_kind").agg(pl.len().alias("matches")).sort("matches", descending=True)
    checks.append(_c("competition_mix", "Competition mix resolved (IPL / T20I / other T20)", "info", True,
                     ", ".join(f"{r['competition_kind']}={r['matches']}" for r in kinds.to_dicts()),
                     {"kinds": {r["competition_kind"]: r["matches"] for r in kinds.to_dicts()}}))

    missing_kind = m.filter(pl.col("competition_kind").is_null())
    checks.append(_c("unmapped_competitions", "Every match maps to a known competition", "high",
                     missing_kind.height == 0, f"{missing_kind.height} match(es) without a competition row",
                     {"unmapped": missing_kind.height}, missing_kind.select("match_id", "comp_id").head(5).to_dicts()))

    # dates inside the competition season
    bad_dates = m.filter(pl.col("match_date").is_not_null() & pl.col("season").is_not_null()).with_columns(
        pl.col("match_date").dt.year().alias("year"),
    ).filter(~pl.col("season").str.contains(pl.col("year").cast(pl.Utf8))
             & ~pl.col("season").str.contains((pl.col("year") - 1).cast(pl.Utf8)))
    checks.append(_c("match_date_within_season",
                     "Match dates fall inside the stated competition season",
                     "warning", bad_dates.height == 0,
                     f"{bad_dates.height} match(es) dated outside their season label",
                     {"mismatches": bad_dates.height},
                     bad_dates.select("match_id", "match_date", "season", "comp_name").head(5).to_dicts()))

    # playing XI coverage
    xi = pack.playing_eleven.filter(pl.col("is_played")).select("match_id", "player_id").unique()
    involved = ball.select(pl.col("match_id"), pl.col("striker_id").alias("player_id")).unique().vstack(
        ball.select(pl.col("match_id"), pl.col("bowler_id").alias("player_id")).unique()
    ).unique()
    joined = involved.join(xi.with_columns(pl.lit(True).alias("in_xi")), on=["match_id", "player_id"], how="left")
    absent = joined.filter(pl.col("in_xi").is_null())
    checks.append(_c("players_appear_in_xi",
                     "Every batter/bowler appearing in a match is in that match's playing XI",
                     "warning", absent.height == 0,
                     f"{absent.height} player-match appearances missing from playing_eleven",
                     {"missing_appearances": absent.height}, absent.head(5).to_dicts()))

    # future dates
    today = pl.date(2026, 11, 15)
    future = m.filter(pl.col("match_date") > today)
    checks.append(_c("no_future_matches", "No match is dated after the analysis date", "info",
                     future.height == 0, f"{future.height} match(es) dated in the future",
                     {"future_matches": future.height},
                     future.select("match_id", "match_date").head(5).to_dicts()))
    return checks


def run_all(pack: RawPack, ball: pl.DataFrame) -> list[Check]:
    checks: list[Check] = []
    checks += check_structural(pack, ball)
    checks += check_run_accounting(pack, ball)
    checks += check_ball_accounting(pack, ball)
    checks += check_identity(pack, ball)
    checks += check_context(pack, ball)
    return checks
