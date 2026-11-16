"""Pressure metric construction, scoring, and bootstrap reliability.

Two layers:

1. **Panels** — per (player, match) aggregates of pressure and non-pressure
   production. Everything downstream is a sum over panels, which makes the whole
   scoring pipeline exactly reproducible and lets a match-level bootstrap be run
   without touching the 200k-row ball table again.

2. **Scoring** — a Pressure Reliability Index (PRI, 0-100) per player built from
   three transparent blocks:

   * LEVEL       how good the player actually is in pressure states
   * LIFT        how much better/worse that is than the same player's own
                 non-pressure baseline (shrunk towards zero by sample size)
   * CONSISTENCY share of pressure innings in which the player beat their own
                 baseline (Laplace-smoothed)

   Weights are explicit, documented and stress-tested against alternatives.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable

import numpy as np
import polars as pl

from .load import competition_labels
from .pressure import (batting_balls, bowling_balls, innings_consistency, MIN_PRESSURE_BALLS_BAT,
                       MIN_PRESSURE_BALLS_BOWL, MIN_PRESSURE_INNINGS, MIN_PRESSURE_MATCHES,
                       SHRINK_K_BALLS)


@dataclass(frozen=True)
class Config:
    label: str = "primary"
    min_pressure_balls_bat: int = MIN_PRESSURE_BALLS_BAT
    min_pressure_balls_bowl: int = MIN_PRESSURE_BALLS_BOWL
    min_pressure_matches: int = MIN_PRESSURE_MATCHES
    min_pressure_innings: int = MIN_PRESSURE_INNINGS
    min_balls_in_innings: int = 6
    min_baseline_balls: int = 60      # a "usual performance level" must exist to compare against
    shrink_k: float = SHRINK_K_BALLS
    shrink_k_level: float = 60.0
    w_level: float = 0.55
    w_lift: float = 0.30
    w_cons: float = 0.15
    bat_level_sr_share: float = 0.70      # level: strike rate vs dismissal avoidance
    bowl_level_econ_share: float = 0.60   # level: economy vs wicket-taking
    lift_sr_share: float = 0.60           # lift: scoring vs survival
    baseline: str = "non_pressure"        # or "overall"
    competitions: tuple[str, ...] = ("IPL", "T20I")   # the two competitions named in the brief
    knockouts_only: bool = False
    use_shrinkage: bool = True

    def with_(self, **kw) -> "Config":
        return replace(self, **kw)


# ---------------------------------------------------------------------------
# Panels
# ---------------------------------------------------------------------------
def _bat_panel(b: pl.DataFrame) -> pl.DataFrame:
    bb = batting_balls(b)
    cols = {"balls": pl.len(), "runs": pl.col("bat_runs").sum(), "outs": pl.col("striker_out").sum(),
            "exp_runs": pl.col("exp_bat_runs").sum(), "exp_outs": pl.col("exp_striker_out").sum()}
    p = bb.filter(pl.col("is_pressure")).group_by(["striker_id", "match_id"]).agg(
        **{f"p_{k}": v for k, v in cols.items()})
    n = bb.filter(~pl.col("is_pressure")).group_by(["striker_id", "match_id"]).agg(
        **{f"b_{k}": v for k, v in cols.items()})
    panel = p.join(n, on=["striker_id", "match_id"], how="full", coalesce=True)
    return panel.rename({"striker_id": "player_id"})


def _bowl_panel(b: pl.DataFrame) -> pl.DataFrame:
    bo = bowling_balls(b)
    cols = {"balls": pl.col("_legal_i").sum(), "conceded": pl.col("bowler_conceded").sum(),
            "wkts": pl.col("bowler_wicket").sum(),
            "exp_conceded": pl.col("exp_conceded").sum(), "exp_wkts": pl.col("exp_bowler_wicket").sum()}
    p = bo.filter(pl.col("is_pressure")).group_by(["bowler_id", "match_id"]).agg(
        **{f"p_{k}": v for k, v in cols.items()})
    n = bo.filter(~pl.col("is_pressure")).group_by(["bowler_id", "match_id"]).agg(
        **{f"b_{k}": v for k, v in cols.items()})
    panel = p.join(n, on=["bowler_id", "match_id"], how="full", coalesce=True)
    return panel.rename({"bowler_id": "player_id"})


def _innings_frame(b: pl.DataFrame, role: str, min_balls: int) -> pl.DataFrame:
    """Per (player, match) count of pressure innings and how many beat the baseline."""
    if role == "bat":
        df = batting_balls(b).filter(pl.col("is_pressure"))
        idcol, runs = "striker_id", pl.col("bat_runs").sum()
        grp = df.group_by([idcol, "match_id", "innings"]).agg(pl.len().alias("balls"), runs.alias("runs"))
        grp = grp.filter(pl.col("balls") >= min_balls).select(
            pl.col(idcol).alias("player_id"), "match_id", "innings",
            (pl.col("runs") * 100 / pl.col("balls")).alias("rate"))
    else:
        df = bowling_balls(b).filter(pl.col("is_pressure"))
        grp = df.group_by([idcol := "bowler_id", "match_id", "innings"]).agg(
            pl.col("_legal_i").sum().alias("balls"), pl.col("bowler_conceded").sum().alias("conceded"),
            pl.col("bowler_wicket").sum().alias("wkts"))
        grp = grp.filter(pl.col("balls") >= min_balls).select(
            pl.col(idcol).alias("player_id"), "match_id", "innings",
            (pl.col("conceded") * 6 / pl.col("balls")).alias("rate"))
    return grp


def build_panels(b: pl.DataFrame, cfg: Config | None = None) -> dict[str, pl.DataFrame]:
    cfg = cfg or Config()
    bat = _bat_panel(b)
    bowl = _bowl_panel(b)
    return {
        "bat": bat, "bowl": bowl,
        "bat_inn": _innings_frame(b, "bat", cfg.min_balls_in_innings),
        "bowl_inn": _innings_frame(b, "bowl", cfg.min_balls_in_innings),
    }


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def _z(x: np.ndarray, mean: float | None = None, sd: float | None = None) -> np.ndarray:
    m = np.nanmean(x) if mean is None else mean
    s = np.nanstd(x, ddof=1) if sd is None else sd
    if not np.isfinite(s) or s == 0:
        return np.zeros_like(x, dtype=float)
    return (x - m) / s


def _totals(panel: pl.DataFrame, cols: Iterable[str], n_players: int) -> dict[str, np.ndarray]:
    out = {}
    idx = panel["_pidx"].to_numpy()
    for c in cols:
        v = panel[c].fill_null(0).to_numpy().astype(float)
        out[c] = np.bincount(idx, weights=v, minlength=n_players)
    return out


def _prep(panel: pl.DataFrame, ids: np.ndarray) -> pl.DataFrame:
    idx = {pid: i for i, pid in enumerate(ids)}
    p = panel.with_columns(pl.col("player_id").replace_strict(idx, default=-1).alias("_pidx")).filter(
        pl.col("_pidx") >= 0).with_columns(pl.lit(len(ids)).alias("_n"))
    return p


def _bat_components(t: dict[str, np.ndarray], inn_beat: np.ndarray, inn_n: np.ndarray,
                    cfg: Config, shrink: bool = True) -> dict[str, np.ndarray]:
    p_balls = np.maximum(t["p_balls"], 1e-9)
    b_balls = np.maximum(t["b_balls"], 1e-9)
    p_sr = 100 * t["p_runs"] / p_balls
    b_sr = 100 * t["b_runs"] / b_balls
    p_dr = 100 * t["p_outs"] / p_balls
    b_dr = 100 * t["b_outs"] / b_balls
    lam = (t["p_balls"] / (t["p_balls"] + cfg.shrink_k)) if shrink else np.ones_like(p_balls)
    lift_sr = lam * (p_sr - b_sr)
    lift_dr = lam * (b_dr - p_dr)          # positive = survives better under pressure
    # level rates are themselves shrunk toward the eligible pool's pressure rate,
    # so a 120-ball cameo cannot outrank a 600-ball body of work on noise alone
    lam_lvl = t["p_balls"] / (t["p_balls"] + cfg.shrink_k_level)
    # situation-adjusted level: runs and survival versus the par of the exact states faced
    xruns = 100 * (t["p_runs"] - t["p_exp_runs"]) / p_balls
    xsurv = 100 * (t["p_exp_outs"] - t["p_outs"]) / p_balls
    pool_xr = float(np.average(xruns, weights=np.maximum(t["p_balls"], 1e-9)))
    pool_xs = float(np.average(xsurv, weights=np.maximum(t["p_balls"], 1e-9)))
    sr_adj = lam_lvl * xruns + (1 - lam_lvl) * pool_xr
    dr_adj = lam_lvl * xsurv + (1 - lam_lvl) * pool_xs
    level = cfg.bat_level_sr_share * _z(sr_adj) + (1 - cfg.bat_level_sr_share) * _z(dr_adj)
    lift = cfg.lift_sr_share * _z(lift_sr) + (1 - cfg.lift_sr_share) * _z(lift_dr)
    cons = (inn_beat + 1.0) / (inn_n + 2.0)
    return {
        "p_balls": t["p_balls"], "p_runs": t["p_runs"], "p_outs": t["p_outs"],
        "p_sr": p_sr, "base_sr": b_sr, "p_dr": p_dr, "base_dr": b_dr,
        "lift_sr": p_sr - b_sr, "lift_dr": b_dr - p_dr,
        "lift_sr_shrunk": lift_sr, "lift_dr_shrunk": lift_dr,
        "sr_adj": sr_adj, "dr_adj": dr_adj,
        "level_z": level, "lift_z": lift, "consistency": cons,
        "consistency_z": _z(cons),
    }


def _bowl_components(t: dict[str, np.ndarray], inn_beat: np.ndarray, inn_n: np.ndarray,
                     cfg: Config, shrink: bool = True) -> dict[str, np.ndarray]:
    p_balls = np.maximum(t["p_balls"], 1e-9)
    b_balls = np.maximum(t["b_balls"], 1e-9)
    p_econ = 6 * t["p_conceded"] / p_balls
    b_econ = 6 * t["b_conceded"] / b_balls
    p_wk = 100 * t["p_wkts"] / p_balls
    b_wk = 100 * t["b_wkts"] / b_balls
    lam = (t["p_balls"] / (t["p_balls"] + cfg.shrink_k)) if shrink else np.ones_like(p_balls)
    lift_econ = lam * (b_econ - p_econ)      # positive = cheaper under pressure
    lift_wkt = lam * (p_wk - b_wk)           # positive = strikes more under pressure
    lam_lvl = t["p_balls"] / (t["p_balls"] + cfg.shrink_k_level)
    xecon = 6 * (t["p_exp_conceded"] - t["p_conceded"]) / p_balls
    xwk = 100 * (t["p_wkts"] - t["p_exp_wkts"]) / p_balls
    pool_xe = float(np.average(xecon, weights=np.maximum(t["p_balls"], 1e-9)))
    pool_xw = float(np.average(xwk, weights=np.maximum(t["p_balls"], 1e-9)))
    econ_adj = lam_lvl * xecon + (1 - lam_lvl) * pool_xe
    wk_adj = lam_lvl * xwk + (1 - lam_lvl) * pool_xw
    level = cfg.bowl_level_econ_share * _z(econ_adj) + (1 - cfg.bowl_level_econ_share) * _z(wk_adj)
    lift = 0.5 * _z(lift_econ) + 0.5 * _z(lift_wkt)
    cons = (inn_beat + 1.0) / (inn_n + 2.0)
    return {
        "p_balls": t["p_balls"], "p_conceded": t["p_conceded"], "p_wkts": t["p_wkts"],
        "p_econ": p_econ, "base_econ": b_econ, "p_wk_rate": p_wk, "base_wk_rate": b_wk,
        "lift_econ": b_econ - p_econ, "lift_wkt": p_wk - b_wk,
        "lift_econ_shrunk": lift_econ, "lift_wkt_shrunk": lift_wkt,
        "econ_adj": econ_adj, "wk_adj": wk_adj,
        "level_z": level, "lift_z": lift, "consistency": cons,
        "consistency_z": _z(cons),
    }


def _assemble(ids: np.ndarray, comp: dict[str, np.ndarray], cfg: Config) -> pl.DataFrame:
    raw = cfg.w_level * comp["level_z"] + cfg.w_lift * comp["lift_z"] + cfg.w_cons * comp["consistency_z"]
    pri = np.clip(50 + 12.5 * raw, 0, 100)
    return pl.DataFrame({
        "player_id": ids,
        **{k: v for k, v in comp.items() if not k.endswith("_z") or k in {"level_z", "lift_z", "consistency_z"}},
        "pri_raw": raw, "pri": pri,
    })


def score_batters(b: pl.DataFrame, panels: dict[str, pl.DataFrame], cfg: Config,
                  ids: np.ndarray | None = None, shrink: bool | None = None) -> pl.DataFrame:
    panel = panels["bat"]
    ids = _player_universe(panel, panels["bat_inn"], cfg, "bat") if ids is None else ids
    p = _prep(panel, ids)
    n = len(ids)
    t = _totals(p, ["p_balls", "p_runs", "p_outs", "p_exp_runs", "p_exp_outs", "b_balls", "b_runs", "b_outs"], n)
    # consistency per player (innings-level, from the innings frame)
    inn = panels["bat_inn"].join(pl.DataFrame({"player_id": ids, "_pidx": np.arange(n)}), on="player_id", how="inner")
    inn_n = np.bincount(inn["_pidx"].to_numpy(), minlength=n).astype(float)
    beat = _innings_beat(inn, panels["bat"], ids, role="bat")
    comp = _bat_components(t, beat, inn_n, cfg, shrink=cfg.use_shrinkage if shrink is None else shrink)
    df = _assemble(ids, comp, cfg)
    return df.with_columns(pl.Series("pressure_matches", _count_matches(panel, ids)),
                           pl.Series("pressure_innings", inn_n))


def score_bowlers(b: pl.DataFrame, panels: dict[str, pl.DataFrame], cfg: Config,
                  ids: np.ndarray | None = None, shrink: bool | None = None) -> pl.DataFrame:
    panel = panels["bowl"]
    ids = _player_universe(panel, panels["bowl_inn"], cfg, "bowl") if ids is None else ids
    p = _prep(panel, ids)
    n = len(ids)
    t = _totals(p, ["p_balls", "p_conceded", "p_wkts", "p_exp_conceded", "p_exp_wkts", "b_balls", "b_conceded", "b_wkts"], n)
    inn = panels["bowl_inn"].join(pl.DataFrame({"player_id": ids, "_pidx": np.arange(n)}), on="player_id", how="inner")
    inn_n = np.bincount(inn["_pidx"].to_numpy(), minlength=n).astype(float)
    beat = _innings_beat(inn, panels["bowl"], ids, role="bowl")
    comp = _bowl_components(t, beat, inn_n, cfg, shrink=cfg.use_shrinkage if shrink is None else shrink)
    df = _assemble(ids, comp, cfg)
    return df.with_columns(pl.Series("pressure_matches", _count_matches(panel, ids)),
                           pl.Series("pressure_innings", inn_n))


def _count_matches(panel: pl.DataFrame, ids: np.ndarray) -> np.ndarray:
    p = panel.filter(pl.col("player_id").is_in(ids) & pl.col("p_balls").is_not_null())
    counts = p.group_by("player_id").agg(pl.len().alias("n"))
    m = dict(zip(counts["player_id"].to_list(), counts["n"].to_list()))
    return np.array([m.get(pid, 0) for pid in ids], dtype=float)


def _innings_beat(inn: pl.DataFrame, panel: pl.DataFrame, ids: np.ndarray, role: str) -> np.ndarray:
    """Count pressure innings in which the player beat their own non-pressure baseline."""
    n = len(ids)
    if role == "bat":
        base = panel.group_by("player_id").agg(
            pl.col("b_runs").sum().alias("br"), pl.col("b_balls").sum().alias("bb")).with_columns(
            (100 * pl.col("br") / pl.col("bb")).alias("base"))
        joined = inn.join(base.select("player_id", "base"), on="player_id", how="left")
        joined = joined.with_columns((pl.col("rate") > pl.col("base")).cast(pl.Int64).alias("beat"))
    else:
        base = panel.group_by("player_id").agg(
            pl.col("b_conceded").sum().alias("bc"), pl.col("b_balls").sum().alias("bb")).with_columns(
            (6 * pl.col("bc") / pl.col("bb")).alias("base"))
        joined = inn.join(base.select("player_id", "base"), on="player_id", how="left")
        joined = joined.with_columns((pl.col("rate") < pl.col("base")).cast(pl.Int64).alias("beat"))
    agg = joined.group_by("player_id").agg(pl.col("beat").sum().alias("beaten"))
    m = dict(zip(agg["player_id"].to_list(), agg["beaten"].to_list()))
    return np.array([m.get(pid, 0) for pid in ids], dtype=float)


def _player_universe(panel: pl.DataFrame, inn: pl.DataFrame, cfg: Config, role: str) -> np.ndarray:
    """Eligibility: enough pressure balls, matches and scored pressure innings."""
    min_balls = cfg.min_pressure_balls_bat if role == "bat" else cfg.min_pressure_balls_bowl
    tot = panel.group_by("player_id").agg(
        pl.col("p_balls").sum().alias("balls"),
        pl.col("b_balls").sum().alias("baseline_balls"),
        pl.col("match_id").n_unique().alias("matches"),
    ).filter((pl.col("balls") >= min_balls) & (pl.col("matches") >= cfg.min_pressure_matches)
             & (pl.col("baseline_balls").fill_null(0) >= cfg.min_baseline_balls))
    inns = inn.group_by("player_id").agg(pl.len().alias("innings"))
    ok = tot.join(inns, on="player_id", how="left").filter(
        pl.col("innings").fill_null(0) >= cfg.min_pressure_innings)
    return np.sort(ok["player_id"].to_numpy())


# ---------------------------------------------------------------------------
# Bootstrap: resample matches, rescore, observe rank movement
# ---------------------------------------------------------------------------
def bootstrap_ranks(ball: pl.DataFrame, panels: dict[str, pl.DataFrame], cfg: Config,
                    role: str, ids: np.ndarray, B: int = 300, seed: int = 7) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    panel = panels["bat" if role == "bat" else "bowl"]
    inn = panels["bat_inn" if role == "bat" else "bowl_inn"]
    id_to_i = {int(pid): i for i, pid in enumerate(ids)}
    n = len(ids)
    p = panel.filter(pl.col("player_id").is_in(ids)).with_columns(
        pl.col("player_id").replace_strict(id_to_i, default=-1).alias("_pidx")).filter(pl.col("_pidx") >= 0)
    matches = np.sort(p["match_id"].unique().to_numpy())
    m_to_i = {int(m): i for i, m in enumerate(matches)}
    p = p.with_columns(pl.col("match_id").replace_strict(m_to_i, default=-1).alias("_midx"))
    pidx = p["_pidx"].to_numpy()
    midx = p["_midx"].to_numpy()
    cols = (["p_balls", "p_runs", "p_outs", "p_exp_runs", "p_exp_outs", "b_balls", "b_runs", "b_outs"]
            if role == "bat" else
            ["p_balls", "p_conceded", "p_wkts", "p_exp_conceded", "p_exp_wkts",
             "b_balls", "b_conceded", "b_wkts"])
    vals = {c: p[c].fill_null(0).to_numpy().astype(float) for c in cols}

    i2 = inn.join(pl.DataFrame({"player_id": ids, "_pidx": np.arange(n)}), on="player_id", how="inner")
    i2 = i2.join(pl.DataFrame({"match_id": matches, "_midx": np.arange(len(matches))}), on="match_id", how="inner")
    base = (panel.group_by("player_id").agg(
        (100 * pl.col("b_runs").sum() / pl.col("b_balls").sum()).alias("bsr") if role == "bat" else
        (6 * pl.col("b_conceded").sum() / pl.col("b_balls").sum()).alias("bsr")).select("player_id", "bsr"))
    i2 = i2.join(base, on="player_id", how="left").with_columns(
        ((pl.col("rate") > pl.col("bsr")) if role == "bat" else (pl.col("rate") < pl.col("bsr")))
        .cast(pl.Float64).alias("beat"))
    i_pidx = i2["_pidx"].to_numpy(); i_midx = i2["_midx"].to_numpy(); i_beat = i2["beat"].to_numpy()

    ranks = np.full((B, n), np.nan)
    nm = len(matches)
    for bi in range(B):
        draw = rng.integers(0, nm, nm)
        mult = np.bincount(draw, minlength=nm).astype(float)
        w = mult[midx]
        t = {c: np.bincount(pidx, weights=vals[c] * w, minlength=n) for c in cols}
        inn_n = np.bincount(i_pidx, weights=mult[i_midx], minlength=n)
        beat = np.bincount(i_pidx, weights=i_beat * mult[i_midx], minlength=n)
        comp = (_bat_components(t, beat, inn_n, cfg) if role == "bat"
                else _bowl_components(t, beat, inn_n, cfg))
        raw = cfg.w_level * comp["level_z"] + cfg.w_lift * comp["lift_z"] + cfg.w_cons * comp["consistency_z"]
        order = np.argsort(-raw)
        r = np.empty(n); r[order] = np.arange(1, n + 1)
        ranks[bi] = r
    out = pl.DataFrame({"player_id": ids,
                        "rank_median": np.nanmedian(ranks, axis=0),
                        "rank_p05": np.nanpercentile(ranks, 5, axis=0),
                        "rank_p95": np.nanpercentile(ranks, 95, axis=0),
                        "p_top10": (ranks <= 10).mean(axis=0),
                        "rank_sd": np.nanstd(ranks, axis=0)})
    return out


# ---------------------------------------------------------------------------
# Situation-adjusted (par) expectations
# ---------------------------------------------------------------------------
OVER_BUCKETS = [(1, 6), (7, 10), (11, 15), (16, 18), (19, 20)]
WICKET_BUCKETS = [(0, 0), (1, 2), (3, 4), (5, 6), (7, 9)]


def _bucket_expr(col: str, buckets: list[tuple[int, int]], name: str) -> pl.Expr:
    expr = None
    for lo, hi in buckets:
        cond = (pl.col(col) >= lo) & (pl.col(col) <= hi)
        expr = pl.when(cond).then(pl.lit((lo, hi))).otherwise(expr) if expr is not None else \
            pl.when(cond).then(pl.lit((lo, hi)))
    return expr.fill_null(pl.lit(buckets[-1])).alias(name)


def add_par(ball: pl.DataFrame, pack) -> pl.DataFrame:
    """Attach the *par* run and wicket expectation for the state the ball is bowled in.

    Par is the pooled average of every other delivery bowled in the same
    (competition kind, innings, over bucket, wickets-lost bucket) cell. It is the
    benchmark that makes cross-situation comparison fair: a finisher batting at
    the death is measured against death-over par, not against an opener's par.
    """
    kind = competition_labels(pack).select("comp_id", "competition_kind", "season")
    b = ball.join(kind, on="comp_id", how="left").with_columns(
        _bucket_expr("overid", OVER_BUCKETS, "over_bucket"),
        _bucket_expr("wickets_before", WICKET_BUCKETS, "wicket_bucket"),
    )
    faced = b.filter(~pl.col("extras_type").is_in(["wide", "Penalty"]))
    legal = b.filter(pl.col("is_legal"))
    keys = ["competition_kind", "innings", "over_bucket", "wicket_bucket"]

    bat_par = faced.group_by(keys).agg(
        pl.len().alias("_n"),
        (pl.col("bat_runs").sum() / pl.len()).alias("exp_bat_runs"),
        (pl.col("striker_out").sum() / pl.len()).alias("exp_striker_out"),
    )
    # conceded runs include wides/no-balls; the denominator is legal balls only
    bowl_par = b.group_by(keys).agg(
        pl.col("_legal_i").sum().alias("_n"),
        (pl.col("bowler_conceded").sum() / pl.col("_legal_i").sum().clip(1)).alias("exp_conceded"),
        (pl.col("bowler_wicket").sum() / pl.col("_legal_i").sum().clip(1)).alias("exp_bowler_wicket"),
    )
    # fall back to the coarser (innings, over bucket) marginal for thin cells
    coarse = faced.group_by(["innings", "over_bucket"]).agg(
        (pl.col("bat_runs").sum() / pl.len()).alias("c_exp_bat_runs"),
        (pl.col("striker_out").sum() / pl.len()).alias("c_exp_striker_out"),
    )
    coarse_b = b.group_by(["innings", "over_bucket"]).agg(
        (pl.col("bowler_conceded").sum() / pl.col("_legal_i").sum().clip(1)).alias("c_exp_conceded"),
        (pl.col("bowler_wicket").sum() / pl.col("_legal_i").sum().clip(1)).alias("c_exp_bowler_wicket"),
    )
    MIN_CELL = 200
    out = b.join(bat_par, on=keys, how="left").join(bowl_par, on=keys, how="left").join(
        coarse, on=["innings", "over_bucket"], how="left").join(
        coarse_b, on=["innings", "over_bucket"], how="left")
    out = out.with_columns(
        pl.when(pl.col("_n").fill_null(0) >= MIN_CELL).then(pl.col("exp_bat_runs"))
          .otherwise(pl.col("c_exp_bat_runs")).alias("exp_bat_runs"),
        pl.when(pl.col("_n").fill_null(0) >= MIN_CELL).then(pl.col("exp_striker_out"))
          .otherwise(pl.col("c_exp_striker_out")).alias("exp_striker_out"),
        pl.when(pl.col("_n").fill_null(0) >= MIN_CELL).then(pl.col("exp_conceded"))
          .otherwise(pl.col("c_exp_conceded")).alias("exp_conceded"),
        pl.when(pl.col("_n").fill_null(0) >= MIN_CELL).then(pl.col("exp_bowler_wicket"))
          .otherwise(pl.col("c_exp_bowler_wicket")).alias("exp_bowler_wicket"),
    ).drop(["_n", "c_exp_bat_runs", "c_exp_striker_out", "c_exp_conceded", "c_exp_bowler_wicket"])
    return out
