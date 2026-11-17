"""Canonical cricket data model construction.

Turns profiled source tables into the logical entities the analytics engine needs
(batting records, bowling records, ball events, players, matches), preserving
lineage back to file / worksheet / row.

Two granularities are modelled explicitly and never conflated:

* ``granularity == "innings"``  – one row per innings (or per match performance).
* ``granularity == "aggregate"`` – one row covering several innings (a season or
  career aggregate). Match-level metrics such as "consistency across innings"
  cannot be computed from these; only aggregate-level dispersion is available and
  it is labelled as such.

Ball-by-ball data is reduced to innings-level records so that every downstream
metric has one definition.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

import polars as pl

from .ingest import RawTable, TableProfile
from .schema import FIELD_INDEX, is_nullish, parse_overs, to_float, to_int

GRANULARITY_INNINGS = "innings"
GRANULARITY_AGGREGATE = "aggregate"


def records_frame(records: list[dict[str, Any]]) -> pl.DataFrame:
    """Build a Parquet-friendly frame: nested values are JSON-encoded, not dropped."""
    import json as _json

    if not records:
        return pl.DataFrame()
    keys: list[str] = []
    for r in records:
        for k in r:
            if k not in keys:
                keys.append(k)
    cols: dict[str, list[Any]] = {}
    for k in keys:
        vals = []
        for r in records:
            v = r.get(k)
            if isinstance(v, (dict, list, tuple, set)):
                v = _json.dumps(v, default=str)
            elif isinstance(v, bool):
                v = v
            vals.append(v)
        # normalise mixed types so Arrow can infer a stable type
        types = {type(v) for v in vals if v is not None}
        if len(types) > 1:
            vals = [None if v is None else str(v) for v in vals]
        cols[k] = vals
    return pl.DataFrame(cols)


# ---------------------------------------------------------------------------
# Lineage helpers
# ---------------------------------------------------------------------------
def row_lineage(t: RawTable, row_index: int) -> dict[str, Any]:
    return {"source_file": t.source_path, "worksheet": t.meta.get("worksheet") or t.table_name,
            "source_row": t.header_row + 2 + row_index, "container": t.container}


def _cell(row: list[Any], idx: int | None) -> Any:
    if idx is None or idx >= len(row):
        return None
    return row[idx]


def _field_cols(profile: TableProfile) -> dict[str, list[int]]:
    """canonical field -> list of column indexes (multiple values allowed)."""
    out: dict[str, list[int]] = {}
    for m in profile.mapping:
        if not m.field:
            continue
        try:
            idx = profile.columns.index(m.column)
        except ValueError:
            continue
        out.setdefault(m.field, []).append(idx)
    return out


def _first(fields: dict[str, list[int]], name: str) -> int | None:
    vals = fields.get(name)
    return vals[0] if vals else None


def normalise_player_name(raw: Any) -> str:
    """Conservative canonicalisation: casing, punctuation, whitespace, comma swap.

    This is the only transformation applied *without* human review because it is
    provably identity-preserving. Everything else becomes a *suggested* merge.
    """
    if is_nullish(raw):
        return ""
    s = str(raw).replace("\u00a0", " ").strip()
    s = re.sub(r"\s+", " ", s)
    if "," in s and len(s.split(",")) == 2:
        last, first = [p.strip() for p in s.split(",")]
        s = f"{first} {last}".strip()
    s = re.sub(r"\((c|wk|vc|capt|keeper)\)", "", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" .*-")
    return re.sub(r"[^A-Za-z .'\-]", "", s).title().strip()


def name_key(name: str) -> str:
    return re.sub(r"[^a-z]", "", name.lower())


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------
@dataclass
class PlayerRegistry:
    """Player identity resolution."""

    canonical: dict[str, str] = field(default_factory=dict)          # name_key -> canonical name
    aliases: dict[str, list[str]] = field(default_factory=dict)       # canonical -> raw variants
    teams: dict[str, set[str]] = field(default_factory=dict)          # canonical -> teams
    suggestions: list[dict[str, Any]] = field(default_factory=list)   # reviewable merges
    conflicts: list[dict[str, Any]] = field(default_factory=list)     # ambiguous identities
    auto_merged: int = 0

    def resolve(self, raw: Any) -> str:
        name = normalise_player_name(raw)
        if not name:
            return ""
        key = name_key(name)
        canon = self.canonical.get(key, name)
        if canon == name and name not in self.aliases:
            self.aliases.setdefault(name, [str(raw)])
            self.canonical[key] = name
        elif str(raw) not in self.aliases.setdefault(canon, []):
            self.aliases[canon].append(str(raw))
        return canon

    def to_dict(self) -> dict[str, Any]:
        return {
            "players": [
                {"player": c, "aliases": sorted(set(self.aliases.get(c, []))),
                 "teams": sorted(self.teams.get(c, set()))}
                for c in sorted(self.aliases)
            ],
            "suggested_merges": self.suggestions,
            "identity_conflicts": self.conflicts,
            "auto_merged_variants": self.auto_merged,
        }


def build_player_registry(name_team_pairs: Iterable[tuple[str, str | None]],
                         auto_merge_similarity: float = 0.965) -> PlayerRegistry:
    """Cluster player names. Only provably-safe merges are automatic.

    A fuzzy similarity at/above `auto_merge_similarity` (default 0.965) is still
    only a *suggestion* unless the raw strings differ solely in case,
    punctuation, spacing or surname-first ordering — those were already
    canonicalised by `normalise_player_name`.
    """
    import difflib

    reg = PlayerRegistry()
    pairs = [(normalise_player_name(n), t) for n, t in name_team_pairs if normalise_player_name(n)]
    for name, team in pairs:
        canon = reg.resolve(name)
        if team:
            reg.teams.setdefault(canon, set()).add(str(team).strip())
    names = sorted(reg.aliases)
    # team conflicts for a single canonical player
    for n in names:
        if len(reg.teams.get(n, ())) > 1:
            reg.conflicts.append({
                "player": n, "issue": "multiple teams mapped to one canonical name",
                "teams": sorted(reg.teams[n]),
                "resolution": "kept as one player (same name); verify if these are different people",
            })
    # fuzzy merge suggestions
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            ratio = difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()
            if ratio >= auto_merge_similarity:
                ka, kb = name_key(a), name_key(b)
                if ka == kb:
                    continue
                same_team = bool(reg.teams.get(a, set()) & reg.teams.get(b, set()))
                reg.suggestions.append({
                    "a": a, "b": b, "similarity": round(ratio, 4),
                    "shared_team": same_team,
                    "action_required": "manual review — names differ beyond punctuation/casing",
                })
    return reg


@dataclass
class CanonicalData:
    batting: list[dict[str, Any]] = field(default_factory=list)
    bowling: list[dict[str, Any]] = field(default_factory=list)
    ball_events: pl.DataFrame | None = None
    matches: list[dict[str, Any]] = field(default_factory=list)
    registry: PlayerRegistry = field(default_factory=PlayerRegistry)
    unmapped_tables: list[dict[str, Any]] = field(default_factory=list)
    player_attributes: dict[str, dict[str, Any]] = field(default_factory=dict)
    derivations: list[dict[str, Any]] = field(default_factory=list)
    capabilities: dict[str, bool] = field(default_factory=dict)

    def batting_frame(self) -> pl.DataFrame:
        return records_frame(self.batting)

    def bowling_frame(self) -> pl.DataFrame:
        return records_frame(self.bowling)


# ---------------------------------------------------------------------------
# Batting extraction
# ---------------------------------------------------------------------------
BAT_SCHEMA_DEFAULTS: dict[str, Any] = {
    "player": "", "team": None, "opposition": None, "competition": None, "season": None,
    "match_id": None, "match_date": None, "venue": None, "innings_number": None,
    "batting_position": None, "runs": 0, "balls_faced": None, "fours": None, "sixes": None,
    "dot_balls_faced": None, "not_outs": 0, "dismissals": None, "innings_count": 1,
    "highest_score": None, "granularity": GRANULARITY_INNINGS, "derived_balls": False,
    "derived_dismissals": False, "source_file": None, "worksheet": None, "source_row": None,
    "record_id": "", "flags": [],
}


def _parse_hs(v: Any) -> tuple[int | None, bool | None]:
    if is_nullish(v):
        return None, None
    s = str(v).strip()
    not_out = s.endswith("*")
    val = to_int(s.rstrip("*"))
    return val, not_out


def extract_batting(t: RawTable, p: TableProfile, reg: PlayerRegistry,
                    derivations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    f = _field_cols(p)
    i_player = _first(f, "player_name") if _first(f, "player_name") is not None else _first(f, "batter_name")
    if i_player is None:
        return []
    i_runs = _first(f, "runs")
    out: list[dict[str, Any]] = []
    for ri, row in enumerate(t.data_rows):
        raw_name = _cell(row, i_player)
        player = reg.resolve(raw_name)
        if not player:
            continue
        runs = to_int(_cell(row, i_runs)) if i_runs is not None else None
        if runs is None:
            # a row with no readable run value is kept out of analytics but reported
            derivations.append({"kind": "batting_row_rejected", "player": player,
                                "reason": "runs value missing or unparseable",
                                "lineage": row_lineage(t, ri)})
            continue
        rec = dict(BAT_SCHEMA_DEFAULTS)
        rec.update({k: None for k in rec if k not in ("runs",)})
        rec["flags"] = []
        rec["player"] = player
        rec["runs"] = runs
        rec["team"] = _str_or_none(_cell(row, _first(f, "team")))
        rec["opposition"] = _str_or_none(_cell(row, _first(f, "opposition")))
        rec["competition"] = _str_or_none(_cell(row, _first(f, "competition")))
        rec["season"] = _str_or_none(_cell(row, _first(f, "season")))
        rec["match_id"] = _str_or_none(_cell(row, _first(f, "match_id")))
        rec["match_date"] = _str_or_none(_cell(row, _first(f, "match_date")))
        rec["venue"] = _str_or_none(_cell(row, _first(f, "venue")))
        rec["innings_number"] = to_int(_cell(row, _first(f, "innings_number")))
        rec["batting_position"] = to_int(_cell(row, _first(f, "batting_position")))
        rec["balls_faced"] = to_int(_cell(row, _first(f, "balls_faced")))
        rec["fours"] = to_int(_cell(row, _first(f, "fours")))
        rec["sixes"] = to_int(_cell(row, _first(f, "sixes")))
        rec["dot_balls_faced"] = to_int(_cell(row, _first(f, "dot_balls_faced")))
        hs, hs_star = _parse_hs(_cell(row, _first(f, "highest_score")))
        rec["highest_score"] = hs

        innings_count = to_int(_cell(row, _first(f, "innings")))
        if innings_count is not None and innings_count > 1:
            rec["granularity"] = GRANULARITY_AGGREGATE
            rec["innings_count"] = innings_count
        else:
            rec["granularity"] = GRANULARITY_INNINGS
            rec["innings_count"] = 1

        # ---- dismissals / not-outs: only from explicit evidence ----
        not_outs = to_int(_cell(row, _first(f, "not_outs")))
        dismissals_field = to_int(_cell(row, _first(f, "dismissals")))
        not_out_flag = _cell(row, _first(f, "not_out"))
        dismissal_text = _cell(row, _first(f, "dismissal"))

        if not_outs is not None:
            rec["not_outs"] = not_outs
        elif _is_not_out_flag(not_out_flag) is not None:
            rec["not_outs"] = 1 if _is_not_out_flag(not_out_flag) else 0
        elif not is_nullish(dismissal_text):
            txt = str(dismissal_text).strip().lower()
            if txt in {"not out", "notout", "retired hurt", "retired not out", "absent hurt"}:
                rec["not_outs"] = 1
                if txt.startswith("retired"):
                    rec["flags"].append("retired_not_out")
            else:
                rec["not_outs"] = 0
        elif hs_star is not None and rec["granularity"] == GRANULARITY_INNINGS:
            rec["not_outs"] = 1 if hs_star else 0
        else:
            rec["not_outs"] = None  # unknown — never assume

        if dismissals_field is not None:
            rec["dismissals"] = dismissals_field
        elif rec["not_outs"] is not None and rec["innings_count"]:
            rec["dismissals"] = rec["innings_count"] - rec["not_outs"]
            rec["derived_dismissals"] = True
        else:
            avg = to_float(_cell(row, _first(f, "batting_average")))
            if avg and avg > 0:
                rec["dismissals"] = max(0, int(round(runs / avg)))
                rec["derived_dismissals"] = True
                derived = {"kind": "dismissals_from_average", "player": player,
                           "basis": "runs / stated average",
                           "lineage": row_lineage(t, ri)}
                derivations.append(derived)
            else:
                rec["dismissals"] = None

        if rec["balls_faced"] is None:
            sr = to_float(_cell(row, _first(f, "strike_rate")))
            if sr and sr > 0:
                rec["balls_faced"] = int(round(runs * 100 / sr))
                rec["derived_balls"] = True
                derivations.append({"kind": "balls_from_strike_rate", "player": player,
                                    "basis": "runs*100/stated SR",
                                    "accuracy": "approx",
                                    "lineage": row_lineage(t, ri)})
        rec["lineage"] = row_lineage(t, ri)
        rec["source_file"] = rec["lineage"]["source_file"]
        rec["worksheet"] = rec["lineage"]["worksheet"]
        rec["source_row"] = rec["lineage"]["source_row"]
        rec["record_id"] = _rid("bat", t.source_path, t.table_name, ri, player, rec["season"])
        out.append(rec)
    return out


def _str_or_none(v: Any) -> str | None:
    if is_nullish(v):
        return None
    s = str(v).strip()
    return s if s else None


def _is_not_out_flag(v: Any) -> bool | None:
    if is_nullish(v):
        return None
    s = str(v).strip().lower()
    if s in {"true", "yes", "y", "1", "not out", "n/o"}:
        return True
    if s in {"false", "no", "n", "0", "out", "dismissed"}:
        return False
    return None


def _rid(*parts: Any) -> str:
    blob = "|".join(str(x) for x in parts)
    return hashlib.sha1(blob.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Bowling extraction
# ---------------------------------------------------------------------------
def extract_bowling(t: RawTable, p: TableProfile, reg: PlayerRegistry,
                    derivations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    f = _field_cols(p)
    i_player = _first(f, "player_name") if _first(f, "player_name") is not None else _first(f, "bowler_name")
    if i_player is None:
        return []
    i_w = _first(f, "wickets")
    out: list[dict[str, Any]] = []
    for ri, row in enumerate(t.data_rows):
        player = reg.resolve(_cell(row, i_player))
        if not player:
            continue
        wickets = to_int(_cell(row, i_w)) if i_w is not None else None
        if wickets is None:
            derivations.append({"kind": "bowling_row_rejected", "player": player,
                                "reason": "wickets value missing or unparseable",
                                "lineage": row_lineage(t, ri)})
            continue
        rec: dict[str, Any] = {
            "player": player, "team": _str_or_none(_cell(row, _first(f, "team"))),
            "opposition": _str_or_none(_cell(row, _first(f, "opposition"))),
            "competition": _str_or_none(_cell(row, _first(f, "competition"))),
            "season": _str_or_none(_cell(row, _first(f, "season"))),
            "match_id": _str_or_none(_cell(row, _first(f, "match_id"))),
            "venue": _str_or_none(_cell(row, _first(f, "venue"))),
            "innings_number": to_int(_cell(row, _first(f, "innings_number"))),
            "wickets": wickets,
            "runs_conceded": to_int(_cell(row, _first(f, "runs_conceded"))),
            "maidens": to_int(_cell(row, _first(f, "maidens"))),
            "dot_balls": to_int(_cell(row, _first(f, "dot_balls_bowled"))),
            "wides": to_int(_cell(row, _first(f, "wides"))),
            "no_balls": to_int(_cell(row, _first(f, "no_balls"))),
            "best_bowling": _str_or_none(_cell(row, _first(f, "best_bowling"))),
            "legal_balls": None, "overs_value": None, "balls_derived": False,
            "granularity": GRANULARITY_INNINGS, "innings_count": 1, "flags": [],
        }
        innings_count = to_int(_cell(row, _first(f, "innings")))
        if innings_count is not None and innings_count > 1:
            rec["granularity"] = GRANULARITY_AGGREGATE
            rec["innings_count"] = innings_count

        # --- overs: cricket notation, never decimal arithmetic ---
        legal_balls = to_int(_cell(row, _first(f, "legal_balls")))
        overs_raw = _cell(row, _first(f, "overs"))
        if legal_balls is not None:
            rec["legal_balls"] = legal_balls
            rec["overs_value"] = overs_raw if not is_nullish(overs_raw) else None
        elif not is_nullish(overs_raw):
            balls, err = parse_overs(overs_raw)
            rec["overs_value"] = str(overs_raw)
            if err:
                rec["flags"].append("invalid_overs")
                derivations.append({"kind": "invalid_overs", "player": player, "reason": err,
                                    "lineage": row_lineage(t, ri)})
            else:
                rec["legal_balls"] = balls
        else:
            econ = to_float(_cell(row, _first(f, "economy")))
            rc = rec["runs_conceded"]
            if econ and rc and econ > 0:
                rec["legal_balls"] = int(round(rc * 6 / econ))
                rec["balls_derived"] = True
                derivations.append({"kind": "balls_from_economy", "player": player,
                                    "basis": "runs_conceded*6/economy", "accuracy": "approx",
                                    "lineage": row_lineage(t, ri)})

        if rec["runs_conceded"] is None:
            econ = to_float(_cell(row, _first(f, "economy")))
            if econ is not None and rec["legal_balls"]:
                rec["runs_conceded"] = int(round(econ * rec["legal_balls"] / 6))
                rec["flags"].append("runs_conceded_derived")
                derivations.append({"kind": "runs_conceded_from_economy", "player": player,
                                    "basis": "economy*balls/6", "accuracy": "approx",
                                    "lineage": row_lineage(t, ri)})
        rec["lineage"] = row_lineage(t, ri)
        rec["source_file"] = rec["lineage"]["source_file"]
        rec["worksheet"] = rec["lineage"]["worksheet"]
        rec["source_row"] = rec["lineage"]["source_row"]
        rec["record_id"] = _rid("bowl", t.source_path, t.table_name, ri, player, rec["season"])
        out.append(rec)
    return out


# ---------------------------------------------------------------------------
# Ball-by-ball extraction + reduction to innings records
# ---------------------------------------------------------------------------
BALL_EVENT_SCHEMA = {
    "batter": pl.Utf8, "bowler": pl.Utf8, "team_batting": pl.Utf8, "team_bowling": pl.Utf8,
    "competition": pl.Utf8, "season": pl.Utf8, "match_id": pl.Utf8, "innings_number": pl.Int32,
    "over_number": pl.Int32, "ball_number": pl.Int32, "batter_runs": pl.Int32,
    "extras": pl.Int32, "is_wicket": pl.Boolean, "wicket_type": pl.Utf8,
    "target": pl.Int32, "source_file": pl.Utf8, "source_row": pl.Int32,
    "phase": pl.Utf8, "legal_delivery": pl.Boolean, "batter_ball": pl.Boolean,
    "bowler_runs": pl.Int32, "bowler_wicket": pl.Boolean,
}


def extract_ball_events(t: RawTable, p: TableProfile, reg: PlayerRegistry) -> pl.DataFrame | None:
    f = _field_cols(p)
    i_bat = _first(f, "batter_name") or _first(f, "player_name")
    i_bowl = _first(f, "bowler_name")
    if i_bat is None or i_bowl is None:
        return None
    rows: list[dict[str, Any]] = []
    for ri, row in enumerate(t.data_rows):
        batter = reg.resolve(_cell(row, i_bat))
        bowler = reg.resolve(_cell(row, i_bowl))
        if not batter or not bowler:
            continue
        over = to_int(_cell(row, _first(f, "over_number")))
        inns = to_int(_cell(row, _first(f, "innings_number"))) or 1
        batter_runs = to_int(_cell(row, _first(f, "batter_runs")))
        runs_total = to_int(_cell(row, _first(f, "runs")))
        extras = to_int(_cell(row, _first(f, "extras")))
        extras = extras or 0
        if batter_runs is None and runs_total is not None:
            batter_runs = max(0, runs_total - extras)
        raw_extra_type = _str_or_none(_cell(row, _first(f, "extras_type")))
        extra_type = re.sub(r"[^a-z]+", " ", (raw_extra_type or "").lower()).strip()
        wide_count = to_int(_cell(row, _first(f, "wides")))
        no_ball_count = to_int(_cell(row, _first(f, "no_balls")))
        is_wide = bool((wide_count or 0) > 0 or "wide" in extra_type.split())
        is_no_ball = bool((no_ball_count or 0) > 0 or "no ball" in extra_type)
        known_legal_extra = any(token in extra_type for token in ("bye", "leg bye", "penalty"))
        if is_wide or is_no_ball:
            legal_delivery: bool | None = False
        elif extras == 0 or known_legal_extra:
            legal_delivery = True
        else:
            # A numeric extras total cannot distinguish byes from wides/no-balls.
            legal_delivery = None
        batter_ball: bool | None = False if is_wide else (True if legal_delivery is not None else None)
        bowler_runs: int | None = (int(batter_runs or 0) + extras
                                   if is_wide or is_no_ball else
                                   int(batter_runs or 0) if extras == 0 or known_legal_extra else None)
        wicket_type = _str_or_none(_cell(row, _first(f, "wicket_type")))
        dismissed = bool(_is_not_out_flag(_cell(row, _first(f, "is_wicket"))) or wicket_type)
        wicket_key = re.sub(r"[^a-z]+", " ", (wicket_type or "").lower()).strip()
        uncredited = ("run out" in wicket_key or "retired hurt" in wicket_key
                      or "retired out" in wicket_key or "timed out" in wicket_key
                      or "obstructing the field" in wicket_key or "handled the ball" in wicket_key)
        credited_types = ("bowled", "caught", "lbw", "stumped", "hit wicket",
                          "hit the ball twice", "hit ball twice")
        bowler_wicket: bool | None = (not uncredited if uncredited else
                                      True if any(token in wicket_key for token in credited_types) else
                                      None if dismissed else False)
        rows.append({
            "batter": batter, "bowler": bowler,
            "team_batting": _str_or_none(_cell(row, _first(f, "team"))),
            "team_bowling": _str_or_none(_cell(row, _first(f, "opposition"))),
            "competition": _str_or_none(_cell(row, _first(f, "competition"))),
            "season": _str_or_none(_cell(row, _first(f, "season"))),
            "match_id": _str_or_none(_cell(row, _first(f, "match_id"))) or f"{t.source_path}:{t.table_name}",
            "innings_number": inns,
            "over_number": over,
            "ball_number": to_int(_cell(row, _first(f, "ball_number"))),
            "batter_runs": batter_runs or 0,
            "extras": extras or 0,
            "is_wicket": bool(_is_not_out_flag(_cell(row, _first(f, "is_wicket"))) or
                              (not is_nullish(_cell(row, _first(f, "wicket_type"))))),
            "wicket_type": _str_or_none(_cell(row, _first(f, "wicket_type"))),
            "target": to_int(_cell(row, _first(f, "target"))),
            "source_file": t.source_path,
            "source_row": t.header_row + 2 + ri,
            "legal_delivery": legal_delivery, "batter_ball": batter_ball,
            "bowler_runs": bowler_runs, "bowler_wicket": bowler_wicket,
        })
    if not rows:
        return None
    df = pl.DataFrame(rows)
    df = df.with_columns([
        pl.when(pl.col("over_number") <= 6).then(pl.lit("powerplay"))
        .when(pl.col("over_number") <= 15).then(pl.lit("middle"))
        .otherwise(pl.lit("death")).alias("phase"),
    ])
    return df


def reduce_ball_events_to_innings(events: pl.DataFrame) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Derive innings-level batting & bowling records from deliveries."""
    # A provider may distinguish "ball faced by the batter" from "legal ball for the
    # bowler" (no-balls are faced but not legal) and "batter dismissed" from "wicket
    # credited to the bowler" (run-outs are not). Fall back to the single flag.
    ball_col = "batter_ball" if "batter_ball" in events.columns else "legal_delivery"
    wkt_col = "batter_dismissed" if "batter_dismissed" in events.columns else "is_wicket"
    bowler_wkt_col = "bowler_wicket" if "bowler_wicket" in events.columns else "is_wicket"
    bat = (
        events.group_by(["match_id", "innings_number", "batter", "team_batting", "competition", "season"])
        .agg([
            pl.col("batter_runs").sum().alias("runs"),
            pl.col(ball_col).sum().alias("balls_faced"),
            (pl.col("is_four").sum() if "is_four" in events.columns
             else (pl.col("batter_runs") == 4).sum()).alias("fours"),
            (pl.col("is_six").sum() if "is_six" in events.columns
             else (pl.col("batter_runs") == 6).sum()).alias("sixes"),
            ((pl.col("batter_runs") == 0) & (~pl.col(wkt_col))).sum().alias("dot_balls_faced"),
            pl.col(wkt_col).sum().alias("_wkts"),
        ])
    )
    bat_rows = []
    for r in bat.to_dicts():
        # a batter can only be dismissed once per innings; more than one wicket
        # against a batter in an innings indicates run-out attribution noise
        dismissed = 1 if r["_wkts"] and r["_wkts"] > 0 else 0
        bat_rows.append({
            "player": r["batter"], "team": r["team_batting"], "opposition": None,
            "competition": r["competition"], "season": r["season"],
            "match_id": r["match_id"], "match_date": None, "venue": None,
            "innings_number": r["innings_number"], "batting_position": None,
            "runs": r["runs"], "balls_faced": r["balls_faced"], "fours": r["fours"],
            "sixes": r["sixes"], "dot_balls_faced": r["dot_balls_faced"],
            "not_outs": 0 if dismissed else 1, "dismissals": dismissed,
            "innings_count": 1, "highest_score": r["runs"],
            "granularity": GRANULARITY_INNINGS, "derived_balls": False,
            "derived_dismissals": False, "flags": ["derived_from_ball_by_ball"],
            "source_file": "derived:ball_events", "worksheet": "derived", "source_row": None,
            "record_id": _rid("derived_bat", r["match_id"], r["innings_number"], r["batter"]),
            "lineage": {"derived_from": "ball_events"},
        })
    # Run-outs can dismiss the non-striker, who is not the batter on that
    # delivery. Preserve that dismissal against the actual dismissed player
    # rather than charging it to (or omitting it from) the striker.
    if "dismissed_batter" in events.columns:
        dismissed = (events.filter(pl.col("dismissed_batter").is_not_null())
                     .select("match_id", "innings_number", pl.col("dismissed_batter").alias("player"),
                             "team_batting", "competition", "season").unique())
        by_key = {(str(r["match_id"]), int(r["innings_number"]), r["player"]): r for r in dismissed.to_dicts()}
        existing = {(str(r["match_id"]), int(r["innings_number"]), r["player"]): r for r in bat_rows}
        for key, ctx in by_key.items():
            if key in existing:
                existing[key]["dismissals"] = 1
                existing[key]["not_outs"] = 0
            else:
                r = {"player": ctx["player"], "team": ctx["team_batting"], "opposition": None,
                     "competition": ctx["competition"], "season": ctx["season"],
                     "match_id": ctx["match_id"], "match_date": None, "venue": None,
                     "innings_number": ctx["innings_number"], "batting_position": None,
                     "runs": 0, "balls_faced": 0, "fours": 0, "sixes": 0, "dot_balls_faced": 0,
                     "not_outs": 0, "dismissals": 1, "innings_count": 1, "highest_score": 0,
                     "granularity": GRANULARITY_INNINGS, "derived_balls": False,
                     "derived_dismissals": False, "flags": ["derived_from_ball_by_ball", "dismissed_as_non_striker"],
                     "source_file": "derived:ball_events", "worksheet": "derived", "source_row": None,
                     "record_id": _rid("derived_bat", *key), "lineage": {"derived_from": "ball_events"}}
                bat_rows.append(r)

    bowl = (
        events.group_by(["match_id", "innings_number", "bowler", "team_bowling", "competition", "season"])
        .agg([
            pl.col("legal_delivery").sum().alias("legal_balls") if "legal_delivery" in events.columns
            else pl.col("batter_ball").sum().alias("legal_balls"),
            pl.col("legal_delivery").is_not_null().all().alias("_legal_known")
            if "legal_delivery" in events.columns else pl.col("batter_ball").is_not_null().all().alias("_legal_known"),
            pl.col("bowler_runs").sum().alias("runs_conceded"),
            pl.col("bowler_runs").is_not_null().all().alias("_runs_known"),
            pl.col(bowler_wkt_col).sum().alias("wickets"),
            pl.col(bowler_wkt_col).is_not_null().all().alias("_wickets_known"),
            ((pl.col("batter_runs") == 0) & (pl.col("extras") == 0)).sum().alias("dot_balls"),
            pl.col("over_number").max().alias("_max_over"),
        ])
    )
    bowl_rows = []
    for r in bowl.to_dicts():
        bowl_rows.append({
            "player": r["bowler"], "team": r["team_bowling"], "opposition": None,
            "competition": r["competition"], "season": r["season"], "match_id": r["match_id"],
            "venue": None, "innings_number": r["innings_number"],
            "wickets": int(r["wickets"] or 0) if r["_wickets_known"] else None,
            "runs_conceded": int(r["runs_conceded"]) if r["_runs_known"] else None,
            "maidens": None, "dot_balls": int(r["dot_balls"]), "wides": None, "no_balls": None,
            "best_bowling": None,
            "legal_balls": int(r["legal_balls"]) if r["_legal_known"] else None,
            "overs_value": None, "balls_derived": False, "granularity": GRANULARITY_INNINGS,
            "innings_count": 1, "flags": ["derived_from_ball_by_ball"],
            "source_file": "derived:ball_events", "worksheet": "derived", "source_row": None,
            "record_id": _rid("derived_bowl", r["match_id"], r["innings_number"], r["bowler"]),
            "lineage": {"derived_from": "ball_events"},
        })
    return bat_rows, bowl_rows


