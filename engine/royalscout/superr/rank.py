"""Ranking, alternative methods, sensitivity and adversarial tests.

The audit asks four questions of every recommendation:

1. Does it survive a *different method*?          -> ``alternative_table``
2. Does it survive a *different* sample rule?     -> ``threshold_sensitivity``
3. Does it survive removing its best match?       -> ``leave_one_match_out``
4. Is the sample big enough to believe it at all? -> ``metrics.bootstrap_ranks``

Nothing here is cosmetic: each function returns the evidence a competing analyst
would need in order to overturn a pick.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import polars as pl

from . import metrics as M
from .load import competition_labels
from .pressure import DEFAULT as PRESSURE_DEFAULT, GAP, Thresholds, WIDE, tag_pressure


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3:
        return float("nan")
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ra -= ra.mean(); rb -= rb.mean()
    denom = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / denom) if denom else float("nan")


def rank_map(df: pl.DataFrame, score: str = "pri") -> dict[int, int]:
    d = df.sort(score, descending=True).with_row_index("rank")
    return dict(zip(d["player_id"].to_list(), (d["rank"] + 1).to_list()))


# ---------------------------------------------------------------------------
@dataclass
class Variant:
    name: str
    kind: str = "config"            # config | comp | knockout | level_only | lift_only | raw_level
    cfg: M.Config | None = None
    competition: str | None = None
    pressure: Thresholds | None = None


BASE = M.Config()
LOOSE = BASE.with_(label="loose", min_pressure_balls_bat=60, min_pressure_balls_bowl=60,
                   min_pressure_matches=4, min_pressure_innings=5, min_baseline_balls=30)
TIGHT = BASE.with_(label="tight", min_pressure_balls_bat=200, min_pressure_balls_bowl=200,
                   min_pressure_matches=10, min_pressure_innings=12, min_baseline_balls=120)
NO_SHRINK = BASE.with_(label="no_shrinkage", use_shrinkage=False)
EQUAL = BASE.with_(label="equal_weights", w_level=1 / 3, w_lift=1 / 3, w_cons=1 / 3)
LIFT_HEAVY = BASE.with_(label="lift_heavy", w_level=0.25, w_lift=0.60, w_cons=0.15)
LEVEL_HEAVY = BASE.with_(label="level_heavy", w_level=0.75, w_lift=0.15, w_cons=0.10)


def variant_list() -> list[Variant]:
    return [
        Variant("primary", "config", BASE),
        Variant("loose_thresholds", "config", LOOSE),
        Variant("tight_thresholds", "config", TIGHT),
        Variant("no_shrinkage", "config", NO_SHRINK),
        Variant("equal_weights", "config", EQUAL),
        Variant("lift_heavy", "config", LIFT_HEAVY),
        Variant("level_heavy", "config", LEVEL_HEAVY),
        Variant("level_only", "level_only", BASE),
        Variant("lift_only", "lift_only", BASE),
        Variant("raw_pressure_level", "raw_level", BASE),
        Variant("ipl_only", "comp", LOOSE, competition="IPL"),
        Variant("t20i_only", "comp", LOOSE, competition="T20I"),
        Variant("knockouts_only", "knockout", LOOSE),
        Variant("include_other_t20", "config", BASE.with_(label="with_other_t20",
                                                         competitions=("IPL", "T20I", "Other T20"))),
        Variant("pressure_v2_wide", "config", BASE, pressure=WIDE),
        Variant("pressure_v3_rate_gap", "config", BASE, pressure=GAP),
    ]


def _filtered_balls(b: pl.DataFrame, pack, variant: Variant) -> pl.DataFrame:
    if variant.kind == "comp" and variant.competition:
        if "competition_kind" not in b.columns:
            kind = competition_labels(pack).select("comp_id", "competition_kind")
            b = b.join(kind, on="comp_id", how="left")
        return b.filter(pl.col("competition_kind") == variant.competition)
    if variant.kind == "knockout":
        return b.filter(pl.col("knockout") > 0)
    return b


def _apply_competitions(b: pl.DataFrame, cfg: M.Config) -> pl.DataFrame:
    if "competition_kind" in b.columns and cfg.competitions:
        return b.filter(pl.col("competition_kind").is_in(list(cfg.competitions)))
    return b


def score_role(b: pl.DataFrame, cfg: M.Config, role: str, variant: Variant | None = None,
               panels: dict[str, pl.DataFrame] | None = None, ids: np.ndarray | None = None) -> pl.DataFrame:
    if panels is None and not (variant is not None and variant.kind in ("comp", "knockout")):
        b = _apply_competitions(b, cfg)
    panels = panels or M.build_panels(b, cfg)
    if role == "bat":
        ids = M._player_universe(panels["bat"], panels["bat_inn"], cfg, "bat") if ids is None else ids
        df = M.score_batters(b, panels, cfg, ids=ids)
    else:
        ids = M._player_universe(panels["bowl"], panels["bowl_inn"], cfg, "bowl") if ids is None else ids
        df = M.score_bowlers(b, panels, cfg, ids=ids)
    if variant is not None and variant.kind == "level_only":
        raw = df["level_z"].to_numpy()
        df = df.with_columns(pl.Series("pri_raw", raw), pl.Series("pri", np.clip(50 + 12.5 * raw, 0, 100)))
    elif variant is not None and variant.kind == "lift_only":
        raw = 0.8 * df["lift_z"].to_numpy() + 0.2 * df["consistency_z"].to_numpy()
        df = df.with_columns(pl.Series("pri_raw", raw), pl.Series("pri", np.clip(50 + 12.5 * raw, 0, 100)))
    elif variant is not None and variant.kind == "raw_level":
        col = "p_sr" if role == "bat" else "p_econ"
        x = df[col].to_numpy().astype(float)
        if role == "bowl":
            x = -x
        raw = (x - x.mean()) / (x.std(ddof=1) or 1.0)
        df = df.with_columns(pl.Series("pri_raw", raw), pl.Series("pri", np.clip(50 + 12.5 * raw, 0, 100)))
    return df.sort("pri", descending=True)


def alternative_table(b: pl.DataFrame, pack, role: str) -> tuple[pl.DataFrame, pl.DataFrame, dict[str, pl.DataFrame]]:
    """Score every variant; return (summary, rank matrix, full tables by variant)."""
    ranks: dict[str, dict[int, int]] = {}
    tables: dict[str, pl.DataFrame] = {}
    notes: dict[str, str] = {}
    for v in variant_list():
        cfg = v.cfg or BASE
        tagged = tag_pressure(b, v.pressure) if v.pressure is not None else (
            b if "is_pressure" in b.columns else tag_pressure(b))
        balls = _filtered_balls(tagged, pack, v)
        if balls.height < 100:
            notes[v.name] = "too few deliveries"
            continue
        try:
            df = score_role(balls, cfg, role, v)
        except Exception as exc:                    # noqa: BLE001 - a variant failing is itself a finding
            notes[v.name] = f"scoring failed: {exc}"
            continue
        if df.height < 10:
            notes[v.name] = f"only {df.height} eligible players"
        ranks[v.name] = rank_map(df)
        tables[v.name] = df

    prim = ranks.get("primary", {})
    prim_top = {p for p, r in prim.items() if r <= 10}
    rows = []
    for name in ranks:
        rm = ranks[name]
        common = sorted(set(rm) & set(prim))
        a = np.array([prim[p] for p in common], dtype=float)
        c = np.array([rm[p] for p in common], dtype=float)
        top = {p for p, r in rm.items() if r <= 10}
        rows.append({
            "variant": name, "eligible": len(rm),
            "top10_overlap": len(top & prim_top),
            "spearman_vs_primary": round(spearman(a, c), 3),
            "jaccard_top10": round(len(top & prim_top) / max(1, len(top | prim_top)), 3),
            "note": notes.get(name, ""),
        })
    for name, note in notes.items():
        rows.append({"variant": name, "eligible": 0, "top10_overlap": 0,
                     "spearman_vs_primary": float("nan"), "jaccard_top10": 0.0, "note": note})
    all_ids = sorted(set().union(*[set(m) for m in ranks.values()])) if ranks else []
    matrix = pl.DataFrame({"player_id": all_ids})
    for name, rm in ranks.items():
        matrix = matrix.with_columns(pl.col("player_id").replace_strict(rm, default=None).alias(f"rank_{name}"))
    return pl.DataFrame(rows), matrix, tables


def leave_one_match_out(b: pl.DataFrame, cfg: M.Config, role: str, player_ids: list[int],
                        top_n_compare: int = 10) -> pl.DataFrame:
    """Re-rank the whole pool with each player's most influential match removed."""
    panels = M.build_panels(b, cfg)
    key = "bat" if role == "bat" else "bowl"
    inn_key = "bat_inn" if role == "bat" else "bowl_inn"
    panel, inn = panels[key], panels[inn_key]
    ids = M._player_universe(panel, inn, cfg, role)
    base = score_role(b, cfg, role, panels=panels, ids=ids)
    base_rank = rank_map(base)
    out = []
    score_col = "p_runs" if role == "bat" else "p_wkts"
    for pid in player_ids:
        sub = panel.filter(pl.col("player_id") == pid)
        if sub.height == 0:
            continue
        # most influential = the match contributing most pressure runs (bat) / wickets (bowl)
        match_id = int(sub.sort(score_col, descending=True)["match_id"][0])
        new_panels = dict(panels)
        new_panels[key] = panel.filter(~((pl.col("player_id") == pid) & (pl.col("match_id") == match_id)))
        new_panels[inn_key] = inn.filter(~((pl.col("player_id") == pid) & (pl.col("match_id") == match_id)))
        df = score_role(b, cfg, role, panels=new_panels, ids=ids)
        rm = rank_map(df)
        out.append({"player_id": pid, "dropped_match": match_id,
                    "rank_full": base_rank.get(pid), "rank_without_best_match": rm.get(pid),
                    "rank_change": (rm.get(pid, 999) or 999) - (base_rank.get(pid, 999) or 999),
                    "still_top10": (rm.get(pid, 999) or 999) <= top_n_compare})
    return pl.DataFrame(out)


