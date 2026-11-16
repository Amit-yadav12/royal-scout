#!/usr/bin/env python3
"""Full audit + ranking run on the real SupeRR Selector data pack.

    python scripts/superr_audit.py --data ../data/real --out ../reports

Produces every artefact the report and the dashboard consume. Nothing is
hard-coded: all numbers come from the delivered CSVs on disk.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from royalscout.superr import load as L                      # noqa: E402
from royalscout.superr import validate as V                  # noqa: E402
from royalscout.superr import verify as VF                   # noqa: E402
from royalscout.superr import metrics as M                   # noqa: E402
from royalscout.superr import rank as R                      # noqa: E402
from royalscout.superr.pressure import tag_pressure, MIN_PRESSURE_BALLS_BAT  # noqa: E402


def _trigger_table(reg: pl.DataFrame) -> list[dict]:
    """Per-trigger difficulty, to show each pressure rule tags harder cricket."""
    out = []
    for reason, grp in reg.group_by("pressure_reason"):
        key = reason[0]
        balls = grp.height
        legal = int(grp["_legal_i"].sum())
        out.append({
            "reason": key, "balls": balls,
            "share_of_all": round(balls / reg.height, 4),
            "runs_per_over": round(float(grp["total_runs"].sum() * 6 / max(legal, 1)), 3),
            "wickets_per_100": round(100 * float(grp["is_wicket"].mean()), 3),
            "boundary_pct": round(100 * float(grp["is_four"].mean()), 3),
            "par_runs_per_ball_bat": round(float(grp["exp_bat_runs"].mean()), 4),
            "fielding_side_win_pct": None,
        })
    return sorted(out, key=lambda r: -r["balls"])


def log(msg: str, t0: float) -> None:
    print(f"[{time.time() - t0:6.1f}s] {msg}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="../data/real")
    ap.add_argument("--out", default="../reports")
    ap.add_argument("--bootstrap", type=int, default=400)
    args = ap.parse_args()
    t0 = time.time()
    data_dir, out = Path(args.data).resolve(), Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    # ---------------- load, harmonise, tag ----------------
    pack = L.load_raw(data_dir)
    log(f"loaded {pack.ball.height:,} deliveries from {data_dir}", t0)
    ball = L.derive_ball_state(pack)
    ball, merge_trail = L.harmonise_identities(ball)
    ball = tag_pressure(ball)
    ball = M.add_par(ball, pack)
    reg_all = ball.filter(pl.col("innings") <= 2)
    cfg_primary = M.Config()
    reg = reg_all.filter(pl.col("competition_kind").is_in(list(cfg_primary.competitions)))
    names = L.player_names(pack)
    log(f"analysed pool: {reg.height:,} regulation deliveries in "
        f"{sorted(cfg_primary.competitions)} (all T20: {reg_all.height:,})", t0)

    # ---------------- validation ----------------
    checks = V.run_all(pack, ball)
    log(f"validation: {sum(c.status == 'pass' for c in checks)} pass / "
        f"{sum(c.status == 'fail' for c in checks)} fail of {len(checks)}", t0)
    sample_players = [int(p) for p in reg["striker_id"].unique().sort()[:25]]
    checks += VF.run(pack, ball, data_dir, sample_players)
    log(f"independent recomputation: {sum(c.status == 'pass' for c in checks[-6:])}/6 pass", t0)
    (out / "validation.json").write_text(json.dumps([c.as_dict() for c in checks], indent=2, default=str))

    # ---------------- scoring ----------------
    cfg = cfg_primary
    panels = M.build_panels(reg, cfg)
    results: dict[str, dict] = {}
    for role in ("bat", "bowl"):
        ids = M._player_universe(panels["bat" if role == "bat" else "bowl"],
                                 panels["bat_inn" if role == "bat" else "bowl_inn"], cfg, role)
        df = R.score_role(reg, cfg, role, panels=panels, ids=ids)
        bs = M.bootstrap_ranks(reg, panels, cfg, role, ids, B=args.bootstrap, seed=20261115)
        df = df.join(bs, on="player_id", how="left").with_columns(
            pl.col("player_id").replace_strict(names, default="Unknown").alias("player_name")
        ).with_row_index("rank").with_columns((pl.col("rank") + 1).alias("rank"))
        df.write_csv(out / f"rankings_{role}.csv")
        log(f"{role}: {df.height} eligible, ranked and bootstrapped ({args.bootstrap} resamples)", t0)
        results[role] = {"ranked": df, "ids": ids}

    # alternative methods / sensitivity / adversarial tests
    alt_matrices: dict[str, pl.DataFrame] = {}
    for role in ("bat", "bowl"):
        summary, matrix, tables = R.alternative_table(reg_all, pack, role)
        alt_matrices[role] = matrix
        summary.write_csv(out / f"alternatives_{role}.csv")
        matrix.with_columns(pl.col("player_id").replace_strict(names, default="Unknown").alias("player_name")) \
            .write_csv(out / f"alternative_ranks_{role}.csv")
        R.threshold_sensitivity(reg, role).write_csv(out / f"threshold_sensitivity_{role}.csv")
        top = results[role]["ranked"].head(15)
        R.leave_one_match_out(reg, cfg, role, top["player_id"].to_list()).with_columns(
            pl.col("player_id").replace_strict(names, default="Unknown").alias("player_name")
        ).write_csv(out / f"leave_one_match_out_{role}.csv")
        R.situation_breakdown(reg, role, top["player_id"].to_list()).with_columns(
            pl.col("player_id").replace_strict(names, default="Unknown").alias("player_name")
        ).write_csv(out / f"situation_breakdown_{role}.csv")
        R.season_stability(reg, cfg, role, results[role]["ranked"].head(40)["player_id"].to_list()).with_columns(
            pl.col("player_id").replace_strict(names, default="Unknown").alias("player_name")
        ).write_csv(out / f"season_stability_{role}.csv")
        R.split_profile(reg, pack, role, top["player_id"].to_list()).with_columns(
            pl.col("player_id").replace_strict(names, default="Unknown").alias("player_name")
        ).write_csv(out / f"split_profile_{role}.csv")
        log(f"{role}: alternatives, thresholds, leave-one-out, situation and split profiles written", t0)

    # final 10 + 10, through the documented selection gates
    final = {}
    for role in ("bat", "bowl"):
        stab = pl.read_csv(out / f"season_stability_{role}.csv")
        scored = R.selection_gates(results[role]["ranked"], alt_matrices[role], stab)
        scored.write_csv(out / f"selection_pool_{role}.csv")
        picked, rejected = R.select_final(scored, n=10)
        results[role]["final"] = picked
        results[role]["rejected"] = rejected
        if rejected.height:
            log(f"{role}: {rejected.height} candidate(s) failed a gate and were passed over", t0)
        top = picked
        final[role] = top.select(
            "rank", "player_id", "player_name", "pri", "p_balls", "pressure_innings",
            "rank_median", "rank_p05", "rank_p95", "p_top10",
            "median_rank_across_methods", "methods_with_top10", "methods_available",
            "seasons_evaluated", "seasons_above_baseline", "worst_season_lift", "best_season_lift",
            *[c for c in ("p_sr", "base_sr", "lift_sr", "p_dr", "base_dr")
              if c in top.columns],
            *[c for c in ("p_econ", "base_econ", "lift_econ", "p_wk_rate", "base_wk_rate")
              if c in top.columns],
            "consistency", "level_z", "lift_z",
        )
        final[role].write_csv(out / f"final_top10_{role}.csv")
        if results[role]["rejected"].height:
            results[role]["rejected"].write_csv(out / f"final_rejected_{role}.csv")
    (out / "final_selection.json").write_text(json.dumps(
        {r: final[r].to_dicts() for r in final}, indent=2, default=str))

    # ---------------- audit facts for the report ----------------
    facts = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "deliveries": int(pack.ball.height),
        "deliveries_used": int(reg.height),
        "matches_with_ball_data": int(reg["match_id"].n_unique()),
        "matches_in_matches_csv": int(pack.matches.height),
        "competitions": int(pack.competitions.height),
        "players_named": len(names),
        "pressure_balls": int(reg["is_pressure"].sum()),
        "pressure_share": round(float(reg["is_pressure"].mean()), 4),
        "pressure_balls_first_innings": int(reg.filter(pl.col("innings") == 1)["is_pressure"].sum()),
        "pressure_balls_chases": int(reg.filter(pl.col("innings") == 2)["is_pressure"].sum()),
        "pressure_rpo": round(float(reg.filter(pl.col("is_pressure"))["total_runs"].sum() * 6 /
                                     reg.filter(pl.col("is_pressure"))["_legal_i"].sum()), 3),
        "nonpressure_rpo": round(float(reg.filter(~pl.col("is_pressure"))["total_runs"].sum() * 6 /
                                       reg.filter(~pl.col("is_pressure"))["_legal_i"].sum()), 3),
        "pressure_wickets_per_100": round(100 * float(reg.filter(pl.col("is_pressure"))["is_wicket"].mean()), 3),
        "nonpressure_wickets_per_100": round(100 * float(reg.filter(~pl.col("is_pressure"))["is_wicket"].mean()), 3),
        "pressure_reason_mix": {r["pressure_reason"]: int(r["len"]) for r in
                                reg.group_by("pressure_reason").agg(pl.len()).to_dicts()},
        "trigger_validation": _trigger_table(reg),
        "identity_merges": merge_trail,
        "chase_target_unknown_innings": int(reg.filter(pl.col("chase_target_unknown")).select(
            pl.struct("match_id", "innings").n_unique()).item()),
        "super_over_deliveries": int(ball.filter(pl.col("innings") > 2).height),
        "validation": {"total": len(checks),
                       "pass": sum(c.status == "pass" for c in checks),
                       "fail": sum(c.status == "fail" for c in checks),
                       "failures": [c.as_dict() for c in checks if c.status == "fail"]},
        "eligible": {r: int(results[r]["ranked"].height) for r in results},
        "config": asdict(M.Config()),
        "thresholds": {"CHASE_RRR_HIGH": 11.0, "CHASE_RRR_HIGH_FROM_OVER": 5,
                       "CHASE_RRR_LATE": 9.5, "CHASE_LATE_FROM_OVER": 15,
                       "COLLAPSE_WICKETS": 6, "DEATH_OVER": 17, "DEATH_MIN_WICKETS": 4,
                       "TIGHT_BALLS_LEFT": 18, "TIGHT_RUNS_NEEDED": 30},
        "competition_balls": {r["competition_kind"]: int(r["len"]) for r in
                              reg.join(L.competition_labels(pack).select("comp_id", "competition_kind"),
                                       on="comp_id", how="left").group_by("competition_kind").agg(pl.len()).to_dicts()},
    }
    (out / "audit_facts.json").write_text(json.dumps(facts, indent=2, default=str))
    log("wrote audit_facts.json, final_selection.json", t0)

    # console summary
    print("\n" + "=" * 96)
    for role in ("bat", "bowl"):
        print(f"\nFINAL TOP 10 {role.upper()}ERS")
        cols = ["rank", "player_name", "pri", "p_balls", "consistency", "median_rank_across_methods",
                "methods_with_top10", "seasons_above_baseline", "seasons_evaluated", "p_top10"]
        print(results[role]["final"].select(cols).to_pandas().to_string(index=False))
    print("\n" + "=" * 96)
    print(f"validation failures: {facts['validation']['fail']} (see validation.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
