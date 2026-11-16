"""Batting intelligence engine.

Two phases, deliberately separated:

1. ``compute_batting_raw`` – additive counting stats from canonical records.
2. ``score_batting_population`` – population-relative scores, shrinkage,
   confidence grading and the composite Reliability-Adjusted Batting Index.

Anything that cannot be computed from the available data returns ``None`` plus a
reason in ``unavailable``. Nothing is imputed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np

from .canonical import GRANULARITY_AGGREGATE, GRANULARITY_INNINGS
from .config import Config
from .stats import (Confidence, bootstrap_ci, composite, confidence_grade,
                    consistency_from_cv, coefficient_of_variation, percentile_rank, shrink)


def _f(x: Any) -> float | None:
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if v != v else v


@dataclass
class BattingRaw:
    player: str
    teams: set[str] = field(default_factory=set)
    competitions: set[str] = field(default_factory=set)
    seasons: set[str] = field(default_factory=set)
    venues: set[str] = field(default_factory=set)
    oppositions: set[str] = field(default_factory=set)
    records: int = 0
    innings: int = 0
    matches: int | None = None
    match_ids: set[str] = field(default_factory=set)
    runs: int = 0
    balls: int = 0
    fours: int = 0
    sixes: int = 0
    dots: int | None = 0
    not_outs: int = 0
    dismissals: int = 0
    dismissals_missing: int = 0
    balls_missing: int = 0
    highest: int | None = None
    scores: list[int] = field(default_factory=list)       # innings-level scores (if available)
    aggregate_values: list[int] = field(default_factory=list)
    granularity: str = GRANULARITY_AGGREGATE
    season_runs: dict[str, int] = field(default_factory=dict)
    season_balls: dict[str, int] = field(default_factory=dict)
    derived_exposure: int = 0
    unavailable: dict[str, str] = field(default_factory=dict)

    # derived
    def finalise(self) -> "BattingRaw":
        if self.balls_missing:
            self.unavailable["balls_faced"] = f"{self.balls_missing} record(s) had no recoverable balls faced"
        if self.dismissals_missing:
            self.unavailable["batting_average"] = (
                f"{self.dismissals_missing} record(s) had no recoverable dismissal/not-out information")
        if not self.scores:
            self.unavailable["innings_distribution"] = (
                "only multi-innings aggregates are present, so no innings-level distribution exists")
        return self

    @property
    def balls_known(self) -> bool:
        return self.balls_missing == 0 and self.balls > 0

    @property
    def dismissals_known(self) -> bool:
        return self.dismissals_missing == 0 and self.dismissals > 0

    @property
    def average(self) -> float | None:
        if not self.dismissals_known:
            return None
        return self.runs / self.dismissals

    @property
    def strike_rate(self) -> float | None:
        if not self.balls_known:
            return None
        return 100.0 * self.runs / self.balls

    @property
    def rpi(self) -> float | None:
        return self.runs / self.innings if self.innings else None

    @property
    def boundary_runs(self) -> int:
        return 4 * self.fours + 6 * self.sixes

    @property
    def boundary_pct(self) -> float | None:
        if not self.runs:
            return None
        return 100.0 * self.boundary_runs / self.runs


def compute_batting_raw(records: Iterable[dict[str, Any]]) -> dict[str, BattingRaw]:
    players: dict[str, BattingRaw] = {}
    for r in records:
        p = r.get("player")
        if not p:
            continue
        b = players.get(p)
        if b is None:
            b = players[p] = BattingRaw(player=p)
        b.records += 1
        if r.get("match_id"):
            b.match_ids.add(str(r["match_id"]))
        gran = r.get("granularity") or GRANULARITY_INNINGS
        innings = int(r.get("innings_count") or 1)
        b.innings += innings
        b.runs += int(r.get("runs") or 0)
        if r.get("balls_faced") is None:
            b.balls_missing += 1
        else:
            b.balls += int(r["balls_faced"])
        b.fours += int(r.get("fours") or 0)
        b.sixes += int(r.get("sixes") or 0)
        if r.get("dot_balls_faced") is not None:
            b.dots = (b.dots or 0) + int(r["dot_balls_faced"])
        else:
            b.dots = None
        if r.get("not_outs") is None:
            b.not_outs += 0
        else:
            b.not_outs += int(r["not_outs"])
        if r.get("dismissals") is None:
            b.dismissals_missing += 1
        else:
            b.dismissals += int(r["dismissals"])
        for key, attr in (("team", "teams"), ("competition", "competitions"),
                          ("season", "seasons"), ("venue", "venues"), ("opposition", "oppositions")):
            v = r.get(key)
            if v:
                getattr(b, attr).add(str(v).strip())
        if gran == GRANULARITY_INNINGS:
            b.granularity = GRANULARITY_INNINGS
            b.scores.append(int(r.get("runs") or 0))
        else:
            b.aggregate_values.append(int(r.get("runs") or 0))
        hs = r.get("highest_score") if gran == GRANULARITY_AGGREGATE else r.get("runs")
        if hs is not None:
            b.highest = max(b.highest or 0, int(hs))
        if r.get("derived_balls"):
            b.derived_exposure += 1
        season = str(r.get("season") or "unknown")
        b.season_runs[season] = b.season_runs.get(season, 0) + int(r.get("runs") or 0)
        b.season_balls[season] = b.season_balls.get(season, 0) + int(r.get("balls_faced") or 0)
    for b in players.values():
        if b.granularity == GRANULARITY_AGGREGATE and b.aggregate_values:
            b.scores = []
        if b.match_ids:
            b.matches = len(b.match_ids)
        b.finalise()
    return players


# ---------------------------------------------------------------------------
# Population baselines
# ---------------------------------------------------------------------------
@dataclass
class BattingBaseline:
    strike_rate: float
    average: float
    boundary_pct: float
    rpi: float
    population: int
    runs: int
    balls: int
    dismissals: int


def batting_baseline(players: dict[str, BattingRaw]) -> BattingBaseline:
    runs = sum(p.runs for p in players.values())
    balls = sum(p.balls for p in players.values())
    dismissals = sum(p.dismissals for p in players.values())
    innings = sum(p.innings for p in players.values())
    boundary = sum(p.boundary_runs for p in players.values())
    return BattingBaseline(
        strike_rate=(100 * runs / balls) if balls else 120.0,
        average=(runs / dismissals) if dismissals else 25.0,
        boundary_pct=(100 * boundary / runs) if runs else 50.0,
        rpi=(runs / innings) if innings else 20.0,
        population=len(players), runs=runs, balls=balls, dismissals=dismissals)


# ---------------------------------------------------------------------------
# Population scoring
# ---------------------------------------------------------------------------
def score_batting_population(raw: dict[str, BattingRaw], cfg: Config,
                             pressure: dict[str, dict[str, Any]] | None = None,
                             roles: dict[str, dict[str, Any]] | None = None
                             ) -> dict[str, dict[str, Any]]:
    base = batting_baseline(raw)
    st = cfg.stats
    ids = sorted(raw)

    sr_shrunk: dict[str, float | None] = {}
    avg_shrunk: dict[str, float | None] = {}
    bnd_shrunk: dict[str, float | None] = {}
    rpi_shrunk: dict[str, float | None] = {}
    cons_raw: dict[str, float | None] = {}
    cons_basis: dict[str, str] = {}

    for pid in ids:
        p = raw[pid]
        sr_shrunk[pid] = shrink(p.strike_rate, p.balls if p.balls_known else None,
                                st.prior_strength_balls_bat, base.strike_rate)
        avg_shrunk[pid] = shrink(p.average, p.dismissals if p.dismissals_known else None,
                                 st.prior_strength_dismissals_bat, base.average)
        bnd_shrunk[pid] = shrink(p.boundary_pct, p.balls if p.balls_known else None,
                                 st.prior_strength_balls_bat, base.boundary_pct)
        rpi_shrunk[pid] = shrink(p.rpi, p.innings if p.innings else None,
                                 max(2.0, st.prior_strength_dismissals_bat), base.rpi)
        if p.scores and len(p.scores) >= 2:
            cv = coefficient_of_variation(p.scores)
            cons_raw[pid] = consistency_from_cv(cv)
            cons_basis[pid] = "innings_distribution"
        elif len(p.aggregate_values) >= 2:
            cv = coefficient_of_variation(p.aggregate_values)
            cons_raw[pid] = consistency_from_cv(cv)
            cons_basis[pid] = "aggregate_dispersion"
        else:
            cons_raw[pid] = None
            cons_basis[pid] = "unavailable: fewer than two observations"

    pct = lambda d: percentile_rank(d, True)  # noqa: E731
    P_sr, P_avg, P_bnd, P_rpi, P_cons = pct(sr_shrunk), pct(avg_shrunk), pct(bnd_shrunk), pct(rpi_shrunk), pct(cons_raw)

    # role-group percentile for role-adjusted score
    role_groups: dict[str, list[str]] = {}
    if roles:
        for pid in ids:
            role_groups.setdefault(str(roles.get(pid, {}).get("primary_role", "unknown")), []).append(pid)

    out: dict[str, dict[str, Any]] = {}
    for pid in ids:
        p = raw[pid]
        pw = {"strike_rate": P_sr.get(pid), "average": P_avg.get(pid),
              "boundary_pct": P_bnd.get(pid), "runs_per_innings": P_rpi.get(pid)}
        inner_w = {"strike_rate": 0.40, "average": 0.35, "boundary_pct": 0.15, "runs_per_innings": 0.10}
        performance, perf_cov, perf_applied = composite(pw, inner_w)

        # ---- consistency ----
        consistency = None
        consistency_detail: dict[str, Any] = {"basis": cons_basis[pid]}
        if P_cons.get(pid) is not None:
            failure_rate = None
            if p.scores:
                mean = float(np.mean(p.scores))
                failure_rate = sum(1 for s in p.scores if s < 0.5 * mean) / len(p.scores)
            # Blend the population percentile with the absolute dispersion measure so a
            # player is not pushed to a hard 100 purely by the percentile transform, then
            # apply a bounded failure-rate adjustment (-10 .. +10).
            rel_cons = cons_raw.get(pid) or 0.0
            bonus = 0.0 if failure_rate is None else (0.5 - failure_rate) * 20
            consistency = max(0.0, min(100.0, (P_cons[pid] or 0) * 0.80 + rel_cons * 0.20 + bonus))
            cv = coefficient_of_variation(p.scores or p.aggregate_values)
            consistency_detail.update({
                "cv": None if cv is None else round(cv, 3),
                "relative_consistency": None if cv is None else round(consistency_from_cv(cv), 1),
                "failure_rate": None if failure_rate is None else round(failure_rate, 3),
                "observations": len(p.scores or p.aggregate_values),
                "warning": ("computed across season aggregates — this is NOT match-level consistency"
                            if cons_basis[pid] == "aggregate_dispersion" else None),
            })
        else:
            consistency_detail["reason"] = cons_basis[pid]

        # ---- confidence ----
        ci_lo, ci_hi = bootstrap_ci(p.scores, lambda s: float(np.mean(s)), st) if p.scores else (None, None)
        rel_ci = None
        if ci_lo is not None and ci_hi is not None:
            mean = float(np.mean(p.scores)) if p.scores else 0
            rel_ci = (ci_hi - ci_lo) / max(1.0, mean)
        coverage_so_far = perf_cov
        conf: Confidence = confidence_grade(
            exposure=float(p.balls), coverage=coverage_so_far, ci_width=rel_ci, cfg=st,
            exposure_name="balls faced")

        # ---- pressure ----
        pressure_component = None
        pressure_detail: dict[str, Any] = {"status": "unavailable",
                                           "reason": "no ball-by-ball or innings-split data was supplied"}
        if pressure and pid in pressure:
            pr = pressure[pid]
            pressure_component = pr.get("score")
            pressure_detail = pr.get("detail", {"status": pr.get("basis", "unknown")})

        # ---- role adjusted ----
        role_adj = None
        role_detail: dict[str, Any] = {}
        role = str((roles or {}).get(pid, {}).get("primary_role", "unknown"))
        group = role_groups.get(role, [])
        if len(group) >= cfg.stats.min_baseline_group and performance is not None:
            gvals = [composite({"strike_rate": P_sr.get(g), "average": P_avg.get(g),
                                "boundary_pct": P_bnd.get(g),
                                "runs_per_innings": P_rpi.get(g)}, inner_w)[0]
                     for g in group]
            gvals = [v for v in gvals if v is not None]
            if len(gvals) >= cfg.stats.min_baseline_group:
                role_adj = float(sum(1 for v in gvals if v <= performance) / len(gvals) * 100)
                role_detail = {"role": role, "peer_group_size": len(gvals),
                               "benchmark": "percentile of this player's performance score within their role group"}
        if role_adj is None:
            role_detail = {"role": role, "reason": "role peer group smaller than "
                                                   f"{cfg.stats.min_baseline_group} players"}

        # ---- reliability ----
        season_stability = None
        seasons_with_data = [(s, b) for s, b in p.season_balls.items() if b >= 30]
        if len(seasons_with_data) >= 2:
            srs = [100 * p.season_runs[s] / b for s, b in seasons_with_data]
            cv = coefficient_of_variation(srs)
            season_stability = consistency_from_cv(cv)
        rel_parts = {"consistency": consistency, "confidence": conf.score,
                     "cross_season_stability": season_stability}
        reliability, rel_cov, _ = composite(rel_parts, {"consistency": 0.45, "confidence": 0.30,
                                                        "cross_season_stability": 0.25})

        components = {
            "performance": performance, "consistency": consistency, "reliability": reliability,
            "pressure": pressure_component, "role_adjusted": role_adj, "confidence": conf.score,
        }
        weights = {"performance": cfg.batting_weights.performance, "consistency": cfg.batting_weights.consistency,
                   "reliability": cfg.batting_weights.reliability, "pressure": cfg.batting_weights.pressure,
                   "role_adjusted": cfg.batting_weights.role_adjusted,
                   "confidence": cfg.batting_weights.confidence}
        rabi, coverage, applied = composite(components, weights)

        # re-grade with the *final* coverage (pressure availability matters)
        final_conf = confidence_grade(p.balls, coverage, rel_ci, st, "balls faced")

        out[pid] = {
            "player": pid,
            "teams": sorted(p.teams), "competitions": sorted(p.competitions), "seasons": sorted(p.seasons),
            "venues": sorted(p.venues), "oppositions": sorted(p.oppositions),
            "records": p.records, "innings": p.innings, "matches": p.matches,
            "runs": p.runs, "balls_faced": p.balls, "fours": p.fours, "sixes": p.sixes,
            "boundary_runs": p.boundary_runs, "boundary_pct": _r(p.boundary_pct),
            "four_pct": _r(100 * 4 * p.fours / p.runs) if p.runs else None,
            "six_pct": _r(100 * 6 * p.sixes / p.runs) if p.runs else None,
            "dot_balls": p.dots,
            "dot_pct": _r(100 * p.dots / p.balls) if (p.dots is not None and p.balls) else None,
            "not_outs": p.not_outs, "dismissals": p.dismissals if p.dismissals_known else None,
            "average": _r(p.average), "strike_rate": _r(p.strike_rate), "runs_per_innings": _r(p.rpi),
            "highest_score": p.highest,
            "balls_per_boundary": _r(p.balls / (p.fours + p.sixes)) if (p.fours + p.sixes) else None,
            "balls_per_dismissal": _r(p.balls / p.dismissals) if p.dismissals else None,
            "scores_30": sum(1 for s in p.scores if s >= 30) if p.scores else None,
            "scores_50": sum(1 for s in p.scores if s >= 50) if p.scores else None,
            "scores_100": sum(1 for s in p.scores if s >= 100) if p.scores else None,
            "ducks": sum(1 for s in p.scores if s == 0) if p.scores else None,
            "dismissal_pct": _r(100 * p.dismissals / p.innings) if (p.innings and p.dismissals_known) else None,
            "consistency": _r(consistency), "consistency_detail": consistency_detail,
            "performance_score": _r(performance), "performance_coverage": round(perf_cov, 3),
            "performance_components": {k: _r(v) for k, v in pw.items()},
            "reliability": _r(reliability), "reliability_coverage": round(rel_cov, 3),
            "pressure_score": _r(pressure_component), "pressure_detail": pressure_detail,
            "role_adjusted_score": _r(role_adj), "role_detail": role_detail,
            "confidence": final_conf.to_dict(),
            "confidence_score": final_conf.score, "grade": final_conf.grade,
            "rabi": _r(rabi), "score_coverage": round(coverage, 3),
            "component_weights_applied": {k: round(v, 4) for k, v in applied.items()},
            "exposure_balls": p.balls, "granularity": p.granularity,
            "derived_exposure_records": p.derived_exposure,
            "unavailable": p.unavailable,
            "method": {
                "shrinkage": {
                    "k_balls": st.prior_strength_balls_bat,
                    "k_dismissals": st.prior_strength_dismissals_bat,
                    "baseline_sr": round(base.strike_rate, 2),
                    "baseline_average": round(base.average, 2),
                    "baseline_boundary_pct": round(base.boundary_pct, 2),
                    "shrink_weight": round(p.balls / (p.balls + st.prior_strength_balls_bat), 3)
                    if p.balls else 0.0,
                },
                "shrunk_values": {
                    "strike_rate": _r(sr_shrunk[pid]), "average": _r(avg_shrunk[pid]),
                    "boundary_pct": _r(bnd_shrunk[pid]), "runs_per_innings": _r(rpi_shrunk[pid]),
                },
            },
        }
    return out


def _r(v: float | None, nd: int = 2) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:
        return None
    return round(f, nd)


# ---------------------------------------------------------------------------
# Phase / situational splits (from records, when innings-level data allows)
# ---------------------------------------------------------------------------
def batting_situational_splits(records: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    """Splits by innings number, season, opposition, venue — record-level only.

    Phase splits (powerplay/middle/death) require ball-by-ball data and are
    produced by ``pressure.py`` instead; they are NOT approximated here.
    """
    out: dict[str, dict[str, dict[str, Any]]] = {
        "by_season": {}, "by_opposition": {}, "by_venue": {}, "by_innings_number": {},
    }
    def ensure(group: str, key: str) -> dict[str, Any]:
        d = out[group].setdefault(key, {"runs": 0, "balls": 0, "innings": 0, "dismissals": 0,
                                        "not_outs": 0, "fours": 0, "sixes": 0})
        return d

    for r in records:
        p = r.get("player")
        if not p:
            continue
        for group, key in (("by_season", r.get("season")), ("by_opposition", r.get("opposition")),
                           ("by_venue", r.get("venue")),
                           ("by_innings_number", (str(r["innings_number"]) if r.get("innings_number") else None))):
            if key is None:
                continue
            d = ensure(group, f"{p}|{key}")
            d["runs"] += int(r.get("runs") or 0)
            d["balls"] += int(r.get("balls_faced") or 0)
            d["innings"] += int(r.get("innings_count") or 1)
            d["dismissals"] += int(r.get("dismissals") or 0)
            d["not_outs"] += int(r.get("not_outs") or 0)
            d["fours"] += int(r.get("fours") or 0)
            d["sixes"] += int(r.get("sixes") or 0)
    for group in out:
        for key, d in out[group].items():
            d["strike_rate"] = _r(100 * d["runs"] / d["balls"]) if d["balls"] else None
            d["average"] = _r(d["runs"] / d["dismissals"]) if d["dismissals"] else None
            d["runs_per_innings"] = _r(d["runs"] / d["innings"]) if d["innings"] else None
    return out