def threshold_sensitivity(b: pl.DataFrame, role: str) -> pl.DataFrame:
    prim = score_role(b, BASE, role)
    prim_rm = rank_map(prim)
    prim_top = {p for p, r in prim_rm.items() if r <= 10}
    rows = []
    for balls in (60, 90, 120, 160, 200, 260):
        for base_min in (30, 60, 120):
            cfg = replace(BASE, min_pressure_balls_bat=balls, min_pressure_balls_bowl=balls,
                          min_baseline_balls=base_min)
            try:
                df = score_role(b, cfg, role)
            except Exception:                       # noqa: BLE001
                continue
            rm = rank_map(df)
            top = {p for p, r in rm.items() if r <= 10}
            common = sorted(set(rm) & set(prim_rm))
            rows.append({
                "pressure_balls_min": balls, "baseline_balls_min": base_min,
                "eligible": len(rm), "top10_overlap": len(top & prim_top),
                "spearman_vs_primary": round(spearman(np.array([prim_rm[p] for p in common], dtype=float),
                                                      np.array([rm[p] for p in common], dtype=float)), 3),
                "top10": ", ".join(str(p) for p in sorted(top, key=lambda p: rm[p])),
            })
    return pl.DataFrame(rows)


def situation_breakdown(b: pl.DataFrame, role: str, player_ids: list[int]) -> pl.DataFrame:
    """Where a player's pressure score actually comes from, per trigger."""
    idcol = "striker_id" if role == "bat" else "bowler_id"
    df = b.filter(pl.col(idcol).is_in(player_ids) & pl.col("is_pressure"))
    if role == "bat":
        agg = df.group_by([pl.col(idcol).alias("player_id"), "pressure_reason"]).agg(
            pl.len().alias("balls"), pl.col("bat_runs").sum().alias("runs"),
            pl.col("striker_out").sum().alias("outs"),
            pl.col("match_id").n_unique().alias("matches"))
        agg = agg.with_columns((pl.col("runs") * 100 / pl.col("balls")).round(1).alias("sr"))
    else:
        agg = df.group_by([pl.col(idcol).alias("player_id"), "pressure_reason"]).agg(
            pl.len().alias("balls"), pl.col("bowler_conceded").sum().alias("conceded"),
            pl.col("bowler_wicket").sum().alias("wkts"),
            pl.col("match_id").n_unique().alias("matches"))
        agg = agg.with_columns((pl.col("conceded") * 6 / pl.col("balls")).round(2).alias("econ"))
    return agg.sort(["player_id", "balls"], descending=[False, True])


