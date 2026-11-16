#!/usr/bin/env python3
"""Trim a full analytical bundle down to what the dashboard renders.

The full bundle carries per-player splits for every player in the pack (18 MB for
the real season). The Next.js app imports the bundle statically, so the published
copy keeps: all leaderboards and scopes (top rows), player detail for the ranked
players, pressure entries for those players, and the schema/quality provenance.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

KEEP_ROWS = 30
KEEP_PLAYERS = 140
KEEP_SCOPE_ROWS = 15


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", default="../web/src/data/bundle_real.json")
    ap.add_argument("--out", default="../web/src/data/bundle_live.json")
    args = ap.parse_args()
    b = json.loads(Path(args.bundle).read_text())

    lb = b["leaderboards"]
    lb["global"]["batters"] = lb["global"]["batters"][:KEEP_ROWS]
    lb["global"]["bowlers"] = lb["global"]["bowlers"][:KEEP_ROWS]
    for s in lb["scopes"]:
        s["batters"] = s["batters"][:KEEP_SCOPE_ROWS]
        s["bowlers"] = s["bowlers"][:KEEP_SCOPE_ROWS]

    keep = {r["player"] for r in lb["global"]["batters"] + lb["global"]["bowlers"]}
    for s in lb["scopes"]:
        keep.update(r["player"] for r in s["batters"] + s["bowlers"])
    ordered = list(keep)[:KEEP_PLAYERS]
    keep = set(ordered)

    for key in ("batting", "bowling"):
        players = b[key].get("players", {})
        b[key]["players"] = {n: v for n, v in players.items() if n in keep}
        # splits are keyed "player|season" (or similar) — keep only ranked players
        splits = b[key].get("splits")
        if isinstance(splits, dict):
            for split_name, rows in splits.items():
                if isinstance(rows, dict):
                    splits[split_name] = {k: v for k, v in rows.items() if str(k).split("|")[0] in keep}
    for key in ("batting", "bowling", "ppi_batting", "ppi_bowling"):
        d = b["pressure"].get(key)
        if isinstance(d, dict):
            b["pressure"][key] = {n: v for n, v in d.items() if n in keep}
    b["roles"] = {n: v for n, v in b["roles"].items() if n in keep}

    b["meta"]["published_slim"] = True
    out = Path(args.out)
    out.write_text(json.dumps(b, default=str))
    print(f"{out}: {out.stat().st_size/1e6:.2f} MB "
          f"({len(b['batting']['players'])} batting / {len(b['bowling']['players'])} bowling profiles, "
          f"{len(lb['scopes'])} scopes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
