"""Schema intelligence: canonical cricket dictionary + automatic column mapping.

Design rules (see PART 4 of the brief):
* aliases are *suggestions*, never assumptions;
* every guess carries a confidence and its evidence;
* two plausible canonical fields within `ambiguous_margin` => human review;
* nothing is silently coerced.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

FieldType = Literal["string", "int", "float", "date", "bool"]

ENTITY_FIELDS: dict[str, list[str]] = {
    "player": ["player_name"],
    "match": ["match_id", "match_date", "venue", "competition", "season", "team", "opposition", "innings_number"],
    "batting": ["runs", "balls_faced", "fours", "sixes", "dismissal", "not_out", "strike_rate", "batting_average"],
    "bowling": ["wickets", "overs", "runs_conceded", "economy", "maidens", "bowling_average", "bowling_strike_rate"],
    "ball_event": ["over_number", "ball_number", "batter_runs", "bowler_name", "extras", "wicket_type"],
    "aggregate": ["matches", "innings"],
}


@dataclass(frozen=True)
class CanonicalField:
    name: str
    dtype: FieldType
    entity: str
    aliases: tuple[str, ...]
    description: str
    required_for: tuple[str, ...] = ()  # record types for which absence blocks that type
    derived_from: tuple[str, ...] = ()  # mathematically derivable from these fields
    unit: str | None = None
    notes: str = ""


# --------------------------------------------------------------------------
# The dictionary. Aliases are drawn from observed Indian domestic / IPL / state
# association exports (BCCI-style scorecards, CricketArchive-style aggregates).
# --------------------------------------------------------------------------
FIELDS: tuple[CanonicalField, ...] = (
    # ---------------- identity ----------------
    CanonicalField("player_name", "string", "player",
                   ("player", "player name", "name", "batter", "batsman", "bowler", "cricketer",
                    "full name", "player full name", "athlete", "player_name", "ply", "player name (full)",
                    "batsmen", "bowlers"),
                   "Canonical player name as printed in the source", ("batting", "bowling", "ball_event")),
    CanonicalField("player_short_name", "string", "player",
                   ("short name", "display name", "initials"), "Abbreviated player name"),
    CanonicalField("team", "string", "match",
                   ("team", "state", "association", "state team", "state association", "team name",
                    "representing", "side", "squad", "team1", "team_state", "domestic team"),
                   "Player's own team / state association", ("batting", "bowling"), unit=None),
    CanonicalField("opposition", "string", "match",
                   ("opposition", "opponent", "opp", "vs", "versus", "against", "opponent team",
                    "opposition team", "opp_team"),
                   "Opposing team"),
    CanonicalField("batter_name", "string", "ball_event",
                   ("batter", "batsman", "striker", "batter name", "striker name", "batsman name", "bat"),
                   "Batter on strike for a ball event"),
    CanonicalField("bowler_name", "string", "ball_event",
                   ("bowler", "bowler name", "bowl", "bowler_name", "bowling"),
                   "Bowler for a ball event"),
    CanonicalField("non_striker_name", "string", "ball_event",
                   ("non striker", "non-striker", "nonstriker", "non striker name"),
                   "Non-striker for a ball event"),
    # ---------------- competition context ----------------
    CanonicalField("competition", "string", "match",
                   ("competition", "tournament", "league", "series", "event", "competition name",
                    "tournament name", "league name", "cup"),
                   "Competition / tournament name"),
    CanonicalField("season", "string", "match",
                   ("season", "year", "edition", "season year", "session", "yr", "season/year"),
                   "Season or year identifier"),
    CanonicalField("match_format", "string", "match",
                   ("format", "match format", "match type", "type", "game type", "overs format", "t20/t50"),
                   "Match format (T20, ODI, First-class, ...)"),
    CanonicalField("match_id", "string", "match",
                   ("match id", "matchid", "match no", "match number", "fixture", "fixture id", "game id",
                    "match_id", "mid"),
                   "Unique match identifier in the source"),
    CanonicalField("match_date", "date", "match",
                   ("date", "match date", "start date", "played on", "match_date", "dt", "date of match"),
                   "Date the match started"),
    CanonicalField("venue", "string", "match",
                   ("venue", "ground", "stadium", "location", "city", "venue name", "ground name"),
                   "Venue / ground"),
    CanonicalField("innings_number", "int", "match",
                   ("innings", "innings no", "innings number", "inns", "inning", "innings_no"),
                   "Innings ordinal within the match"),
    CanonicalField("batting_position", "int", "batting",
                   ("batting position", "bat pos", "position", "batting order", "order", "bat_order"),
                   "Order in which the batter came to the crease"),
    CanonicalField("result", "string", "match",
                   ("result", "result type", "outcome", "winner", "match result"),
                   "Match outcome"),
    # ---------------- batting ----------------
    CanonicalField("runs", "int", "batting",
                   ("runs", "total runs", "batter runs", "runs scored", "runs made", "r", "runs_total",
                    "batting runs", "score"),
                   "Runs credited to the batter", ("batting",)),
    CanonicalField("balls_faced", "int", "batting",
                   ("balls", "balls faced", "deliveries", "balls_faced", "bf", "b", "balls consumed",
                    "deliveries faced"),
                   "Legal + illegal balls faced by the batter", unit="balls"),
    CanonicalField("fours", "int", "batting",
                   ("4s", "fours", "four", "boundaries four", "no of 4s", "num 4s", "fours hit"),
                   "Number of fours"),
    CanonicalField("sixes", "int", "batting",
                   ("6s", "sixes", "six", "no of 6s", "num 6s", "sixes hit"),
                   "Number of sixes"),
    CanonicalField("not_out", "bool", "batting",
                   ("not out", "notout", "not_out", "no", "is not out", "dismissed", "out/not out"),
                   "True when the batter finished unbeaten"),
    CanonicalField("dismissal", "string", "batting",
                   ("dismissal", "dismissal type", "how out", "wicket type", "mode of dismissal", "dismissal kind"),
                   "Mode of dismissal ('not out' / blank means unbeaten)"),
    CanonicalField("strike_rate", "float", "batting",
                   ("strike rate", "sr", "s/r", "strikerate", "batting strike rate", "strike_rate"),
                   "Runs per 100 balls", unit="runs/100 balls",
                   derived_from=("runs", "balls_faced")),
    CanonicalField("batting_average", "float", "batting",
                   ("average", "avg", "batting average", "ave", "bat avg", "average_runs"),
                   "Runs per dismissal", unit="runs/dismissal", derived_from=("runs", "dismissals")),
    CanonicalField("highest_score", "string", "batting",
                   ("highest score", "hs", "high score", "best", "highest", "best score", "hs*"),
                   "Highest innings score, retaining the * for not out"),
    CanonicalField("dismissals", "int", "batting",
                   ("dismissals", "times out", "outs", "no of dismissals", "wickets lost"),
                   "Number of completed dismissals", unit="dismissals",
                   derived_from=("innings", "not_outs")),
    CanonicalField("not_outs", "int", "batting",
                   ("not outs", "notouts", "no_", "unbeaten", "not out count"),
                   "Number of unbeaten innings"),
    CanonicalField("ducks", "int", "batting", ("ducks", "duck", "0s"), "Innings dismissed for zero"),
    CanonicalField("dot_balls_faced", "int", "batting",
                   ("dot balls", "dots", "dot ball faced", "dot_balls", "dot balls faced"),
                   "Balls from which the batter scored no run", unit="balls"),
    # ---------------- bowling ----------------
    CanonicalField("overs", "float", "bowling",
                   ("overs", "overs bowled", "bowling overs", "ov", "o", "overs_bowled", "over"),
                   "Overs as written in the source (cricket notation, NOT decimal)", unit="overs"),
    CanonicalField("legal_balls", "int", "bowling",
                   ("legal balls", "balls bowled", "deliveries bowled", "legal_balls", "b_f", "balls_bowled"),
                   "Legal deliveries bowled", unit="balls"),
    CanonicalField("runs_conceded", "int", "bowling",
                   ("runs conceded", "runs given", "runs against", "conceded", "runs_conceded", "rc",
                    "runs conceded total", "runs"),
                   "Runs charged to the bowler", ("bowling",), unit="runs"),
    CanonicalField("wickets", "int", "bowling",
                   ("wickets", "wkts", "w", "wickets taken", "dismissals by bowler", "no of wickets"),
                   "Wickets credited to the bowler", ("bowling",)),
    CanonicalField("economy", "float", "bowling",
                   ("economy", "econ", "economy rate", "econ rate", "eco", "economy_rate"),
                   "Runs conceded per over", unit="runs/over", derived_from=("runs_conceded", "overs")),
    CanonicalField("bowling_average", "float", "bowling",
                   ("bowling average", "bowl avg", "avg bowl", "average (bowling)", "bowling_average"),
                   "Runs conceded per wicket", unit="runs/wicket", derived_from=("runs_conceded", "wickets")),
    CanonicalField("bowling_strike_rate", "float", "bowling",
                   ("bowling strike rate", "bowl sr", "strike rate (bowling)", "bowling_sr", "bwl sr"),
                   "Balls per wicket", unit="balls/wicket", derived_from=("legal_balls", "wickets")),
    CanonicalField("maidens", "int", "bowling",
                   ("maidens", "maiden", "maidens bowled", "m"), "Maiden overs"),
    CanonicalField("best_bowling", "string", "bowling",
                   ("best bowling", "best", "bb", "best figures", "bbi", "best bowling figures"),
                   "Best innings figures, e.g. 4/23"),
    CanonicalField("dot_balls_bowled", "int", "bowling",
                   ("dot balls bowled", "dots bowled", "dot ball", "dot_balls_bowled", "dot balls conceded"),
                   "Dot balls delivered", unit="balls"),
    CanonicalField("wides", "int", "bowling", ("wides", "wide", "wd"), "Wides conceded"),
    CanonicalField("no_balls", "int", "bowling", ("no balls", "noballs", "nb"), "No-balls conceded"),
    # ---------------- ball events ----------------
    CanonicalField("over_number", "int", "ball_event",
                   ("over", "over number", "over_no", "ovr", "over num"),
                   "Over index of a delivery (1-based)"),
    CanonicalField("ball_number", "int", "ball_event",
                   ("ball", "ball number", "ball_no", "delivery", "ball num"),
                   "Ball within the over (1-based, legal balls)"),
    CanonicalField("batter_runs", "int", "ball_event",
                   ("batter runs", "runs off bat", "batsman runs", "runs scored off bat", "bat runs"),
                   "Runs scored off the bat on the delivery"),
    CanonicalField("extras", "int", "ball_event",
                   ("extras", "extra runs", "extras total"),
                   "Extras on the delivery (never attributed to the batter)"),
    CanonicalField("extras_type", "string", "ball_event",
                   ("extras type", "extra type", "extra kind", "extras kind", "type of extras"),
                   "Delivery extra classification (wide, no-ball, bye, leg-bye, penalty)"),
    CanonicalField("is_wicket", "bool", "ball_event",
                   ("wicket", "is wicket", "wicket flag", "wkt"), "Delivery produced a dismissal"),
    CanonicalField("wicket_type", "string", "ball_event",
                   ("wicket type", "dismissal kind", "how out", "dismissal type", "kind"),
                   "Dismissal type on the delivery"),
    CanonicalField("target", "int", "match",
                   ("target", "target runs", "runs to win", "target_score"),
                   "Runs required by the chasing side"),
    CanonicalField("required_runs", "int", "ball_event",
                   ("required runs", "runs required", "runs left", "runs_required"),
                   "Runs still required at the point of the delivery"),
    CanonicalField("required_run_rate", "float", "ball_event",
                   ("required run rate", "rrr", "required rate", "req rate"),
                   "Runs per over required at the point of the delivery"),
    CanonicalField("current_run_rate", "float", "ball_event",
                   ("current run rate", "crr", "run rate", "current rate"),
                   "Runs per over achieved so far"),
    # ---------------- aggregates ----------------
    CanonicalField("matches", "int", "aggregate",
                   ("matches", "mat", "m", "games", "matches played", "no of matches", "appearances"),
                   "Matches in which the player appeared", unit="matches"),
    CanonicalField("innings", "int", "aggregate",
                   ("innings", "inns", "i", "innings played", "no of innings", "inn"),
                   "Innings in which the player participated"),
    CanonicalField("catches", "int", "aggregate", ("catches", "ct", "catches taken"), "Catches taken"),
    CanonicalField("stumpings", "int", "aggregate", ("stumpings", "st", "stumped"), "Stumpings effected"),
    CanonicalField("run_outs", "int", "aggregate", ("run outs", "runout", "ro"), "Run-outs effected"),
    CanonicalField("role", "string", "player",
                   ("role", "player role", "primary role", "player type", "designation", "skill"),
                   "Declared player role, if the source states one"),
    CanonicalField("bowling_style", "string", "player",
                   ("bowling style", "bowl style", "bowling type", "pace/spin", "style"),
                   "Declared bowling style"),
    CanonicalField("batting_hand", "string", "player",
                   ("batting hand", "bats", "handedness", "bat hand", "batsman hand"),
                   "Declared batting hand"),
    CanonicalField("age", "int", "player", ("age",), "Age at time of record"),
)

FIELD_INDEX: dict[str, CanonicalField] = {f.name: f for f in FIELDS}

# Columns that must never be inferred from a same-named money/other table.
_NON_MATCHING = re.compile(r"^(unnamed.*|index|s\.?no\.?|sr\.? no\.?|#)$", re.I)


def normalise(name: str) -> str:
    """Lower-case, strip punctuation/units, collapse whitespace."""
    s = str(name).strip().lower()
    s = s.replace("%", " pct ").replace("*", " ").replace("/", " ").replace("-", " ")
    s = re.sub(r"[^a-z0-9. ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


@dataclass
class MappingCandidate:
    column: str
    field: str
    confidence: float
    method: str
    dtype: str
    samples: list[Any] = field(default_factory=list)
    required: bool = False
    ambiguous_with: list[str] = field(default_factory=list)
    needs_review: bool = False
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "column": self.column,
            "field": self.field,
            "confidence": round(self.confidence, 3),
            "method": self.method,
            "dtype": self.dtype,
            "samples": [str(s)[:48] for s in self.samples[:5]],
            "required": self.required,
            "ambiguous_with": self.ambiguous_with,
            "needs_review": self.needs_review,
            "evidence": self.evidence,
        }


#: The first two aliases of each field are its *primary* names. A bare "Runs"
#: column is the canonical batting field, not bowling runs conceded; treating
#: primary and secondary aliases as equally strong is what produced spurious
#: ambiguity, so primary matches score higher and ambiguity is only raised
#: between two comparably specific candidates.
PRIMARY_ALIAS_COUNT = 2


def _score_column(column: str, canonical: CanonicalField, cfg_margin: float) -> tuple[float, str]:
    norm = normalise(column)
    if _NON_MATCHING.match(norm):
        return 0.0, ""
    alias_list = [normalise(a) for a in canonical.aliases]
    aliases = set(alias_list)
    primary = set(alias_list[:PRIMARY_ALIAS_COUNT])
    if norm in primary:
        return 1.0, "exact alias"
    if norm in aliases:
        return 0.88, "exact alias (secondary)"
    # normalised containment: "total runs" vs "runs scored" etc.
    if any(norm == a or norm.replace(" ", "") == a.replace(" ", "") for a in aliases):
        return 0.92, "normalised alias"
    field_norm = normalise(canonical.name)
    if norm == field_norm:
        return 0.97, "canonical name"
    best = 0.0
    best_alias = ""
    for a in aliases | {field_norm}:
        ratio = difflib.SequenceMatcher(None, norm, a).ratio()
        # token containment bonus ("batter runs" vs "runs")
        if norm and (f" {norm} " in f" {a} " or f" {a} " in f" {norm} "):
            ratio = max(ratio, 0.85)
        if ratio > best:
            best, best_alias = ratio, a
    if best >= 0.72:
        return best, f"fuzzy ~ '{best_alias}'"
    return 0.0, ""


def map_columns(
    columns: Iterable[str],
    samples: dict[str, list[Any]] | None = None,
    config_margin: float = 0.06,
    fuzzy_floor: float = 0.72,
) -> list[MappingCandidate]:
    """Map every raw column to at most one canonical field, with confidence."""
    samples = samples or {}
    out: list[MappingCandidate] = []
    used: dict[str, int] = {}
    for col in columns:
        scored: list[tuple[float, str, str]] = []
        for f in FIELDS:
            sc, ev = _score_column(col, f, config_margin)
            if sc >= fuzzy_floor:
                scored.append((sc, f.name, ev))
        scored.sort(reverse=True)
        if not scored:
            out.append(MappingCandidate(
                column=col, field="", confidence=0.0, method="none", dtype="unknown",
                samples=samples.get(col, []), evidence="no alias matched", needs_review=True))
            continue
        top = scored[0]
        ambiguous = [s[1] for s in scored[1:] if top[0] - s[0] <= config_margin]
        cand = MappingCandidate(
            column=col, field=top[1], confidence=top[0], method=top[2],
            dtype=FIELD_INDEX[top[1]].dtype,
            samples=samples.get(col, []),
            ambiguous_with=ambiguous, evidence=top[2])
        if ambiguous:
            cand.needs_review = True
        used[top[1]] = used.get(top[1], 0) + 1
        out.append(cand)

    # Duplicate assignment of a single-valued canonical field is a red flag.
    for cand in out:
        if used.get(cand.field, 0) > 1:
            cand.needs_review = True
            cand.evidence += " | duplicate target field"
        if cand.field in FIELD_INDEX:
            cand.required = cand.field in {"player_name", "runs", "wickets", "overs"}
    return out


# --------------------------------------------------------------------------
# Contextual disambiguation
# --------------------------------------------------------------------------
MATCH_CONTEXT_FIELDS = {"match_id", "match_date", "venue", "opposition"}
AGGREGATE_MARKERS = {"matches", "not_outs", "batting_average", "highest_score", "bowling_average",
                     "economy", "maidens", "best_bowling", "strike_rate"}


def apply_contextual_rules(mapped: list[MappingCandidate]) -> tuple[list[MappingCandidate], list[dict]]:
    """Resolve ambiguity that only the surrounding columns can settle.

    A bare "Innings" column is an innings *count* in an aggregate export and an
    innings *ordinal* in a match-level export. "Avg" is a batting average in a
    batting table and a bowling average in a bowling table. These decisions are
    recorded so they appear in the schema report instead of being invisible.
    """
    fields = {m.field for m in mapped if m.field}
    bowling_orientation = bool({"wickets", "overs"} & fields) and "wickets" in fields
    batting_evidence = bool(fields & {"fours", "sixes", "not_outs", "ducks", "batting_average",
                                      "highest_score", "dot_balls_faced", "batting_position"})
    has_match_context = bool(fields & MATCH_CONTEXT_FIELDS)
    has_aggregate_markers = bool(fields & AGGREGATE_MARKERS)
    bowling_only = bowling_orientation and not batting_evidence

    adjustments: list[dict] = []
    rules: list[tuple[str, str, str, bool]] = [
        # (from_field, to_field, condition description, condition)
        ("innings_number", "innings", "no match-level columns but aggregate markers present",
         (not has_match_context) and (has_aggregate_markers or bowling_orientation)),
        ("batting_average", "bowling_average", "bowling-oriented table", bowling_only),
        ("strike_rate", "bowling_strike_rate", "bowling-oriented table", bowling_only),
        ("balls_faced", "legal_balls", "bowling-oriented table", bowling_only),
        ("runs", "runs_conceded", "bowling-oriented table", bowling_only),
        ("highest_score", "best_bowling", "bowling-oriented table", bowling_only),
    ]
    for m in mapped:
        for src, dst, why, cond in rules:
            if m.field == src and cond and dst not in fields:
                adjustments.append({"column": m.column, "from": src, "to": dst, "reason": why})
                m.field = dst
                m.dtype = FIELD_INDEX[dst].dtype
                m.evidence = f"{m.evidence} | contextual remap -> {dst} ({why})"
                m.needs_review = False
                m.ambiguous_with = []
                fields.discard(src)
                fields.add(dst)
                break
    return mapped, adjustments


# --------------------------------------------------------------------------
# Record-type hypotheses
# --------------------------------------------------------------------------
@dataclass
class RecordTypeHypothesis:
    record_type: str
    score: float
    matched: list[str]
    missing: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {"record_type": self.record_type, "score": round(self.score, 3),
                "matched": self.matched, "missing": self.missing}


def detect_record_type(mapped: list[MappingCandidate], multi_valued: set[str] | None = None) -> list[RecordTypeHypothesis]:
    """Score plausible record types for a table.

    `multi_valued` holds canonical fields assignable more than once (e.g. both a
    batter and a bowler column map to player_name) — used for ball-by-ball.

    A table is only treated as a *combined* batting+bowling aggregate when it
    carries strong, distinct evidence for BOTH disciplines. A bowling summary
    with a "Runs" column must never be mined for batting records.
    """
    present = {c.field for c in mapped if c.field}
    if multi_valued:
        present |= multi_valued
    hyps: list[RecordTypeHypothesis] = []

    batting_specific = {"balls_faced", "fours", "sixes", "not_out", "dismissal", "strike_rate",
                        "batting_average", "highest_score", "not_outs", "ducks", "dot_balls_faced"}
    bowling_specific = {"overs", "legal_balls", "economy", "maidens", "bowling_average",
                        "bowling_strike_rate", "dot_balls_bowled", "best_bowling", "wides", "no_balls",
                        "runs_conceded", "best_bowling"}
    bat_evidence = len(present & batting_specific)
    bowl_evidence = len(present & bowling_specific)
    has_runs = "runs" in present
    has_wickets = "wickets" in present

    def add(rt: str, required: list[str], bonus: list[str], weight: float = 1.0) -> None:
        got = [f for f in required if f in present]
        missing = [f for f in required if f not in present]
        if not got:
            return
        base = len(got) / len(required)
        extra = len([b for b in bonus if b in present]) / max(1, len(bonus))
        score = (0.8 * base + 0.2 * extra) * weight
        hyps.append(RecordTypeHypothesis(rt, score, got, missing))

    add("ball_event", ["batter_name", "bowler_name", "over_number"],
        ["batter_runs", "is_wicket", "extras", "wicket_type", "ball_number"])
    add("bowling", ["wickets", "overs"], ["economy", "runs_conceded", "maidens", "bowling_average"])
    add("batting", ["runs"], ["balls_faced", "fours", "sixes", "not_out", "dismissal", "strike_rate"])
    add("batting_aggregate", ["runs", "innings"], ["matches", "not_outs", "batting_average", "highest_score"])
    add("bowling_aggregate", ["wickets", "overs"], ["matches", "economy", "maidens", "bowling_average"])
    add("player_register", ["player_name", "role"], ["batting_hand", "bowling_style", "age"])

    # Combined table only with independent evidence for both disciplines.
    if has_runs and has_wickets and bat_evidence >= 2 and bowl_evidence >= 2:
        # a genuinely combined export must beat both single-discipline hypotheses
        hyps.append(RecordTypeHypothesis("combined_aggregate", 0.94,
                                         ["runs", "wickets"], []))
    elif has_wickets and bowl_evidence > bat_evidence:
        # suppress a runs-column false positive for the batting hypotheses
        for h in hyps:
            if h.record_type.startswith("batting"):
                h.score *= 0.55
    elif has_runs and bat_evidence > bowl_evidence:
        for h in hyps:
            if h.record_type.startswith("bowling"):
                h.score *= 0.55

    hyps.sort(key=lambda h: (-h.score, h.record_type))
    return hyps


def pick_record_type(hyps: list[RecordTypeHypothesis], floor: float = 0.34) -> str:
    if not hyps:
        return "unknown"
    top = hyps[0]
    if top.score < floor:
        return "unknown"
    # ball_event wins ties: it is strictly more informative.
    if any(h.record_type == "ball_event" and h.score >= top.score - 0.05 for h in hyps):
        return "ball_event"
    return top.record_type


# --------------------------------------------------------------------------
# Value coercion (never silent: every rejection is reported)
# --------------------------------------------------------------------------
_NULLISH = {"", "-", "--", "na", "n/a", "nan", "null", "none", "?", "dnb", "did not bat", "absent"}


def is_nullish(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and v != v:  # NaN
        return True
    return str(v).strip().lower() in _NULLISH


def to_int(v: Any) -> int | None:
    if is_nullish(v):
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int,)):
        return int(v)
    if isinstance(v, float):
        return int(v) if v == int(v) else None
    s = str(v).strip().replace(",", "")
    m = re.match(r"^-?\d+", s)
    if m:
        return int(m.group(0))
    try:
        f = float(s)
        return int(f) if f == int(f) else None
    except ValueError:
        return None


def to_float(v: Any) -> float | None:
    if is_nullish(v):
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    s = str(v).strip().replace(",", "").replace("%", "")
    try:
        return float(s)
    except ValueError:
        return None


def parse_overs(v: Any) -> tuple[int | None, str | None]:
    """Cricket-notation overs -> legal balls. Returns (balls, error).

    "12.4" means 12 overs and 4 balls == 76 balls. It is NOT 12.4 overs.
    Illegal / ambiguous inputs are rejected with a reason instead of guessed.
    """
    if is_nullish(v):
        return None, None
    s = str(v).strip().replace(",", "")
    m = re.match(r"^(\d+)(?:\.(\d))?\s*(?:ov|overs)?$", s, re.I)
    if not m:
        return None, f"unparseable overs value '{v}'"
    overs = int(m.group(1))
    balls = int(m.group(2) or 0)
    if balls > 5:
        return None, f"illegal overs notation '{v}' (minor part must be 0-5)"
    return overs * 6 + balls, None
