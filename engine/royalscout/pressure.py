"""Pressure performance intelligence.

Core principle: **an over being late does not make it pressure**. A delivery is
tagged as a pressure situation only when the *scoreboard situation* is difficult,
using the transparent, configurable definitions in ``PressureScenarios``.

Everything here degrades honestly:

* ball-by-ball data  -> ``basis = "ball_by_ball"`` (actual match situations)
* innings-split data -> ``basis = "innings_index_proxy"`` (chasing = 2nd innings)
* aggregates only    -> pressure is *unavailable*, never invented

The optional win-expectancy estimate below is a documented heuristic used only
for leverage weighting and reporting. It is explicitly NOT a validated model and
is never used to upgrade a player's score.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl

from .config import Config
from .stats import composite, percentile_rank, shrink


# ---------------------------------------------------------------------------
# Situation tagging
# ---------------------------------------------------------------------------
def _heuristic_win_expectancy(required_runs: float, balls_left: float, wickets_left: float,
                              wicket_value: float = 0.055) -> float | None:
    """Heuristic chase win-expectancy in [0,1].

    Combines required run rate pressure with wicket resources. Coefficients are
    hand-set and unvalidated; treat the output as an ordering device only.
    """
    if balls_left <= 0:
        return 0.0 if required_runs > 0 else 1.0
    rrr = required_runs * 6 / balls_left
    resource = max(0.0, min(1.0, wickets_left / 10.0))
    z = 1.35 - 0.30 * (rrr - 8.0) + 2.1 * (resource - 0.5)
    return 1.0 / (1.0 + math.exp(-z))


def tag_ball_events(events: pl.DataFrame, cfg: Config) -> pl.DataFrame:
    """Add situation columns and pressure tags to each delivery."""
    sc = cfg.scenarios
    df = events
    if "ball_number" not in df.columns:
        df = df.with_columns(pl.lit(None).cast(pl.Int32).alias("ball_number"))
    df = df.sort(["match_id", "innings_number", "over_number", "ball_number"],
                 nulls_last=True)
    df = df.with_columns([
        (pl.col("batter_runs") + pl.col("extras")).alias("runs_total"),
        (pl.col("is_wicket").cast(pl.Int32)).alias("wicket_i"),
    ])
    # delivery index within the innings (1-based, includes illegal deliveries)
    df = df.with_columns(pl.int_range(1, pl.len() + 1).over(["match_id", "innings_number"]).alias("ball_seq"))
    df = df.with_columns([
        pl.col("runs_total").cum_sum().over(["match_id", "innings_number"]).alias("score"),
        pl.col("wicket_i").cum_sum().over(["match_id", "innings_number"]).alias("wkts_fallen"),
        pl.col("wicket_i").rolling_sum(window_size=sc.collapse_window_balls, min_samples=1)
        .over(["match_id", "innings_number"]).fill_null(0).alias("recent_wkts"),
    ])
    total_per_innings = df.group_by(["match_id", "innings_number"]).agg(
        pl.col("ball_seq").max().alias("innings_balls"))
    df = df.join(total_per_innings, on=["match_id", "innings_number"], how="left")
    df = df.with_columns([
        (pl.col("innings_balls") - pl.col("ball_seq")).alias("balls_left"),
        (10 - pl.col("wkts_fallen")).alias("wkts_left"),
    ])
    # first-innings total per match => defending scenarios
    first_inn = (df.filter(pl.col("innings_number") == 1)
                 .group_by("match_id").agg(pl.col("score").max().alias("first_innings_total")))
    df = df.join(first_inn, on="match_id", how="left")
    df = df.with_columns([
        pl.when(pl.col("target").is_not_null())
        .then(pl.col("target"))
        .otherwise(pl.col("first_innings_total") + 1).alias("effective_target")
    ])
    df = df.with_columns([
        (pl.col("effective_target") - pl.col("score")).alias("runs_required"),
    ])
    df = df.with_columns([
        pl.when((pl.col("innings_number") == 2) & (pl.col("balls_left") > 0))
        .then(pl.col("runs_required") * 6.0 / pl.col("balls_left")).otherwise(None).alias("rrr"),
        pl.when(pl.col("ball_seq") > 0)
        .then(pl.col("score") * 6.0 / pl.col("ball_seq")).otherwise(None).alias("crr"),
    ])

    # ---- scenario flags ----
    # The chasing side bats second; the side *bowling* second is the side defending.
    # "Defending" tags therefore live on second-innings deliveries, never on the
    # innings where the total is still being built.
    chasing = pl.col("innings_number") == 2
    defending = pl.col("innings_number") == 2
    flags = {
        "difficult_chase": chasing & (pl.col("rrr") >= sc.chase_min_required_rate) &
                           (pl.col("balls_left") <= sc.chase_balls_remaining_max),
        "chase_rate_gap": chasing & (pl.col("rrr") - pl.col("crr") >= sc.chase_rate_over_current),
        "low_wickets_remaining": pl.col("wkts_left") <= sc.low_wickets_remaining,
        "early_collapse": (pl.col("over_number") <= 8) & (pl.col("wkts_fallen") >= 3),
        "recovery_after_wickets": pl.col("recent_wkts") >= sc.collapse_wickets_in_window,
        "difficult_final_overs": (pl.col("over_number") >= sc.final_overs_from) &
                                 (pl.col("wkts_left") <= sc.low_wickets_remaining + 1),
        "defending_low_total": defending & (pl.col("first_innings_total") <= sc.defend_low_total_max),
        "high_scoring_chase": chasing & (pl.col("effective_target") >= sc.high_scoring_chase_min_target),
        "defending_competitive_total": defending & (pl.col("first_innings_total") > sc.defend_low_total_max),
    }
    df = df.with_columns([expr.fill_null(False).alias(name) for name, expr in flags.items()])
    df = df.with_columns(
        pl.any_horizontal([pl.col(n) for n in flags]).alias("is_pressure"))
    df = df.with_columns([
        pl.concat_list([pl.when(pl.col(n)).then(pl.lit(n)).otherwise(None) for n in flags])
        .list.drop_nulls().alias("pressure_tags")
    ])

    # leverage (informational only)
    le = []
    for r in df.select(["runs_required", "balls_left", "wkts_left", "innings_number"]).iter_rows():
        if r[3] == 2 and r[0] is not None and r[1] is not None:
            wp = _heuristic_win_expectancy(float(r[0]), float(r[1]), float(r[2] or 10))
            le.append(round(abs(0.5 - wp) * 2, 4))
        else:
            le.append(None)
    df = df.with_columns(pl.Series("leverage_heuristic", le, dtype=pl.Float64))
    return df


SCENARIO_DEFINITIONS: list[dict[str, str]] = [
    {"id": "difficult_chase", "label": "Difficult run chase",
     "definition": "2nd innings, required run rate >= {chase_min_required_rate} with <= "
                   "{chase_balls_remaining_max} balls remaining"},
    {"id": "chase_rate_gap", "label": "Required rate outpacing current rate",
     "definition": "2nd innings, (required rate - current rate) >= {chase_rate_over_current}"},
    {"id": "low_wickets_remaining", "label": "Wicket resources exhausted",
     "definition": "{low_wickets_remaining} or fewer wickets in hand"},
    {"id": "early_collapse", "label": "Early innings collapse",
     "definition": "over <= 8 with 3+ wickets already lost"},
    {"id": "recovery_after_wickets", "label": "Recovery after a cluster of wickets",
     "definition": "{collapse_wickets_in_window}+ wickets in the preceding "
                   "{collapse_window_balls} deliveries"},
    {"id": "difficult_final_overs", "label": "Difficult final overs",
     "definition": "over >= {final_overs_from} with 5 or fewer wickets in hand"},
    {"id": "defending_low_total", "label": "Defending a low total",
     "definition": "2nd-innings bowling side defending a first-innings total <= {defend_low_total_max}"},
    {"id": "high_scoring_chase", "label": "High-scoring chase",
     "definition": "chasing a target of >= {high_scoring_chase_min_target}"},
    {"id": "defending_competitive_total", "label": "Defending a competitive total",
     "definition": "2nd-innings bowling side defending a first-innings total above {defend_low_total_max}"},
]


def scenario_table(cfg: Config) -> list[dict[str, Any]]:
    fmt = cfg.scenarios.__dict__
    out = []
    for s in SCENARIO_DEFINITIONS:
        out.append({"id": s["id"], "label": s["label"], "definition": s["definition"].format(**fmt)})
    return out


# ---------------------------------------------------------------------------
# Phase aggregates (available whenever ball-by-ball exists)
# ---------------------------------------------------------------------------
def phase_aggregates(events: pl.DataFrame) -> dict[str, Any]:
    bat = events.group_by(["batter", "phase"]).agg([
        pl.col("batter_runs").sum().alias("runs"),
        pl.len().alias("balls"),
        (pl.col("batter_runs") == 4).sum().alias("fours"),
        (pl.col("batter_runs") == 6).sum().alias("sixes"),
        ((pl.col("batter_runs") == 0) & (~pl.col("is_wicket"))).sum().alias("dots"),
    ])
    bowl = events.group_by(["bowler", "phase"]).agg([
        pl.col("batter_runs").sum().alias("runs"),
        pl.col("extras").sum().alias("extras"),
        pl.len().alias("balls"),
        pl.col("is_wicket").sum().alias("wickets"),
        ((pl.col("batter_runs") == 0) & (pl.col("extras") == 0)).sum().alias("dots"),
    ])
    batting: dict[str, dict[str, Any]] = {}
    for r in bat.to_dicts():
        d = batting.setdefault(r["batter"], {})
        d[r["phase"]] = {
            "runs": r["runs"], "balls": r["balls"],
            "strike_rate": round(100 * r["runs"] / r["balls"], 2) if r["balls"] else None,
            "fours": r["fours"], "sixes": r["sixes"],
            "boundary_pct": round(100 * (4 * r["fours"] + 6 * r["sixes"]) / r["runs"], 2) if r["runs"] else None,
            "dot_pct": round(100 * r["dots"] / r["balls"], 2) if r["balls"] else None,
        }
    bowling: dict[str, dict[str, Any]] = {}
    for r in bowl.to_dicts():
        d = bowling.setdefault(r["bowler"], {})
        runs = r["runs"] + r["extras"]
        d[r["phase"]] = {
            "runs_conceded": runs, "balls": r["balls"], "wickets": r["wickets"],
            "economy": round(runs * 6 / r["balls"], 2) if r["balls"] else None,
            "dot_pct": round(100 * r["dots"] / r["balls"], 2) if r["balls"] else None,
            "bowling_strike_rate": round(r["balls"] / r["wickets"], 2) if r["wickets"] else None,
        }
    for pid, d in batting.items():
        total = sum(v["balls"] for v in d.values()) or 1
        d["phase_ball_shares"] = {k: round(v["balls"] / total, 3) for k, v in d.items() if k != "phase_ball_shares"}
    for pid, d in bowling.items():
        total = sum(v["balls"] for v in d.values()) or 1
        d["phase_ball_shares"] = {k: round(v["balls"] / total, 3) for k, v in d.items() if k != "phase_ball_shares"}
    return {"batting": batting, "bowling": bowling, "available": True}


# ---------------------------------------------------------------------------
# Pressure metrics
# ---------------------------------------------------------------------------
def _score_from_delta(deltas: dict[str, float | None]) -> dict[str, float | None]:
    return percentile_rank({k: v for k, v in deltas.items()}, higher_is_better=True)


def pressure_batting_metrics(tagged: pl.DataFrame, cfg: Config) -> dict[str, dict[str, Any]]:
    sc = cfg.scenarios
    pres = tagged.filter(pl.col("is_pressure"))
    non = tagged.filter(~pl.col("is_pressure"))
    agg_p = pres.group_by("batter").agg([
        pl.col("batter_runs").sum().alias("runs"), pl.len().alias("balls"),
        (pl.col("batter_runs") == 4).sum().alias("fours"),
        (pl.col("batter_runs") == 6).sum().alias("sixes"),
        pl.col("is_wicket").sum().alias("dismissals"),
    ])
    agg_n = non.group_by("batter").agg([
        pl.col("batter_runs").sum().alias("runs"), pl.len().alias("balls"),
        pl.col("is_wicket").sum().alias("dismissals"),
    ])
    dismissals_total = (tagged.filter(pl.col("is_wicket")).group_by("batter")
                        .agg(pl.len().alias("n")))
    all_names = set(agg_p["batter"].to_list()) | set(agg_n["batter"].to_list())
    np_map = {r["batter"]: r for r in agg_n.to_dicts()}
    pmap = {r["batter"]: r for r in agg_p.to_dicts()}
    dmap = {r["batter"]: r["n"] for r in dismissals_total.to_dicts()}

    deltas: dict[str, float | None] = {}
    details: dict[str, dict[str, Any]] = {}
    for name in all_names:
        p = pmap.get(name, {"runs": 0, "balls": 0})
        n = np_map.get(name, {"runs": 0, "balls": 0})
        ps = 100 * p["runs"] / p["balls"] if p["balls"] else None
        ns = 100 * n["runs"] / n["balls"] if n["balls"] else None
        delta = (ps - ns) if (ps is not None and ns is not None) else None
        deltas[name] = delta
        details[name] = {
            "pressure_runs": p.get("runs"), "pressure_balls": p.get("balls"),
            "pressure_strike_rate": None if ps is None else round(ps, 2),
            "non_pressure_runs": n.get("runs"), "non_pressure_balls": n.get("balls"),
            "non_pressure_strike_rate": None if ns is None else round(ns, 2),
            "strike_rate_delta": None if delta is None else round(delta, 2),
            "dismissals_total": dmap.get(name, 0),
        }
    # shrink the delta toward zero on limited pressure exposure, then percentile
    shrunk = {k: shrink(v, (details[k]["pressure_balls"] or 0), 40.0, 0.0)
              for k, v in deltas.items()}
    scores = _score_from_delta(shrunk)
    out: dict[str, dict[str, Any]] = {}
    for name in all_names:
        pb = details[name]["pressure_balls"] or 0
        provisional = pb < sc.min_tagged_balls_for_score
        out[name] = {
            "score": None if scores.get(name) is None else round(scores[name], 2),
            "basis": "ball_by_ball",
            "detail": {
                **details[name],
                "tagged_deliveries_total": int(tagged.height),
                "tagged_deliveries_pressure": int(pres.height),
                "status": "provisional" if provisional else "supported",
                "explanation": ("Fewer than "
                                f"{sc.min_tagged_balls_for_score} pressure deliveries faced — score is "
                                "provisional and its weight in the composite is reduced by the coverage "
                                "penalty." if provisional else
                                "Pressure score compares the player's strike rate in tagged pressure "
                                "situations with their own non-pressure strike rate (shrunk toward 0 on "
                                "small samples, then percentile-ranked)."),
                "scenario_counts": _scenario_counts(pres, "batter", name),
            },
        }
    return out


def _scenario_counts(df: pl.DataFrame, who_col: str, who: str) -> dict[str, int]:
    sub = df.filter(pl.col(who_col) == who)
    if sub.height == 0:
        return {}
    counts: dict[str, int] = {}
    for tags in sub["pressure_tags"].to_list():
        for t in (tags or []):
            counts[t] = counts.get(t, 0) + 1
    return counts


def pressure_bowling_metrics(tagged: pl.DataFrame, cfg: Config) -> dict[str, dict[str, Any]]:
    sc = cfg.scenarios
    pres = tagged.filter(pl.col("is_pressure"))
    non = tagged.filter(~pl.col("is_pressure"))

    def agg(df: pl.DataFrame) -> pl.DataFrame:
        return df.group_by("bowler").agg([
            (pl.col("batter_runs") + pl.col("extras")).sum().alias("runs"),
            pl.len().alias("balls"),
            pl.col("is_wicket").sum().alias("wickets"),
            ((pl.col("batter_runs") == 0) & (pl.col("extras") == 0)).sum().alias("dots"),
        ])

    ap, an = agg(pres), agg(non)
    pmap = {r["bowler"]: r for r in ap.to_dicts()}
    nmap = {r["bowler"]: r for r in an.to_dicts()}
    names = set(pmap) | set(nmap)
    deltas: dict[str, float | None] = {}
    details: dict[str, dict[str, Any]] = {}
    for name in names:
        p, n = pmap.get(name), nmap.get(name)
        pe = p["runs"] * 6 / p["balls"] if p and p["balls"] else None
        ne = n["runs"] * 6 / n["balls"] if n and n["balls"] else None
        # positive delta = better under pressure (lower economy)
        delta = (ne - pe) if (pe is not None and ne is not None) else None
        wr_p = (p["wickets"] / p["balls"] * 6) if p and p["balls"] else None
        wr_n = (n["wickets"] / n["balls"] * 6) if n and n["balls"] else None
        deltas[name] = delta
        details[name] = {
            "pressure_balls": p["balls"] if p else 0, "pressure_runs_conceded": p["runs"] if p else 0,
            "pressure_wickets": p["wickets"] if p else 0,
            "pressure_economy": None if pe is None else round(pe, 2),
            "pressure_dot_pct": round(100 * p["dots"] / p["balls"], 2) if p and p["balls"] else None,
            "non_pressure_economy": None if ne is None else round(ne, 2),
            "economy_delta": None if delta is None else round(delta, 2),
            "wicket_rate_pressure": None if wr_p is None else round(wr_p, 3),
            "wicket_rate_non_pressure": None if wr_n is None else round(wr_n, 3),
            "status": "provisional" if (p["balls"] if p else 0) < sc.min_tagged_balls_for_score else "supported",
        }
    shrunk = {k: shrink(v, (details[k]["pressure_balls"] or 0), 40.0, 0.0) for k, v in deltas.items()}
    scores = _score_from_delta(shrunk)
    out = {}
    for name in names:
        out[name] = {
            "score": None if scores.get(name) is None else round(scores[name], 2),
            "basis": "ball_by_ball",
            "detail": {**details[name],
                       "explanation": "Compares economy in tagged pressure situations with the "
                                      "bowler's own non-pressure economy (positive = better under "
                                      "pressure), shrunk toward zero on small samples and "
                                      "percentile-ranked.",
                       "scenario_counts": _scenario_counts(pres, "bowler", name)},
        }
    return out


# ---------------------------------------------------------------------------
# Proxy fallback from innings-split records
# ---------------------------------------------------------------------------
def pressure_proxy_from_records(batting_records: list[dict[str, Any]],
                                bowling_records: list[dict[str, Any]],
                                cfg: Config) -> dict[str, dict[str, Any]]:
    """Second-innings (chasing) proxy — clearly labelled as a proxy.

    This is *not* match-pressure performance: it cannot see the scoreboard. It
    only says whether a player's output differs when batting/bowling second.
    """
    def split(records: list[dict[str, Any]], value_key: str, balls_key: str | None):
        """Bucket innings 1 vs innings 2+ (a 'batting second' proxy)."""
        by: dict[str, dict[int, list[int]]] = {}
        for r in records:
            p = r.get("player")
            inn = r.get("innings_number")
            if not p or inn is None:
                continue
            try:
                bucket = 1 if int(inn) == 1 else 2
            except (TypeError, ValueError):
                continue
            d = by.setdefault(p, {1: [0, 0], 2: [0, 0]})
            d[bucket][0] += int(r.get(value_key) or 0)
            d[bucket][1] += int(r.get(balls_key) or 0) if balls_key else 1
        return by

    out: dict[str, dict[str, Any]] = {}
    bat_split = split(batting_records, "runs", "balls_faced")
    for p, d in bat_split.items():
        b1, b2 = d[1], d[2]
        if not (b1[1] and b2[1]):
            continue
        sr1 = 100 * b1[0] / b1[1]
        sr2 = 100 * b2[0] / b2[1]
        out[p] = {
            "score": None, "basis": "innings_index_proxy",
            "detail": {
                "status": "proxy_only",
                "first_innings_strike_rate": round(sr1, 2), "second_innings_strike_rate": round(sr2, 2),
                "delta": round(sr2 - sr1, 2),
                "explanation": "No ball-by-ball data: only a first-vs-second-innings proxy is available. "
                               "Scoreboard pressure cannot be measured.",
            },
        }
    bowl_split = split(bowling_records, "runs_conceded", "legal_balls")
    for p, d in bowl_split.items():
        b1, b2 = d[1], d[2]
        entry = out.setdefault(p, {"score": None, "basis": "innings_index_proxy", "detail": {}})
        if b1[1] and b2[1]:
            e1 = b1[0] * 6 / b1[1]
            e2 = b2[0] * 6 / b2[1]
            entry["detail"].update({
                "status": "proxy_only",
                "first_innings_economy": round(e1, 2), "second_innings_economy": round(e2, 2),
                "delta": round(e1 - e2, 2),
                "explanation": "No ball-by-ball data: only a first-vs-second-innings proxy is available.",
            })
    return out


# ---------------------------------------------------------------------------
# Pressure Performance Index (Part 8)
# ---------------------------------------------------------------------------
def pressure_performance_index(driver: dict[str, dict[str, Any]], cfg: Config,
                               discipline: str) -> dict[str, dict[str, Any]]:
    """Coverage-aware PPI.

    Components: pressure-specific contribution (30%), consistency (20%),
    role-specific execution (20%), opposition-adjusted performance (10%),
    match impact (10%), statistical confidence (10%). Missing components are
    dropped and the coverage is reported — never imputed.
    """
    w = {"pressure_contribution": cfg.pressure_weights.pressure_contribution,
         "consistency": cfg.pressure_weights.consistency,
         "role_execution": cfg.pressure_weights.role_execution,
         "opposition_adjusted": cfg.pressure_weights.opposition_adjusted,
         "match_impact": cfg.pressure_weights.match_impact,
         "confidence": cfg.pressure_weights.confidence}
    out: dict[str, dict[str, Any]] = {}
    for pid, m in driver.items():
        components = {
            "pressure_contribution": m.get("pressure_score"),
            "consistency": m.get("consistency"),
            "role_execution": m.get("role_adjusted_score"),
            "opposition_adjusted": (m.get("opposition_adjusted") or {}).get("score"),
            "match_impact": (m.get("match_impact") or {}).get("score"),
            "confidence": m.get("confidence_score"),
        }
        score, coverage, applied = composite(components, w)
        out[pid] = {
            "ppi": None if score is None else round(score, 2),
            "coverage": round(coverage, 3),
            "discipline": discipline,
            "components": {k: (None if v is None else round(v, 2)) for k, v in components.items()},
            "missing_components": [k for k, v in components.items() if v is None],
            "applied_weights": {k: round(v, 4) for k, v in applied.items()},
            "interpretation": _ppi_interpretation(score, coverage, components),
        }
    return out


def _ppi_interpretation(score: float | None, coverage: float, components: dict[str, Any]) -> str:
    if score is None:
        return "Pressure performance cannot be assessed from the supplied data."
    missing = [k for k, v in components.items() if v is None]
    parts = [f"PPI {score:.1f}/100 built on {coverage:.0%} of the nominal weight."]
    if missing:
        parts.append("Unavailable: " + ", ".join(missing) + ".")
    if components.get("pressure_contribution") is None:
        parts.append("No ball-by-ball data, so the pressure-specific component is absent and the index "
                     "must not be read as match-pressure performance.")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Match impact (ball-by-ball only)
# ---------------------------------------------------------------------------
def match_impact(events: pl.DataFrame) -> dict[str, dict[str, Any]]:
    """Share of the team's runs / wickets produced in each match, averaged."""
    bat = events.group_by(["match_id", "innings_number", "batter"]).agg(
        pl.col("batter_runs").sum().alias("runs"))
    team_tot = bat.group_by(["match_id", "innings_number"]).agg(pl.col("runs").sum().alias("team_runs"))
    bat = bat.join(team_tot, on=["match_id", "innings_number"], how="left")
    bat = bat.with_columns((pl.col("runs") / pl.col("team_runs").clip(1)).alias("share"))
    agg = bat.group_by("batter").agg(pl.col("share").mean().alias("mean_share"))
    vals = {r["batter"]: r["mean_share"] * 100 for r in agg.to_dicts()}
    pct = percentile_rank(vals, higher_is_better=True)
    out = {}
    for p, v in vals.items():
        out[p] = {"score": round(pct[p], 2) if pct.get(p) is not None else None,
                  "mean_team_run_share_pct": round(v, 2), "basis": "ball_by_ball"}
    bowl = events.group_by(["match_id", "innings_number", "bowler"]).agg(
        pl.col("is_wicket").sum().alias("wkts"))
    tot = bowl.group_by(["match_id", "innings_number"]).agg(pl.col("wkts").sum().alias("innings_wkts"))
    bowl = bowl.join(tot, on=["match_id", "innings_number"], how="left")
    bowl = bowl.with_columns((pl.col("wkts") / pl.col("innings_wkts").clip(1)).alias("share"))
    agg_b = bowl.group_by("bowler").agg(pl.col("share").mean().alias("mean_share"))
    vals_b = {r["bowler"]: r["mean_share"] * 100 for r in agg_b.to_dicts()}
    pct_b = percentile_rank(vals_b, higher_is_better=True)
    for p, v in vals_b.items():
        entry = out.setdefault(p, {"score": None, "basis": "ball_by_ball"})
        if entry.get("score") is None:
            entry["score"] = round(pct_b[p], 2) if pct_b.get(p) is not None else None
        entry["mean_innings_wicket_share_pct"] = round(v, 2)
    return out