def split_profile(b: pl.DataFrame, pack, role: str, player_ids: list[int]) -> pl.DataFrame:
    """Pressure production split by competition kind, season and innings phase."""
    idcol = "striker_id" if role == "bat" else "bowler_id"
    kind = competition_labels(pack).select("comp_id", "competition_kind", "season")
    df = b.filter(pl.col(idcol).is_in(player_ids) & pl.col("is_pressure")).join(kind, on="comp_id", how="left")
    if role == "bat":
        agg = df.group_by([pl.col(idcol).alias("player_id"), "competition_kind", "season"]).agg(
            pl.len().alias("pressure_balls"), pl.col("bat_runs").sum().alias("runs"),
            pl.col("striker_out").sum().alias("outs"))
        agg = agg.with_columns((pl.col("runs") * 100 / pl.col("pressure_balls")).round(1).alias("sr"))
    else:
        agg = df.group_by([pl.col(idcol).alias("player_id"), "competition_kind", "season"]).agg(
            pl.len().alias("pressure_balls"), pl.col("bowler_conceded").sum().alias("conceded"),
            pl.col("bowler_wicket").sum().alias("wkts"))
        agg = agg.with_columns((pl.col("conceded") * 6 / pl.col("pressure_balls")).round(2).alias("econ"))
    return agg.sort(["player_id", "season", "competition_kind"])


