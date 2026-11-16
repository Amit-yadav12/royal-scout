"""Bowling intelligence engine.

Overs are treated as cricket notation throughout: every workload is carried as
*legal balls* and only formatted as overs for display. A bowler with 3.4 overs
has bowled 22 balls, not 3.4 overs of decimal arithmetic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np

from .canonical import GRANULARITY_AGGREGATE, GRANULARITY_INNINGS
from .config import Config
from .stats import (Confidence, bootstrap_ci, composite, confidence_grade,
                    consistency_from_cv, coefficient_of_variation, percentile_rank, shrink)


def overs_display(balls: int | None) -> str | None:
    if balls is None:
        return None
    return f"{balls // 6}.{balls % 6}"


def _r(v: float | None, nd: int = 2) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else round(f, nd)


@dataclass
class BowlingRaw:
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
    legal_balls: int = 0
    balls_missing: int = 0
    runs_conceded: int = 0
    runs_missing: int = 0
    wickets: int = 0
    wickets_missing: int = 0
    dots: int | None = 0
    maidens: int | None = 0
    best: tuple[int, int] | None = None
    econ_series: list[float] = field(default_factory=list)
    wicket_series: list[tuple[int, int]] = field(default_factory=list)  # (wickets, balls)
    granularity: str = GRANULARITY_AGGREGATE
    season_balls: dict[str, int] = field(default_factory=dict)
    season_runs: dict[str, int] = field(default_factory=dict)
    season_wkts: dict[str, int] = field(default_factory=dict)
    flags: set[str] = field(default_factory=set)
    unavailable: dict[str, str] = field(default_factory=dict)

    @property
    def balls_known(self) -> bool:
        return self.balls_missing == 0 and self.legal_balls > 0

    @property
    def wickets_known(self) -> bool:
        return self.wickets_missing == 0

    @property
    def average(self) -> float | None:
        if not self.wickets_known or self.wickets <= 0 or self.runs_missing:
            return None
        return self.runs_conceded / self.wickets

    @property
    def economy(self) -> float | None:
        if not self.balls_known or self.runs_missing:
            return None
        return self.runs_conceded * 6 / self.legal_balls

    @property
    def strike_rate(self) -> float | None:
        if not self.wickets_known or self.wickets <= 0 or not self.balls_known:
            return None
        return self.legal_balls / self.wickets

    @property
    def dot_pct(self) -> float | None:
        if self.dots is None or not self.balls_known:
            return None
        return 100 * self.dots / self.legal_balls


def compute_bowling_raw(records: Iterable[dict[str, Any]]) -> dict[str, BowlingRaw]:
    players: dict[str, BowlingRaw] = {}
    for r in records:
        p = r.get("player")
        if not p:
            continue
        b = players.get(p) or players.setdefault(p, BowlingRaw(player=p))
        b.records += 1
        if r.get("match_id"):
            b.match_ids.add(str(r["match_id"]))
        gran = r.get("granularity") or GRANULARITY_INNINGS
        b.innings += int(r.get("innings_count") or 1)
        balls = r.get("legal_balls")
        if balls is None:
            b.balls_missing += 1
        else:
            b.legal_balls += int(balls)
        if r.get("runs_conceded") is None:
            b.runs_missing += 1
        else:
            b.runs_conceded += int(r["runs_conceded"])
        if r.get("wickets") is None:
            b.wickets_missing += 1
        else:
            b.wickets += int(r["wickets"])
        b.dots = None if (b.dots is None or r.get("dot_balls") is None) else b.dots + int(r["dot_balls"])
        b.maidens = None if (b.maidens is None or r.get("maidens") is None) else b.maidens + int(r["maidens"])
        for key, attr in (("team", "teams"), ("competition", "competitions"),
                          ("season", "seasons"), ("venue", "venues"), ("opposition", "oppositions")):
            v = r.get(key)
            if v:
                getattr(b, attr).add(str(v).strip())
        b.flags.update(r.get("flags") or [])
        if gran == GRANULARITY_INNINGS:
            b.granularity = GRANULARITY_INNINGS
            if balls:
                b.econ_series.append(int(r["runs_conceded"] or 0) * 6 / int(balls))
                if r.get("wickets") is not None:
                    b.wicket_series.append((int(r["wickets"]), int(balls)))
        best = r.get("best_bowling")
        if best and "/" in str(best):
            try:
                w, rc = str(best).split("/")[:2]
                cand = (int(w), int(rc))
                if b.best is None or cand[0] > b.best[0] or (cand[0] == b.best[0] and cand[1] < b.best[1]):
                    b.best = cand
            except ValueError:
                pass
        elif gran == GRANULARITY_INNINGS:
            cand = (int(r.get("wickets") or 0), int(r.get("runs_conceded") or 0))
            if b.best is None or cand[0] > b.best[0] or (cand[0] == b.best[0] and cand[1] < b.best[1]):
                b.best = cand
        season = str(r.get("season") or "unknown")
        b.season_balls[season] = b.season_balls.get(season, 0) + int(balls or 0)
        b.season_runs[season] = b.season_runs.get(season, 0) + int(r.get("runs_conceded") or 0)
        b.season_wkts[season] = b.season_wkts.get(season, 0) + int(r.get("wickets") or 0)

    for b in players.values():
        if b.match_ids:
            b.matches = len(b.match_ids)
        if b.balls_missing:
            b.unavailable["legal_balls"] = f"{b.balls_missing} record(s) had no recoverable overs/workload"
        if b.runs_missing:
            b.unavailable["economy"] = f"{b.runs_missing} record(s) had no runs-conceded value"
        if b.wickets_missing:
            b.unavailable["wickets"] = f"{b.wickets_missing} record(s) had unclassified wicket attribution"
        if "invalid_overs" in b.flags:
            b.unavailable["overs_notation"] = "at least one source row used illegal overs notation"
        if b.dots is None:
            b.unavailable["dot_ball_percentage"] = "dot-ball counts are not present in the source"
        if not b.econ_series:
            b.unavailable["innings_economy_distribution"] = (
                "only multi-innings aggregates are present; per-innings economy dispersion is unavailable")
    return players


@dataclass
class BowlingBaseline:
    economy: float
    average: float
    strike_rate: float
    dot_pct: float | None
    population: int
    balls: int
    runs: int
    wickets: int


def bowling_baseline(players: dict[str, BowlingRaw]) -> BowlingBaseline:
    balls = sum(p.legal_balls for p in players.values())
    eligible = [p for p in players.values() if p.wickets_known and not p.runs_missing]
    runs = sum(p.runs_conceded for p in eligible)
    wkts = sum(p.wickets for p in eligible)
    dots = sum(p.dots for p in players.values() if p.dots is not None) if any(
        p.dots is not None for p in players.values()) else None
    return BowlingBaseline(
        economy=(runs * 6 / balls) if balls else 8.5,
        average=(runs / wkts) if wkts else 30.0,
        strike_rate=(balls / wkts) if wkts else 21.0,
        dot_pct=(100 * dots / balls) if (dots is not None and balls) else None,
        population=len(players), balls=balls, runs=runs, wickets=wkts)


def classify_bowler_type(metrics: dict[str, dict[str, Any]], phases: dict[str, dict[str, Any]] | None,
                         cfg: Config) -> dict[str, dict[str, Any]]:
    """Separate wicket-takers from economy bowlers from phase specialists.

    With ball-by-ball data the label is derived from *phase* economy/wicket rates.
    Without it, we fall back to career shape and say so. This prevents a
    low-economy, low-wicket bowler from being ranked as an equal of a strike
    bowler without the distinction being visible.
    """
    out: dict[str, dict[str, Any]] = {}
    econ_pct = percentile_rank({k: v.get("economy") for k, v in metrics.items()}, higher_is_better=False)
    sr_pct = percentile_rank({k: v.get("bowling_strike_rate") for k, v in metrics.items()},
                             higher_is_better=False)
    wpm_pct = percentile_rank({k: (v.get("wickets_per_innings") or 0) for k, v in metrics.items()})
    for pid, m in metrics.items():
        e, s, w = econ_pct.get(pid), sr_pct.get(pid), wpm_pct.get(pid)
        basis = "career_shape"
        phase_label = None
        if phases and pid in phases and phases[pid].get("available"):
            ph = phases[pid]
            shares = ph.get("phase_ball_shares") or {}
            best_phase = max(shares, key=shares.get) if shares else None
            if best_phase and shares.get(best_phase, 0) >= 0.55:
                phase_label = best_phase
            basis = "phase_workload"
        if phase_label:
            label = {"powerplay": "powerplay_specialist", "middle": "middle_overs_specialist",
                     "death": "death_specialist"}[phase_label]
        elif e is not None and s is not None and e >= 60 and s >= 60:
            label = "all_phase_bowler"
        elif s is not None and s >= 65 and (e is None or e < 60):
            label = "wicket_taker"
        elif e is not None and e >= 65 and (s is None or s < 65):
            label = "economy_bowler"
        elif w is not None and w >= 70:
            label = "wicket_taker"
        else:
            label = "balanced"
        out[pid] = {
            "bowler_type": label, "basis": basis,
            "economy_percentile": _r(e), "strike_rate_percentile": _r(s),
            "wickets_per_innings_percentile": _r(w),
            "note": ("Classification is derived from phase workload shares (ball-by-ball data present)."
                     if basis == "phase_workload" else
                     "Classification is derived from career shape only; phase data was not available."),
        }
    return out


def score_bowling_population(raw: dict[str, BowlingRaw], cfg: Config,
                             pressure: dict[str, dict[str, Any]] | None = None,
                             phases: dict[str, dict[str, Any]] | None = None,
                             roles: dict[str, dict[str, Any]] | None = None
                             ) -> dict[str, dict[str, Any]]:
    base = bowling_baseline(raw)
    st = cfg.stats
    ids = sorted(raw)

    econ_sh, avg_sh, sr_sh, dot_sh = {}, {}, {}, {}
    cons_raw: dict[str, float | None] = {}
    cons_basis: dict[str, str] = {}
    for pid in ids:
        p = raw[pid]
        econ_sh[pid] = shrink(p.economy, p.legal_balls if p.balls_known else None,
                              st.prior_strength_balls_econ, base.economy)
        avg_sh[pid] = shrink(p.average, p.wickets if p.wickets_known and p.wickets > 0 else None,
                             st.prior_strength_wickets_bowl, base.average)
        sr_sh[pid] = shrink(p.strike_rate, p.wickets if p.wickets_known and p.wickets > 0 else None,
                            st.prior_strength_wickets_bowl, base.strike_rate)
        dot_sh[pid] = shrink(p.dot_pct, p.legal_balls if p.balls_known else None,
                             st.prior_strength_balls_bowl, base.dot_pct) if base.dot_pct is not None else None
        if len(p.econ_series) >= 2:
            cons_raw[pid] = consistency_from_cv(coefficient_of_variation(p.econ_series))
            cons_basis[pid] = "innings_economy_distribution"
        elif len([s for s in p.season_balls.values() if s]) >= 2 and not p.runs_missing:
            season_econ = [p.season_runs[s] * 6 / p.season_balls[s]
                           for s in p.season_balls if p.season_balls[s] > 0]
            cons_raw[pid] = consistency_from_cv(coefficient_of_variation(season_econ))
            cons_basis[pid] = "season_economy_dispersion"
        else:
            cons_raw[pid] = None
            cons_basis[pid] = "unavailable: fewer than two economy observations"

    # economy: lower is better; average & SR: lower is better; dot%: higher better
    P_econ = percentile_rank(econ_sh, higher_is_better=False)
    P_avg = percentile_rank(avg_sh, higher_is_better=False)
    P_sr = percentile_rank(sr_sh, higher_is_better=False)
    P_dot = percentile_rank(dot_sh, higher_is_better=True)
    P_cons = percentile_rank(cons_raw, higher_is_better=True)
    P_wpi = percentile_rank({p: raw[p].wickets / raw[p].innings
                             if raw[p].wickets_known and raw[p].innings else None for p in ids},
                            higher_is_better=True)

    out: dict[str, dict[str, Any]] = {}
    for pid in ids:
        p = raw[pid]
        containment_parts = {"economy": P_econ.get(pid), "dot_ball_pct": P_dot.get(pid),
                             "bowling_average": P_avg.get(pid)}
        economy_containment, contain_cov, contain_applied = composite(
            containment_parts, {"economy": 0.50, "dot_ball_pct": 0.30, "bowling_average": 0.20})
        wicket_parts = {"strike_rate": P_sr.get(pid), "wickets_per_innings": P_wpi.get(pid)}
        wicket_score, wkt_cov, _ = composite(wicket_parts, {"strike_rate": 0.6, "wickets_per_innings": 0.4})

        performance, perf_cov, _ = composite(
            {"economy_containment": economy_containment, "wicket_taking": wicket_score},
            {"economy_containment": 0.45, "wicket_taking": 0.55})

        consistency = None
        consistency_detail: dict[str, Any] = {"basis": cons_basis[pid]}
        if P_cons.get(pid) is not None:
            multi_wkt_rate = None
            if p.wickets_known and p.wicket_series:
                multi_wkt_rate = sum(1 for w, _ in p.wicket_series if w >= 2) / len(p.wicket_series)
            bonus = 0.0 if multi_wkt_rate is None else (multi_wkt_rate - 0.25) * 40
            consistency = max(0.0, min(100.0, (P_cons[pid] or 0) * 0.85 + 15 * 0.15 + bonus))
            cv = coefficient_of_variation(p.econ_series) if p.econ_series else None
            consistency_detail.update({
                "cv": _r(cv, 3), "multi_wicket_innings_rate": _r(multi_wkt_rate, 3),
                "observations": len(p.econ_series),
                "warning": ("computed across season aggregates — not innings-level consistency"
                            if cons_basis[pid] == "season_economy_dispersion" else None)})
        else:
            consistency_detail["reason"] = cons_basis[pid]

        ci_lo, ci_hi = bootstrap_ci(p.econ_series, lambda s: float(np.mean(s)), st) if p.econ_series else (None, None)
        rel_ci = None
        if ci_lo is not None and ci_hi is not None and p.econ_series:
            mean = float(np.mean(p.econ_series))
            rel_ci = (ci_hi - ci_lo) / max(1.0, abs(mean))

        conf = confidence_grade(float(p.legal_balls), perf_cov, rel_ci, st, "legal balls bowled")

        pressure_component = None
        pressure_detail: dict[str, Any] = {"status": "unavailable",
                                           "reason": "no ball-by-ball data was supplied"}
        if pressure and pid in pressure:
            pressure_component = pressure[pid].get("score")
            pressure_detail = pressure[pid].get("detail", {})

        # wicket-taking consistency (share of innings with >=1 wicket) if innings-level
        wkt_conv = None
        if p.wickets_known and p.wicket_series:
            wkt_conv = 100 * sum(1 for w, _ in p.wicket_series if w > 0) / len(p.wicket_series)

        components = {
            "performance": performance, "wicket_taking": wicket_score, "economy": economy_containment,
            "consistency": consistency, "pressure": pressure_component, "confidence": conf.score,
        }
        weights = {"performance": cfg.bowling_weights.performance,
                   "wicket_taking": cfg.bowling_weights.wicket_taking,
                   "economy": cfg.bowling_weights.economy,
                   "consistency": cfg.bowling_weights.consistency,
                   "pressure": cfg.bowling_weights.pressure,
                   "confidence": cfg.bowling_weights.confidence}
        rabi, coverage, applied = composite(components, weights)
        final_conf = confidence_grade(float(p.legal_balls), coverage, rel_ci, st, "legal balls bowled")

        out[pid] = {
            "player": pid, "teams": sorted(p.teams), "competitions": sorted(p.competitions),
            "seasons": sorted(p.seasons), "venues": sorted(p.venues), "oppositions": sorted(p.oppositions),
            "records": p.records, "innings": p.innings, "matches": p.matches,
            "overs": overs_display(p.legal_balls if p.balls_known else None),
            "legal_balls": p.legal_balls if p.balls_known else None,
            "runs_conceded": p.runs_conceded if not p.runs_missing else None,
            "wickets": p.wickets if p.wickets_known else None,
            "average": _r(p.average), "economy": _r(p.economy), "bowling_strike_rate": _r(p.strike_rate),
            "dot_balls": p.dots, "dot_pct": _r(p.dot_pct),
            "maidens": p.maidens,
            "best_bowling": (f"{p.best[0]}/{p.best[1]}" if p.best else None),
            "wickets_per_innings": _r(p.wickets / p.innings)
            if p.wickets_known and p.innings else None,
            "wickets_per_match": None,
            "multi_wicket_innings": (sum(1 for w, _ in p.wicket_series if w >= 2)
                                     if p.wickets_known and p.wicket_series else None),
            "wicket_conversion_pct": _r(wkt_conv),
            "boundary_conceded_pct": None,  # requires ball-level boundary data; filled by pressure module
            "bowler_type": None,
            "economy_containment_score": _r(economy_containment),
            "wicket_taking_score": _r(wicket_score),
            "performance_score": _r(performance), "performance_coverage": round(perf_cov, 3),
            "consistency": _r(consistency), "consistency_detail": consistency_detail,
            "reliability": _r(composite({"consistency": consistency, "confidence": conf.score},
                                        {"consistency": 0.65, "confidence": 0.35})[0]),
            "pressure_score": _r(pressure_component), "pressure_detail": pressure_detail,
            "confidence": final_conf.to_dict(), "confidence_score": final_conf.score, "grade": final_conf.grade,
            "rabi_bowl": _r(rabi), "score_coverage": round(coverage, 3),
            "component_weights_applied": {k: round(v, 4) for k, v in applied.items()},
            "exposure_balls": p.legal_balls,
            "granularity": p.granularity,
            "unavailable": p.unavailable,
            "method": {
                "shrinkage": {"k_balls": st.prior_strength_balls_econ,
                              "k_wickets": st.prior_strength_wickets_bowl,
                              "baseline_economy": round(base.economy, 2),
                              "baseline_average": round(base.average, 2),
                              "baseline_strike_rate": round(base.strike_rate, 2),
                              "baseline_dot_pct": _r(base.dot_pct)},
                "shrunk_values": {"economy": _r(econ_sh[pid]), "average": _r(avg_sh[pid]),
                                  "strike_rate": _r(sr_sh[pid]), "dot_pct": _r(dot_sh[pid])},
            },
        }

    types = classify_bowler_type(out, phases, cfg)
    for pid in ids:
        out[pid].update({"bowler_type": types[pid]["bowler_type"],
                         "bowler_type_detail": types[pid]})
    return out


def bowling_situational_splits(records: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = {"by_season": {}, "by_opposition": {}, "by_venue": {},
                                                 "by_innings_number": {}}
    for r in records:
        p = r.get("player")
        if not p:
            continue
        for group, key in (("by_season", r.get("season")), ("by_opposition", r.get("opposition")),
                           ("by_venue", r.get("venue")),
                           ("by_innings_number", (str(r["innings_number"]) if r.get("innings_number") else None))):
            if key is None:
                continue
            d = out[group].setdefault(f"{p}|{key}", {"balls": 0, "runs": 0, "wickets": 0, "innings": 0,
                                                     "dots": 0, "dots_known": True})
            d["balls"] += int(r.get("legal_balls") or 0)
            d["runs"] += int(r.get("runs_conceded") or 0)
            d["wickets"] += int(r.get("wickets") or 0)
            d["innings"] += int(r.get("innings_count") or 1)
            if r.get("dot_balls") is None:
                d["dots_known"] = False
            else:
                d["dots"] += int(r["dot_balls"])
    for group in out:
        for d in out[group].values():
            d["economy"] = _r(d["runs"] * 6 / d["balls"]) if d["balls"] else None
            d["average"] = _r(d["runs"] / d["wickets"]) if d["wickets"] else None
            d["strike_rate"] = _r(d["balls"] / d["wickets"]) if d["wickets"] else None
            d["dot_pct"] = _r(100 * d["dots"] / d["balls"]) if (d["dots_known"] and d["balls"]) else None
            d.pop("dots_known", None)
    return out