# ---------------------------------------------------------------------------
# Overlap resolution
# ---------------------------------------------------------------------------
def _resolve_granularity_overlap(cd: CanonicalData) -> None:
    """Never sum an aggregate row and the innings rows it summarises.

    Two situations are handled:

    1. The aggregate is explicit (it carries an innings count > 1).
    2. The aggregate is *inferred*: one source file contributes exactly one row
       per player/season while another source contributes several. Summing them
       would double count, so the single-row source is treated as an aggregate and
       excluded — recorded as an auditable decision, never silently.
    """
    for records, label in ((cd.batting, "batting"), (cd.bowling, "bowling")):
        keys_innings: set[tuple] = set()
        for r in records:
            if r.get("granularity") == GRANULARITY_INNINGS:
                keys_innings.add((r.get("player"), str(r.get("competition")), str(r.get("season"))))

        # per (player, competition, season, source) record counts
        groups: dict[tuple, dict[str, list[dict]]] = {}
        for r in records:
            key = (r.get("player"), str(r.get("competition")), str(r.get("season")))
            groups.setdefault(key, {}).setdefault(str(r.get("source_file")), []).append(r)

        supersede: set[int] = set()
        for key, by_source in groups.items():
            if len(by_source) < 2:
                continue
            counts = {src: len(rows) for src, rows in by_source.items()}
            multi = [src for src, n in counts.items() if n >= 2]
            single = [src for src, n in counts.items() if n == 1]
            if not multi or not single:
                continue
            multi_matches = {str(r.get("match_id")) for src in multi for r in by_source[src]
                             if r.get("match_id")}
            for src in single:
                for r in by_source[src]:
                    mid = str(r.get("match_id")) if r.get("match_id") else None
                    if mid and multi_matches and mid not in multi_matches:
                        continue  # genuinely a different match
                    supersede.add(id(r))
                    cd.derivations.append({
                        "kind": "aggregate_row_superseded",
                        "discipline": label, "player": r.get("player"),
                        "competition": r.get("competition"), "season": r.get("season"),
                        "reason": ("a single-row source overlaps an innings-level source for the same "
                                   "player/competition/season and no innings count was supplied; the "
                                   "single row was treated as an aggregate and excluded to avoid "
                                   "double counting"),
                        "lineage": r.get("lineage"),
                    })
        kept = []
        for r in records:
            if id(r) in supersede:
                continue
            key = (r.get("player"), str(r.get("competition")), str(r.get("season")))
            if r.get("granularity") == GRANULARITY_AGGREGATE and key in keys_innings:
                cd.derivations.append({
                    "kind": "aggregate_row_superseded",
                    "discipline": label, "player": r.get("player"),
                    "competition": r.get("competition"), "season": r.get("season"),
                    "reason": "innings-level records exist for this player/competition/season; the "
                              "aggregate row was excluded to avoid double counting",
                    "lineage": r.get("lineage"),
                })
                continue
            kept.append(r)
        records[:] = kept


