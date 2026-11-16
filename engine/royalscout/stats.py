"""Reproducible statistical utilities.

Implements percentile normalisation, robust scaling, Bayesian-style shrinkage,
bootstrap confidence intervals, coverage-aware composite scoring, confidence
grading and rank-stability statistics. All randomness is seeded.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

import numpy as np

from .config import StatsConfig


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------
def percentile_rank(values: dict[str, float | None], higher_is_better: bool = True) -> dict[str, float]:
    """Map values onto 0-100 using mid-rank percentiles (ties share a score)."""
    present = {k: v for k, v in values.items() if v is not None and not (isinstance(v, float) and math.isnan(v))}
    out: dict[str, float] = {}
    if not present:
        return {k: 0.0 for k in values}
    items = sorted(present.items(), key=lambda kv: kv[1])
    n = len(items)
    if n == 1:
        return {k: 50.0 if present else 0.0 for k in values}
    # assign averaged ranks
    ranks: dict[str, float] = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and items[j + 1][1] == items[i][1]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[items[k][0]] = avg_rank
        i = j + 1
    for k, r in ranks.items():
        pct = 100 * (r - 1) / (n - 1)
        out[k] = pct if higher_is_better else 100 - pct
    for k in values:
        out.setdefault(k, None)  # type: ignore[arg-type]
    return out


def robust_scale(values: dict[str, float | None]) -> dict[str, float | None]:
    """Median/MAD scaling — resilient to the outliers endemic in small samples."""
    present = {k: v for k, v in values.items() if v is not None}
    if len(present) < 3:
        return {k: None for k in values}
    arr = np.array(list(present.values()), dtype=float)
    med = float(np.median(arr))
    mad = float(np.median(np.abs(arr - med)))
    scale = mad * 1.4826 if mad > 0 else float(np.std(arr)) or 1.0
    return {k: (v - med) / scale for k, v in values.items() if v is not None}


def zscore(values: dict[str, float | None]) -> dict[str, float | None]:
    present = {k: v for k, v in values.items() if v is not None}
    if len(present) < 2:
        return {k: None for k in values}
    arr = np.array(list(present.values()), dtype=float)
    mu, sd = float(arr.mean()), float(arr.std(ddof=1)) or 0.0
    if sd == 0:
        return {k: 0.0 for k in present}
    return {k: (v - mu) / sd for k, v in present.items()}


# ---------------------------------------------------------------------------
# Shrinkage
# ---------------------------------------------------------------------------
def shrink(observed: float | None, exposure: float | None, k: float, baseline: float) -> float | None:
    """Adjusted = observed * n/(n+k) + baseline * k/(n+k).

    `exposure` must be the honest denominator for the metric (balls for strike
    rate, dismissals for average, wickets for bowling strike rate). Passing 0
    exposure returns the baseline, never the player's own noisy value.
    """
    if observed is None:
        return None
    n = max(0.0, float(exposure or 0.0))
    if n <= 0:
        return baseline
    w = n / (n + k)
    return observed * w + baseline * (1 - w)


def shrinkage_weight(exposure: float | None, k: float) -> float:
    n = max(0.0, float(exposure or 0.0))
    return n / (n + k) if (n + k) > 0 else 0.0


# ---------------------------------------------------------------------------
# Dispersion / consistency
# ---------------------------------------------------------------------------
def coefficient_of_variation(scores: Sequence[float]) -> float | None:
    vals = [float(s) for s in scores if s is not None]
    if len(vals) < 2:
        return None
    mu = sum(vals) / len(vals)
    if mu <= 0:
        return None
    sd = float(np.std(vals, ddof=1))
    return sd / mu


def consistency_from_cv(cv: float | None) -> float | None:
    """Map CV to a 0-100 *relative* consistency measure (1/(1+CV) * 100).

    A CV of 0 gives 100; 0.5 gives 67; 1.0 gives 50; 2.0 gives 33. Documented,
    monotone and bounded — then percentile-ranked against the peer group so the
    final score is population-relative rather than absolute.
    """
    if cv is None:
        return None
    return 100.0 / (1.0 + max(0.0, cv))


def bootstrap_ci(scores: Sequence[float], statistic: Callable[[Sequence[float]], float],
                 cfg: StatsConfig) -> tuple[float | None, float | None]:
    vals = [float(s) for s in scores if s is not None]
    if len(vals) < 3:
        return None, None
    rng = random.Random(cfg.bootstrap_seed)
    n = len(vals)
    stats = []
    for _ in range(cfg.bootstrap_iterations):
        sample = [vals[rng.randrange(n)] for _ in range(n)]
        try:
            stats.append(statistic(sample))
        except Exception:
            continue
    if not stats:
        return None, None
    lo = float(np.percentile(stats, 100 * (1 - cfg.ci_level) / 2))
    hi = float(np.percentile(stats, 100 * (1 - (1 - cfg.ci_level) / 2)))
    return lo, hi


# ---------------------------------------------------------------------------
# Coverage-aware composite
# ---------------------------------------------------------------------------
def composite(components: dict[str, float | None], weights: dict[str, float],
              config_stats: StatsConfig | None = None) -> tuple[float | None, float, dict[str, float]]:
    """Weighted mean over *available* components, with renormalisation.

    Returns (score, coverage, applied_weights). Coverage is the share of the
    nominal weight that the data actually supports — published next to every
    composite so partial models cannot masquerade as complete ones.
    """
    available = {k: v for k, v in components.items()
                 if v is not None and not (isinstance(v, float) and math.isnan(v))}
    total_w = sum(weights.get(k, 0.0) for k in weights)
    if not available or total_w <= 0:
        return None, 0.0, {}
    avail_w = sum(weights.get(k, 0.0) for k in available)
    if avail_w <= 0:
        return None, 0.0, {}
    score = sum(available[k] * weights.get(k, 0.0) for k in available) / avail_w
    applied = {k: weights.get(k, 0.0) / avail_w for k in available}
    return score, avail_w / total_w, applied


# ---------------------------------------------------------------------------
# Confidence grading
# ---------------------------------------------------------------------------
@dataclass
class Confidence:
    grade: str
    score: float
    exposure: float
    coverage: float
    ci_width: float | None
    reasons: list[str]

    def to_dict(self) -> dict:
        return {"grade": self.grade, "score": round(self.score, 2), "exposure": self.exposure,
                "coverage": round(self.coverage, 3),
                "ci_width": None if self.ci_width is None else round(self.ci_width, 3),
                "reasons": self.reasons}


def confidence_grade(exposure: float, coverage: float, ci_width: float | None,
                     cfg: StatsConfig, exposure_name: str = "balls") -> Confidence:
    reasons: list[str] = []
    base = 0.0
    if exposure >= cfg.grade_a_min_exposure:
        base, grade = 100.0, "A"
        reasons.append(f"{exposure:.0f} {exposure_name} (>= {cfg.grade_a_min_exposure}) supports grade A exposure")
    elif exposure >= cfg.grade_b_min_exposure:
        base, grade = 78.0, "B"
        reasons.append(f"{exposure:.0f} {exposure_name} (>= {cfg.grade_b_min_exposure}) supports grade B exposure")
    elif exposure >= cfg.grade_c_min_exposure:
        base, grade = 55.0, "C"
        reasons.append(f"{exposure:.0f} {exposure_name} (>= {cfg.grade_c_min_exposure}) supports grade C exposure")
    else:
        base, grade = 28.0, "D"
        reasons.append(f"only {exposure:.0f} {exposure_name} (< {cfg.grade_c_min_exposure}) — grade D exposure")

    # coverage modifier: a partial model cannot hold a top grade
    score = base * (0.55 + 0.45 * min(1.0, coverage))
    if coverage < cfg.grade_a_min_coverage and grade == "A":
        grade = "B"
        reasons.append(f"composite coverage {coverage:.0%} < {cfg.grade_a_min_coverage:.0%} caps the grade at B")
    if coverage < cfg.grade_b_min_coverage and grade in {"A", "B"}:
        grade = "C"
        reasons.append(f"composite coverage {coverage:.0%} < {cfg.grade_b_min_coverage:.0%} caps the grade at C")

    if ci_width is not None:
        # a wide interval relative to the score means unstable evidence
        rel = ci_width / max(1.0, 50.0)
        if rel > cfg.grade_volatility_penalty:
            score *= max(0.6, 1 - 0.35 * rel)
            if grade in {"A", "B"}:
                grade = {"A": "B", "B": "C"}[grade]
            reasons.append(f"bootstrap interval width {ci_width:.1f} indicates volatile output; grade reduced")

    return Confidence(grade, round(min(100.0, score), 2), round(exposure, 1),
                      round(coverage, 3), ci_width, reasons)


# ---------------------------------------------------------------------------
# Rank statistics
# ---------------------------------------------------------------------------
def spearman(a: dict[str, float], b: dict[str, float]) -> float | None:
    keys = sorted(set(a) & set(b))
    if len(keys) < 3:
        return None
    ra = {k: i for i, k in enumerate(sorted(keys, key=lambda x: a[x]))}
    rb = {k: i for i, k in enumerate(sorted(keys, key=lambda x: b[x]))}
    n = len(keys)
    d2 = sum((ra[k] - rb[k]) ** 2 for k in keys)
    return 1 - (6 * d2) / (n * (n * n - 1))


def pearson(a: dict[str, float], b: dict[str, float]) -> float | None:
    keys = sorted(set(a) & set(b))
    if len(keys) < 3:
        return None
    x = np.array([a[k] for k in keys], dtype=float)
    y = np.array([b[k] for k in keys], dtype=float)
    if x.std() == 0 or y.std() == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def kendall_tau(a: dict[str, float], b: dict[str, float]) -> float | None:
    keys = sorted(set(a) & set(b))
    if len(keys) < 3:
        return None
    conc = disc = 0
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            ka, kb = keys[i], keys[j]
            da = a[ka] - a[kb]
            db = b[ka] - b[kb]
            if da == 0 or db == 0:
                continue
            if da * db > 0:
                conc += 1
            else:
                disc += 1
    tot = conc + disc
    return (conc - disc) / tot if tot else None


def two_proportion_z(p1: float, n1: float, p2: float, n2: float) -> float | None:
    """Quick significance check between two rates with different exposure."""
    if n1 <= 0 or n2 <= 0:
        return None
    p = (p1 * n1 + p2 * n2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return None
    return (p1 - p2) / se
