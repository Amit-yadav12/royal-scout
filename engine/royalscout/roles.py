"""Role classification.

Rules of engagement:
* A declared role from the source is used when present.
* Otherwise the role is inferred from *observable workload* (innings batted, balls
  bowled, wicket share) — and the basis is always published.
* A wicketkeeper is never inferred from statistics alone; absent a declared role
  the player is labelled "batter" with ``keeper_confidence = "unverified"``.
"""
from __future__ import annotations

from typing import Any

from .config import Config

ROLE_BATTER = "batter"
ROLE_BOWLER = "bowler"
ROLE_ALLROUNDER = "all-rounder"
ROLE_KEEPER = "wicketkeeper"
ROLE_UNKNOWN = "unknown"

_DECLARED_MAP = {
    "bat": ROLE_BATTER, "batter": ROLE_BATTER, "batsman": ROLE_BATTER, "top order batter": ROLE_BATTER,
    "middle order batter": ROLE_BATTER, "opener": ROLE_BATTER,
    "bowl": ROLE_BOWLER, "bowler": ROLE_BOWLER, "fast bowler": ROLE_BOWLER,
    "spin bowler": ROLE_BOWLER, "pace bowler": ROLE_BOWLER, "seamer": ROLE_BOWLER, "spinner": ROLE_BOWLER,
    "all rounder": ROLE_ALLROUNDER, "all-rounder": ROLE_ALLROUNDER, "allrounder": ROLE_ALLROUNDER,
    "wicket keeper": ROLE_KEEPER, "wicketkeeper": ROLE_KEEPER, "wk": ROLE_KEEPER,
    "wk-batter": ROLE_KEEPER, "keeper": ROLE_KEEPER, "wicket keeper batter": ROLE_KEEPER,
}


def _normalise_declared(text: str | None) -> str | None:
    if not text:
        return None
    t = str(text).strip().lower().replace("_", " ")
    if t in _DECLARED_MAP:
        return _DECLARED_MAP[t]
    for k, v in _DECLARED_MAP.items():
        if k in t:
            return v
    return None


def classify_roles(bat_raw: dict[str, Any], bowl_raw: dict[str, Any],
                   declared: dict[str, str], cfg: Config) -> dict[str, dict[str, Any]]:
    rc = cfg.roles
    players = set(bat_raw) | set(bowl_raw) | set(declared)
    out: dict[str, dict[str, Any]] = {}
    for pid in sorted(players):
        b = bat_raw.get(pid)
        w = bowl_raw.get(pid)
        bat_innings = b.innings if b else 0
        bat_balls = b.balls if b else 0
        bowl_balls = w.legal_balls if w else 0
        bowl_wkts = w.wickets if w else 0

        decl = _normalise_declared(declared.get(pid))
        basis = "declared" if decl else "inferred_from_workload"
        primary, secondary = ROLE_UNKNOWN, None
        notes: list[str] = []

        bat_ok = bat_innings >= rc.allrounder_min_innings_bat and bat_balls > 0
        bowl_ok = bowl_balls >= rc.allrounder_min_balls_bowl
        if bat_ok and bowl_ok:
            # balance: neither discipline is a token presence
            bat_rate = (b.runs / b.innings) if b and b.innings else 0
            bowl_rate = (bowl_wkts / max(1, bowl_balls / 6)) if bowl_balls else 0
            bat_share = bat_rate / max(0.01, bat_rate + bowl_rate * 8)
            if 0.25 <= bat_share <= 0.75:
                primary = ROLE_ALLROUNDER
                secondary = ROLE_BATTER if bat_share >= 0.5 else ROLE_BOWLER
                notes.append(f"batting share of combined output = {bat_share:.2f}")
            else:
                primary = ROLE_BATTER if bat_share > 0.75 else ROLE_BOWLER
                secondary = ROLE_ALLROUNDER
                notes.append("both disciplines present but output is strongly one-sided")
        elif bat_ok and bat_balls >= 120:
            primary = ROLE_BATTER
            if bowl_ok:
                secondary = ROLE_ALLROUNDER
        elif bowl_ok:
            primary = ROLE_BOWLER
            if bat_ok:
                secondary = ROLE_ALLROUNDER
        elif bat_innings or bat_balls:
            primary = ROLE_BATTER
        elif bowl_balls:
            primary = ROLE_BOWLER

        if decl:
            primary = decl if primary == ROLE_UNKNOWN or decl not in {ROLE_BATTER, ROLE_BOWLER} else decl
            if decl == ROLE_KEEPER and primary not in {ROLE_KEEPER}:
                primary = ROLE_KEEPER
            notes.append("role taken from the source's own role column")
        keeper_confidence = "declared" if decl == ROLE_KEEPER else "unverified"
        out[pid] = {
            "primary_role": primary, "secondary_role": secondary, "role_basis": basis,
            "keeper_confidence": keeper_confidence,
            "batting_innings": bat_innings, "balls_faced": bat_balls,
            "legal_balls_bowled": bowl_balls, "wickets": bowl_wkts,
            "notes": notes,
            "eligibility_warning": (
                "no batting or bowling exposure in the dataset" if primary == ROLE_UNKNOWN else None),
        }
    return out