# ---------------------------------------------------------------------------
# Top-level assembly
# ---------------------------------------------------------------------------
def build_canonical(tables: list[RawTable], profiles: list[TableProfile],
                    include_aggregates: bool = True) -> CanonicalData:
    cd = CanonicalData()
    # Pass 1: registry from every identifiable name so aliases are global.
    name_team: list[tuple[str, str | None]] = []
    for t, p in zip(tables, profiles):
        f = _field_cols(p)
        for key in ("player_name", "batter_name", "bowler_name"):
            idx = _first(f, key)
            if idx is None:
                continue
            # A ball-by-ball "Team" column describes the batting side of the delivery, not the
            # player's own team, so it must never be used for team attribution.
            team_idx = _first(f, "team") if p.record_type != "ball_event" else None
            for row in t.data_rows:
                nm = _cell(row, idx)
                if not is_nullish(nm):
                    name_team.append((str(nm), _str_or_none(_cell(row, team_idx)) if team_idx is not None else None))
    cd.registry = build_player_registry(name_team)

    ball_frames: list[pl.DataFrame] = []
    matches: dict[str, dict[str, Any]] = {}
    for t, p in zip(tables, profiles):
        rt = p.record_type
        try:
            if rt in {"batting", "batting_aggregate", "combined_aggregate"}:
                recs = extract_batting(t, p, cd.registry, cd.derivations)
                if not include_aggregates:
                    recs = [r for r in recs if r["granularity"] == GRANULARITY_INNINGS]
                cd.batting.extend(recs)
            if rt in {"bowling", "bowling_aggregate", "combined_aggregate"}:
                recs_b = extract_bowling(t, p, cd.registry, cd.derivations)
                if not include_aggregates:
                    recs_b = [r for r in recs_b if r["granularity"] == GRANULARITY_INNINGS]
                cd.bowling.extend(recs_b)
            if rt == "ball_event":
                frame = extract_ball_events(t, p, cd.registry)
                if frame is not None:
                    ball_frames.append(frame)
            if rt == "player_register":
                f = _field_cols(p)
                i_name = _first(f, "player_name")
                i_role, i_hand, i_style = (_first(f, "role"), _first(f, "batting_hand"),
                                           _first(f, "bowling_style"))
                for row in t.data_rows:
                    pid = cd.registry.resolve(_cell(row, i_name))
                    if not pid:
                        continue
                    attrs = cd.player_attributes.setdefault(pid, {})
                    for key, idx in (("declared_role", i_role), ("batting_hand", i_hand),
                                     ("bowling_style", i_style)):
                        val = _str_or_none(_cell(row, idx))
                        if val:
                            attrs[key] = val
            if rt == "unknown":
                cd.unmapped_tables.append({
                    "source_path": t.source_path, "table": t.table_name,
                    "rows": len(t.data_rows), "columns": t.columns[:25],
                    "reason": "no cricket record type detected; manual mapping required",
                })
        except Exception as exc:  # a bad table must not kill the dataset
            cd.unmapped_tables.append({
                "source_path": t.source_path, "table": t.table_name,
                "rows": len(t.data_rows), "columns": t.columns[:25],
                "reason": f"extraction failed: {type(exc).__name__}: {exc}",
            })

    _resolve_granularity_overlap(cd)

    if ball_frames:
        events = pl.concat([f.select([c for c in BALL_EVENT_SCHEMA if c in f.columns])
                            for f in ball_frames], how="diagonal_relaxed")
        cd.ball_events = events
        d_bat, d_bowl = reduce_ball_events_to_innings(events)
        cd.batting.extend(d_bat)
        cd.bowling.extend(d_bowl)
        for m in events.select(["match_id", "competition", "season", "team_batting", "target"]).unique().to_dicts():
            matches[m["match_id"]] = m

    _resolve_granularity_overlap(cd)
    cd.matches = list(matches.values())
    cd.capabilities = {
        "batting_records": bool(cd.batting),
        "bowling_records": bool(cd.bowling),
        "ball_by_ball": cd.ball_events is not None,
        "innings_granularity_batting": any(b["granularity"] == GRANULARITY_INNINGS for b in cd.batting),
        "innings_granularity_bowling": any(b["granularity"] == GRANULARITY_INNINGS for b in cd.bowling),
        "aggregate_only_batting": bool(cd.batting) and not any(
            b["granularity"] == GRANULARITY_INNINGS for b in cd.batting),
        "phase_data": cd.ball_events is not None,
        "actual_match_pressure": cd.ball_events is not None,
        "targets_available": bool(matches) and any(m.get("target") is not None for m in matches.values()),
        "venue_data": any(b.get("venue") for b in cd.batting + cd.bowling),
        "opposition_data": any(b.get("opposition") for b in cd.batting + cd.bowling),
    }
    return cd
