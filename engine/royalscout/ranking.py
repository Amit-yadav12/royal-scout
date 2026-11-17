"""Leaderboards, eligibility, alternative rankings and robustness testing."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable

from .config import Config
from .stats import percentile_rank, spearman

BAT_ALT = ["rabi", "runs", "average", "strike_rate", "balls_faced", "boundary_pct", "dot_pct",
           "consistency", "pressure_score", "performance_score", "recent_form_score", "confidence_score"]
BOWL_ALT = ["rabi_bowl", "wickets", "economy", "average", "bowling_strike_rate", "dot_pct",
            "wickets_per_innings", "consistency", "pressure_score", "wicket_taking_score",
            "economy_containment_score", "recent_form_score", "confidence_score"]

LOWER_IS_BETTER = {"economy", "average", "bowling_strike_rate", "bowl_average", "dot_pct"}


def eligibility_bat(m: dict[str, Any], cfg: Config) -> tuple[bool, str]:
    e = cfg.eligibility
    balls = m.get("exposure_balls") or 0
    innings = m.get("innings") or 0
    if balls < e.bat_min_balls_ranked:
        return False, (f"batsman faced {balls} balls — below the ranked threshold of "
                       f"{e.bat_min_balls_ranked} balls")
    if innings < e.bat_min_innings_ranked:
        return False, (f"{innings} innings — below the ranked threshold of {e.bat_min_innings_ranked}")
    if m.get("rabi") is None:
        return False, "reliability-adjusted index could not be computed"
    return True, "meets ball and innings thresholds"


def eligibility_bowl(m: dict[str, Any], cfg: Config) -> tuple[bool, str]:
    e = cfg.eligibility
    balls = m.get("exposure_balls") or 0
    innings = m.get("innings") or 0
    if balls < e.bowl_min_balls_ranked:
        return False, (f"bowler delivered {balls} legal balls — below the ranked threshold of "
                       f"{e.bowl_min_balls_ranked}")
    if innings < e.bowl_min_innings_ranked:
        return False, f"{innings} innings — below the ranked threshold of {e.bowl_min_innings_ranked}"
    if m.get("rabi_bowl") is None:
        return False, "reliability-adjusted index could not be computed"
    return True, "meets workload and innings thresholds"


def attach_recent_form(scored: dict[str, dict[str, Any]], season_runs: dict[str, dict[str, float]],
                       season_balls: dict[str, dict[str, float]], discipline: str) -> None:
    """Recent form = output in the most recent season with meaningful exposure."""
    recent_sr: dict[str, float | None] = {}
    for pid in scored:
        runs = season_runs.get(pid) or {}
        balls = season_balls.get(pid) or {}
        usable = [(s, b) for s, b in balls.items() if b >= 30 and s not in {"unknown", "None"}]
        if not usable:
            recent_sr[pid] = None
            continue
        latest = sorted(usable, key=lambda x: str(x[0]))[-1][0]
        recent_sr[pid] = 100 * (runs.get(latest) or 0) / max(1.0, balls[latest])
    pct = percentile_rank(recent_sr)
    for pid in scored:
        scored[pid]["recent_form_score"] = None if pct.get(pid) is None else round(pct[pid], 2)
        scored[pid]["recent_season_strike_rate"] = None if recent_sr.get(pid) is None else round(recent_sr[pid], 2)


@dataclass
class Leaderboard:
    discipline: str
    rows: list[dict[str, Any]]
    eligible_count: int
    evaluated_count: int
    excluded: list[dict[str, Any]]
    alternative_ranks: dict[str, dict[str, int]]
    scope: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "discipline": self.discipline, "rows": self.rows,
            "eligible_count": self.eligible_count, "evaluated_count": self.evaluated_count,
            "excluded_count": len(self.excluded), "excluded_sample": self.excluded[:25],
            "alternative_ranks": self.alternative_ranks, "scope": self.scope,
        }


def _alt_ranks(scored: dict[str, dict[str, Any]], metrics: list[str]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for metric in metrics:
        vals = {}
        for pid, m in scored.items():
            v = m.get(metric)
            if v is None or isinstance(v, (dict, list, str)):
                continue
            vals[pid] = -v if metric in LOWER_IS_BETTER else v
        ordered = sorted(vals.items(), key=lambda kv: -kv[1])
        out[metric] = {pid: i + 1 for i, (pid, _) in enumerate(ordered)}
    return out


def build_leaderboard(scored: dict[str, dict[str, Any]], cfg: Config, discipline: str,
                      scope: dict[str, Any] | None = None, limit: int | None = None,
                      eligible_only: bool = True) -> Leaderboard:
    if discipline == "batting":
        elig_fn, key, alts = eligibility_bat, "rabi", BAT_ALT
    else:
        elig_fn, key, alts = eligibility_bowl, "rabi_bowl", BOWL_ALT
    rows: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for pid, m in scored.items():
        ok, reason = elig_fn(m, cfg)
        if not ok:
            excluded.append({"player": pid, "reason": reason,
                             "exposure": m.get("exposure_balls"),
                             "innings": m.get("innings")})
            if eligible_only:
                continue
        rows.append(m)
    rows.sort(key=lambda m: (-(m.get(key) if m.get(key) is not None else -1), -(m.get("exposure_balls") or 0)))
    alt = _alt_ranks({m["player"]: m for m in rows}, alts)
    if limit:
        rows = rows[:limit]
    for i, m in enumerate(rows, start=1):
        m["rank"] = i
        m["rank_metric"] = key
        m["eligibility_reason"] = elig_fn(m, cfg)[1]
    return Leaderboard(discipline=discipline, rows=rows, eligible_count=len(rows),
                       evaluated_count=len(scored), excluded=excluded,
                       alternative_ranks=alt, scope=scope or {"type": "global"})


# ---------------------------------------------------------------------------
# Ranking robustness / sensitivity analysis
# ---------------------------------------------------------------------------
def stability_variants(cfg: Config) -> list[tuple[str, Config]]:
    """Documented perturbations of the model. Each is a *testable assumption*."""
    variants: list[tuple[str, Config]] = [("baseline", cfg)]
    for k in (60, 120, 480, 960):
        variants.append((f"prior_k_{k}", replace(
            cfg, stats=replace(cfg.stats, prior_strength_balls_bat=float(k),
                               prior_strength_balls_bowl=float(k),
                               prior_strength_balls_econ=float(k)))))
    for delta in (-0.10, 0.10):
        b = cfg.batting_weights
        variants.append((f"bat_weights_pressure{'+' if delta > 0 else '-'}10", replace(cfg, batting_weights=replace(
            b, pressure=max(0.0, b.pressure + delta), performance=max(0.0, b.performance - delta)))))
        w = cfg.bowling_weights
        variants.append((f"bowl_weights_wickets{'+' if delta > 0 else '-'}10", replace(cfg, bowling_weights=replace(
            w, wicket_taking=max(0.0, w.wicket_taking + delta), economy=max(0.0, w.economy - delta)))))
    for min_balls in (80, 300):
        variants.append((f"min_balls_{min_balls}", replace(cfg, eligibility=replace(
            cfg.eligibility, bat_min_balls_ranked=min_balls, bowl_min_balls_ranked=min_balls))))
    return variants


def stability_analysis(rescore: Callable[[Config], dict[str, dict[str, Any]]], cfg: Config,
                       key: str, discipline: str) -> dict[str, Any]:
    base_scored = rescore(cfg)
    variants = stability_variants(cfg)
    variant_ranks: dict[str, dict[str, int]] = {}
    summary: list[dict[str, Any]] = []
    base_rank = _rank_map(base_scored, key, cfg, discipline)
    for name, vcfg in variants:
        scored = base_scored if name == "baseline" else rescore(vcfg)
        ranks = _rank_map(scored, key, vcfg, discipline)
        variant_ranks[name] = ranks
        rho = spearman({k: -v for k, v in base_rank.items()}, {k: -v for k, v in ranks.items()})
        top_a = {k for k, v in base_rank.items() if v <= 30}
        top_b = {k for k, v in ranks.items() if v <= 30}
        summary.append({
            "variant": name, "spearman_vs_baseline": None if rho is None else round(rho, 4),
            "top30_overlap": len(top_a & top_b),
            "top30_changes": len(top_a ^ top_b),
            "players_ranked": len(ranks),
            "config_delta": _config_delta(name),
        })
    # per-player stability
    players = sorted(set(base_rank) | {p for r in variant_ranks.values() for p in r})
    per_player = []
    for p in players:
        ranks = [r[p] for r in variant_ranks.values() if p in r]
        if not ranks:
            continue
        spread = max(ranks) - min(ranks)
        per_player.append({
            "player": p,
            "baseline_rank": base_rank.get(p),
            "min_rank": min(ranks), "max_rank": max(ranks), "rank_spread": spread,
            "stability_score": round(max(0.0, 100 - spread * 2.0), 2),
            "assessments": len(ranks),
        })
    per_player.sort(key=lambda d: (d["baseline_rank"] or 9999))
    rho_values = [s["spearman_vs_baseline"] for s in summary if s["spearman_vs_baseline"] is not None]
    return {
        "discipline": discipline,
        "variants": summary,
        "per_player": per_player,
        "mean_spearman": round(sum(rho_values) / len(rho_values), 4) if rho_values else None,
        "min_spearman": round(min(rho_values), 4) if rho_values else None,
        "interpretation": _stability_interpretation(rho_values, discipline),
    }


def _config_delta(name: str) -> str:
    table = {
        "baseline": "reference configuration",
        "prior_k_60": "shrinkage prior k=60 balls (trusts short samples more)",
        "prior_k_120": "shrinkage prior k=120 balls",
        "prior_k_480": "shrinkage prior k=480 balls",
        "prior_k_960": "shrinkage prior k=960 balls (strongly distrusts short samples)",
        "bat_weights_pressure+10": "batting composite: +10pp weight on pressure",
        "bat_weights_pressure-10": "batting composite: -10pp weight on pressure",
        "bowl_weights_wickets+10": "bowling composite: +10pp weight on wickets",
        "bowl_weights_wickets-10": "bowling composite: -10pp weight on wickets",
        "min_balls_80": "ranked eligibility floor lowered to 80 balls",
        "min_balls_300": "ranked eligibility floor raised to 300 balls",
    }
    return table.get(name, name)


def _stability_interpretation(rhos: list[float], discipline: str) -> str:
    if not rhos:
        return "Not enough players for a rank-correlation test."
    mn, mean = min(rhos), sum(rhos) / len(rhos)
    if mean >= 0.9 and mn >= 0.8:
        verdict = ("Rankings are robust: every tested assumption change preserves the ordering "
                   "(mean Spearman >= 0.90, worst >= 0.80).")
    elif mean >= 0.75:
        verdict = ("Rankings are moderately robust. Some players move materially under alternative "
                   "assumptions — consult the per-player rank spread before acting on the ranking.")
    else:
        verdict = ("Rankings are sensitive to methodology. The ordering should not be treated as "
                   "settled; the data or the weights do not pin the ranking down.")
    return f"{verdict} Across {len(rhos)} alternative {discipline} configurations."


def _rank_map(scored: dict[str, dict[str, Any]], key: str, cfg: Config, discipline: str) -> dict[str, int]:
    fn = eligibility_bat if discipline == "batting" else eligibility_bowl
    vals = [(pid, m.get(key)) for pid, m in scored.items() if fn(m, cfg)[0] and m.get(key) is not None]
    vals.sort(key=lambda kv: (-kv[1], -(scored[kv[0]].get("exposure_balls") or 0)))
    return {pid: i + 1 for i, (pid, _) in enumerate(vals)}


# ---------------------------------------------------------------------------
# Scope generation for precomputed filtering
# ---------------------------------------------------------------------------
def candidate_scopes(bat_records: list[dict[str, Any]], bowl_records: list[dict[str, Any]],
                     max_scopes: int = 160) -> list[dict[str, Any]]:
    """Single-dimension scopes plus competition x season pairs, capped."""
    comps, seasons, teams = set(), set(), set()
    for r in bat_records + bowl_records:
        if r.get("competition"):
            comps.add(str(r["competition"]).strip())
        if r.get("season"):
            seasons.add(str(r["season"]).strip())
        if r.get("team"):
            teams.add(str(r["team"]).strip())
    scopes: list[dict[str, Any]] = [{"type": "global", "label": "All data", "filter": {}}]
    # Keep precomputation strictly bounded; do not let a large number of teams
    # or competition-season combinations multiply analysis cost without limit.
    for values, make in (
        (sorted(comps), lambda v: {"type": "competition", "label": v,
                                   "filter": {"competition": [v]}}),
        (sorted(seasons), lambda v: {"type": "season", "label": v,
                                     "filter": {"season": [v]}}),
        (sorted(teams), lambda v: {"type": "team", "label": v,
                                   "filter": {"team": [v]}}),
    ):
        for value in values:
            if len(scopes) >= max_scopes:
                break
            scopes.append(make(value))
    budget = max_scopes - len(scopes)
    pairs = [(c, s) for c in sorted(comps) for s in sorted(seasons)]
    for c, s in pairs[:max(0, budget)]:
        scopes.append({"type": "competition_season", "label": f"{c} · {s}",
                       "filter": {"competition": [c], "season": [s]}})
    return scopes