def season_stability(b: pl.DataFrame, cfg: M.Config, role: str, player_ids: list[int],
                     min_balls_per_season: int = 20) -> pl.DataFrame:
    """Does the pressure record hold up season by season, or rest on one year?

    For every player/season with enough pressure cricket, compares the player's
    pressure rate with their own all-competition baseline rate.
    """
    idcol = "striker_id" if role == "bat" else "bowler_id"
    df = b.filter(pl.col(idcol).is_in(player_ids))
    # baseline per player over the whole analysed pool (non-pressure)
    base = (df.filter(~pl.col("is_pressure")).group_by(idcol).agg(
        (100 * pl.col("bat_runs").sum() / pl.len()).alias("base_sr") if role == "bat" else
        (6 * pl.col("bowler_conceded").sum() / pl.len()).alias("base_econ")))
    per = df.filter(pl.col("is_pressure")).group_by([idcol, "season"]).agg(
        pl.len().alias("pressure_balls"),
        (100 * pl.col("bat_runs").sum() / pl.len()).alias("sr") if role == "bat" else
        (6 * pl.col("bowler_conceded").sum() / pl.len()).alias("econ"),
        pl.col("match_id").n_unique().alias("matches"),
    ).join(base, on=idcol, how="left")
    per = per.filter(pl.col("pressure_balls") >= min_balls_per_season)
    if role == "bat":
        per = per.with_columns((pl.col("sr") - pl.col("base_sr")).alias("lift"))
    else:
        per = per.with_columns((pl.col("base_econ") - pl.col("econ")).alias("lift"))
    agg = per.group_by(idcol).agg(
        pl.len().alias("seasons_evaluated"),
        (pl.col("lift") > 0).sum().alias("seasons_above_baseline"),
        pl.col("lift").min().round(2).alias("worst_season_lift"),
        pl.col("lift").max().round(2).alias("best_season_lift"),
        pl.col("pressure_balls").sum().alias("pressure_balls_in_evaluated_seasons"),
    )
    return agg.rename({idcol: "player_id"}).sort("seasons_above_baseline", descending=True)


