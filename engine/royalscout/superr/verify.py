"""Independent recomputation.

The point of this module is to disagree with the pipeline. Aggregates are
re-derived with a deliberately naive row-by-row loop over the raw CSV and
compared with the vectorised panel output; conservation identities (runs in =
runs out, dismissals in = dismissals out) are checked across the whole file.

If these fail, nothing downstream can be trusted.
"""
from __future__ import annotations

import csv
from pathlib import Path

import polars as pl

from .validate import Check, _c


def _naive_pass(csv_path: Path) -> dict:
    """Single pass over the raw CSV with no framework help at all."""
    total_runs = 0
    bat_runs = 0
    extra_runs = 0
    legal = 0
    dismissals = 0
    rows = 0
    per_player: dict[int, dict[str, int]] = {}
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            rows += 1
            runs = int(row["runs"] or 0)
            e1 = int(row["extras1_runs"] or 0)
            e2 = int(row["extras_2_runs"] or 0)
            et = (row["extras_type"] or "None")
            bat_runs += runs
            extra_runs += e1 + e2
            total_runs += runs + e1 + e2
            if et not in ("wide", "Overstep", "other", "Penalty"):
                legal += 1
            if (row["is_wicket"] or "").lower() == "true":
                dismissals += 1
            pid = int(row["striker_id"])
            d = per_player.setdefault(pid, {"bat_runs": 0, "balls": 0, "outs": 0})
            if et not in ("wide", "Penalty"):
                d["balls"] += 1
            d["bat_runs"] += runs
            if (row["is_wicket"] or "").lower() == "true" and int(row["dismissed_player_id"] or -1) == pid:
                d["outs"] += 1
    return {"rows": rows, "total_runs": total_runs, "bat_runs": bat_runs, "extra_runs": extra_runs,
            "legal": legal, "dismissals": dismissals, "per_player": per_player}


def run(pack, ball: pl.DataFrame, raw_dir: Path, sample_players: list[int] | None = None) -> list[Check]:
    checks: list[Check] = []
    naive = _naive_pass(Path(raw_dir) / "ball_by_ball.csv")

    checks.append(_c("row_count", "Loaded row count equals the raw file's data rows",
                     "critical", naive["rows"] == ball.height,
                     f"raw={naive['rows']} loaded={ball.height}",
                     {"raw": naive["rows"], "loaded": ball.height}))

    checks.append(_c("run_total", "Total runs recomputed row-by-row equals the pipeline's total",
                     "critical", naive["total_runs"] == int(ball["total_runs"].sum()),
                     f"naive={naive['total_runs']} pipeline={int(ball['total_runs'].sum())}",
                     {"naive": naive["total_runs"], "pipeline": int(ball["total_runs"].sum())}))

    checks.append(_c("run_conservation",
                     "Bat runs + extras equal total runs (no run is double counted or lost)",
                     "critical", naive["bat_runs"] + naive["extra_runs"] == naive["total_runs"],
                     f"bat={naive['bat_runs']} extras={naive['extra_runs']} total={naive['total_runs']}",
                     {"bat": naive["bat_runs"], "extras": naive["extra_runs"], "total": naive["total_runs"]}))

    checks.append(_c("legal_ball_count", "Legal deliveries recomputed row-by-row match",
                     "high", naive["legal"] == int(ball["_legal_i"].sum()),
                     f"naive={naive['legal']} pipeline={int(ball['_legal_i'].sum())}",
                     {"naive": naive["legal"], "pipeline": int(ball["_legal_i"].sum())}))

    checks.append(_c("dismissal_conservation",
                     "Dismissals credited to bowlers plus non-bowler dismissals equal all wickets",
                     "high",
                     int(ball["bowler_wicket"].sum()) + int((ball["is_wicket"] & ~ball["bowler_wicket"]).sum())
                     == int(ball["is_wicket"].sum()),
                     f"bowler={int(ball['bowler_wicket'].sum())} "
                     f"other={int((ball['is_wicket'] & ~ball['bowler_wicket']).sum())} "
                     f"total={int(ball['is_wicket'].sum())}",
                     {"bowler": int(ball["bowler_wicket"].sum()),
                      "total": int(ball["is_wicket"].sum())}))

    # per-player agreement on a sample of players
    if sample_players:
        b = ball.filter(pl.col("striker_id").is_in(sample_players))
        agg = b.group_by("striker_id").agg(
            pl.col("bat_runs").sum().alias("bat_runs"),
            pl.when(~pl.col("extras_type").is_in(["wide", "Penalty"])).then(1).otherwise(0).sum().alias("balls"),
        )
        mismatches = []
        for r in agg.to_dicts():
            n = naive["per_player"][int(r["striker_id"])]
            if int(r["bat_runs"]) != n["bat_runs"] or int(r["balls"]) != n["balls"]:
                mismatches.append({"player_id": r["striker_id"], "pipeline": r, "naive": n})
        checks.append(_c("player_aggregate_agreement",
                         "Per-player bat runs and balls reproduce for the sampled players",
                         "critical", not mismatches,
                         f"{len(sample_players)} players sampled, {len(mismatches)} mismatched",
                         {"sampled": len(sample_players), "mismatches": len(mismatches)}, mismatches[:5]))
    return checks
