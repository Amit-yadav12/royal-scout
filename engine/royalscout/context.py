"""Opposition / competition strength adjustment.

A first-order ratio adjustment, stated plainly: if a batter's opposition
conceded runs at 1.15x the population rate, that batter's strike rate is deflated
by that factor before being compared with peers. This is not a full
Bradley-Terry or Elo model, so the basis is always published and the component is
dropped when opposition information is missing.
"""
from __future__ import annotations

from typing import Any

from .stats import percentile_rank

BASIS = "first_order_ratio_adjustment"


def team_strength(records: list[dict[str, Any]], value_key: str, exposure_key: str,
                  higher_index_means_stronger: bool) -> tuple[dict[str, float], float | None]:
    agg: dict[str, list[float]] = {}
    total_v = total_e = 0.0
    for r in records:
        team = r.get("team")
        v, e = r.get(value_key), r.get(exposure_key)
        if not team or v is None or not e:
            continue
        a = agg.setdefault(str(team).strip(), [0.0, 0.0])
        a[0] += float(v)
        a[1] += float(e)
        total_v += float(v)
        total_e += float(e)
    if not agg or not total_e:
        return {}, None
    population = total_v / total_e
    if population == 0:
        return {}, None
    index: dict[str, float] = {}
    for team, (v, e) in agg.items():
        if e <= 0:
            continue
        ratio = (v / e) / population
        index[team] = ratio if higher_index_means_stronger else 1.0 / ratio if ratio else 1.0
    return index, population


def opposition_adjusted(bat_records: list[dict[str, Any]], bowl_records: list[dict[str, Any]],
                        scored_bat: dict[str, dict[str, Any]],
                        scored_bowl: dict[str, dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    """Return {"batting": {player: {...}}, "bowling": {player: {...}}}."""
    # Bowling strength of a team = runs conceded per ball (higher = weaker attack)
    bowl_strength, bowl_pop = team_strength(bowl_records, "runs_conceded", "legal_balls",
                                            higher_index_means_stronger=True)
    bat_strength, bat_pop = team_strength(bat_records, "runs", "balls_faced",
                                          higher_index_means_stronger=True)

    out: dict[str, dict[str, dict[str, Any]]] = {"batting": {}, "bowling": {}}

    # ---- batters: adjust SR for the strength of the attacks they faced ----
    adj_sr: dict[str, float | None] = {}
    detail: dict[str, dict[str, Any]] = {}
    for pid, m in scored_bat.items():
        if not bowl_strength:
            break
        recs = [r for r in bat_records if r.get("player") == pid and r.get("opposition")
                and (r.get("balls_faced") or 0) > 0]
        if not recs:
            adj_sr[pid] = None
            detail[pid] = {"reason": "no opposition information on this player's records"}
            continue
        wsum = sum(r["balls_faced"] for r in recs)
        weighted = sum(bowl_strength.get(str(r["opposition"]).strip(), 1.0) * r["balls_faced"]
                       for r in recs) / max(1, wsum)
        sr = m.get("strike_rate")
        if sr is None or weighted <= 0:
            adj_sr[pid] = None
            detail[pid] = {"reason": "strike rate unavailable for this player"}
            continue
        adj_sr[pid] = sr / weighted
        detail[pid] = {
            "observed_strike_rate": sr, "adjusted_strike_rate": round(sr / weighted, 2),
            "opposition_bowling_strength_index": round(weighted, 3),
            "opposition_balls_covered": wsum,
            "interpretation": ("Opposition attacks faced were, on a runs-conceded basis, "
                               f"{'stronger' if weighted < 1 else 'weaker' if weighted > 1 else 'average'} "
                               "than the population average (index < 1 = better attack)."),
            "basis": BASIS,
        }
    pct = percentile_rank(adj_sr, higher_is_better=True)
    for pid, v in adj_sr.items():
        out["batting"][pid] = {
            "score": None if pct.get(pid) is None else round(pct[pid], 2),
            "adjusted_strike_rate": None if v is None else round(v, 2),
            "basis": BASIS,
            "coverage": 1.0 if v is not None else 0.0,
            "detail": detail.get(pid, {}),
        }

    # ---- bowlers: adjust economy for the strength of the batting faced ----
    adj_econ: dict[str, float | None] = {}
    detail_b: dict[str, dict[str, Any]] = {}
    for pid, m in scored_bowl.items():
        if not bat_strength:
            break
        recs = [r for r in bowl_records if r.get("player") == pid and r.get("opposition")
                and (r.get("legal_balls") or 0) > 0]
        if not recs:
            adj_econ[pid] = None
            detail_b[pid] = {"reason": "no opposition information on this player's records"}
            continue
        wsum = sum(r["legal_balls"] for r in recs)
        weighted = sum(bat_strength.get(str(r["opposition"]).strip(), 1.0) * r["legal_balls"]
                       for r in recs) / max(1, wsum)
        econ = m.get("economy")
        if econ is None or weighted <= 0:
            adj_econ[pid] = None
            detail_b[pid] = {"reason": "economy unavailable for this player"}
            continue
        adj_econ[pid] = econ / weighted
        detail_b[pid] = {
            "observed_economy": econ, "adjusted_economy": round(econ / weighted, 2),
            "opposition_batting_strength_index": round(weighted, 3),
            "opposition_balls_covered": wsum,
            "basis": BASIS,
        }
    pct_b = percentile_rank(adj_econ, higher_is_better=False)
    for pid, v in adj_econ.items():
        out["bowling"][pid] = {
            "score": None if pct_b.get(pid) is None else round(pct_b[pid], 2),
            "adjusted_economy": None if v is None else round(v, 2),
            "basis": BASIS,
            "coverage": 1.0 if v is not None else 0.0,
            "detail": detail_b.get(pid, {}),
        }
    return out