def selection_gates(ranked: pl.DataFrame, alt_matrix: pl.DataFrame, stability: pl.DataFrame,
                    max_median_rank: float = 15.0, min_seasons: int = 2) -> pl.DataFrame:
    """Attach the two robustness gates used to confirm a final selection.

    Gate A (method robustness): the player's median rank across every alternative
    method must be inside the top 15 (roughly the top tenth of an eligible pool), so the pick is not an artefact of one
    weighting, one sample rule or one competition.
    Gate B (season replication): the pressure record must be repeated in at least
    two seasons with enough pressure cricket, so it is not one hot tournament.
    """
    rank_cols = [c for c in alt_matrix.columns if c.startswith("rank_") and "knockout" not in c]
    arr = alt_matrix.select(rank_cols).to_numpy().astype(float)
    med = np.nanmedian(arr, axis=1)
    n10 = np.nansum(arr <= 10, axis=1).astype(int)
    nvar = np.sum(~np.isnan(arr), axis=1).astype(int)
    alt = alt_matrix.select("player_id").with_columns(
        pl.Series("median_rank_across_methods", np.round(med, 2)),
        pl.Series("methods_with_top10", n10), pl.Series("methods_available", nvar))
    df = ranked.join(alt, on="player_id", how="left").join(
        stability.select("player_id", "seasons_evaluated", "seasons_above_baseline",
                         "worst_season_lift", "best_season_lift"), on="player_id", how="left")
    df = df.with_columns(
        (pl.col("median_rank_across_methods") <= max_median_rank).fill_null(False).alias("gate_method"),
        (pl.col("seasons_evaluated").fill_null(0) >= min_seasons).alias("gate_season"),
    ).with_columns((pl.col("gate_method") & pl.col("gate_season")).alias("gate_pass"))
    return df


def select_final(scored: pl.DataFrame, n: int = 10, depth: int = 15) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Confirm the top ``n`` by PRI, swapping out any pick that fails a gate.

    The ranking order is the model's; the gates are a confirmation screen. A pick
    that fails a gate is replaced by the highest-ranked candidate that passes and
    sits within ``depth`` of the list. If no confirmed replacement exists inside
    that depth, the original pick is kept and marked ``confirmed=False`` — the
    list is never silently shortened.
    """
    ordered = scored.sort("pri", descending=True)
    rows = ordered.to_dicts()
    pool = [r for r in rows[:depth]]
    rest = [r for r in rows[depth:]]
    top = [dict(r) for r in rows[:n]]
    confirmed_ids = {r["player_id"] for r in top if r["gate_pass"]}
    swaps, rejected = [], []
    for i, pick in enumerate(top):
        if pick["gate_pass"]:
            continue
        replacement = next((r for r in pool if r["gate_pass"] and r["player_id"] not in confirmed_ids
                            and r["player_id"] not in {p["player_id"] for p in top}), None)
        if replacement is None:
            replacement = next((r for r in rest if r["gate_pass"] and r["player_id"] not in confirmed_ids), None)
        if replacement is not None:
            rejected.append(pick)
            top[i] = dict(replacement)
            confirmed_ids.add(replacement["player_id"])
        else:
            rejected.append(pick)
            top[i] = {**pick, "gate_pass": False}
    # keep the model's ordering for the retained players
    kept_ids = [r["player_id"] for r in top]
    order_index = {r["player_id"]: i for i, r in enumerate(rows)}
    top = sorted(top, key=lambda r: order_index[r["player_id"]])
    picked = pl.DataFrame(top).with_row_index("_i").with_columns(
        (pl.col("_i") + 1).alias("rank")).drop("_i").with_columns(
        pl.col("gate_pass").alias("confirmed"))
    rej = pl.DataFrame(rejected) if rejected else pl.DataFrame()
    return picked, rej
