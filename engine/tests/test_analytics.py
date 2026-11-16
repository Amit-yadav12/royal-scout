"""Analytics tests against hand-calculated expectations.

Every expected number below is computed by hand from the fixture rows in
tests/fixtures/make_fixtures.py. If a definition changes, these tests fail.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from royalscout.batting import compute_batting_raw, score_batting_population
from royalscout.bowling import compute_bowling_raw, overs_display
from royalscout.canonical import build_canonical
from royalscout.config import DEFAULT_CONFIG, Config
from royalscout.ingest import profile_table, read_file
from royalscout.pipeline import run_pipeline
from royalscout.quality import run_quality_audit
from royalscout.ranking import build_leaderboard, eligibility_bat
from royalscout.schema import apply_contextual_rules, map_columns, parse_overs
from royalscout.stats import (composite, confidence_grade, consistency_from_cv, percentile_rank,
                              shrink)

FIXTURES = Path(__file__).parent / "fixtures" / "generated"


# ---------------------------------------------------------------- overs / units
def test_overs_are_cricket_notation_not_decimals() -> None:
    assert parse_overs("3.4") == (22, None)
    assert parse_overs("4") == (24, None)
    assert parse_overs("0.5") == (5, None)
    assert parse_overs("12.0") == (72, None)
    balls, err = parse_overs("3.7")
    assert balls is None and "illegal overs" in err
    assert parse_overs("abc")[0] is None


def test_overs_display_roundtrip() -> None:
    assert overs_display(22) == "3.4"
    assert overs_display(24) == "4.0"
    assert overs_display(120) == "20.0"


# ---------------------------------------------------------------- column mapping
def test_column_mapping_confidence_and_ambiguity() -> None:
    mapped = map_columns(["Player", "Total Runs", "Balls Faced", "Economy", "Mystery Column"])
    by_col = {m.column: m for m in mapped}
    assert by_col["Player"].field == "player_name"
    assert by_col["Player"].confidence == 1.0
    assert by_col["Total Runs"].field == "runs"
    assert by_col["Balls Faced"].field == "balls_faced"
    assert by_col["Economy"].field == "economy"
    assert by_col["Mystery Column"].field == "" and by_col["Mystery Column"].needs_review


def test_contextual_disambiguation_innings_vs_innings_number() -> None:
    aggregate = map_columns(["Player", "Innings", "Runs", "Not Outs", "Average"])
    fixed, adjustments = apply_contextual_rules(aggregate)
    fields = {m.column: m.field for m in fixed}
    assert fields["Innings"] == "innings"
    assert adjustments and adjustments[0]["to"] == "innings"

    match_level = map_columns(["Player", "Innings", "Runs", "Match ID", "Venue"])
    fixed2, adjustments2 = apply_contextual_rules(match_level)
    assert {m.column: m.field for m in fixed2}["Innings"] == "innings_number"
    assert not adjustments2


def test_bowling_table_runs_remapped_to_runs_conceded() -> None:
    mapped = map_columns(["Bowler", "Overs", "Runs", "Wickets", "Economy"])
    fixed, _ = apply_contextual_rules(mapped)
    fields = {m.column: m.field for m in fixed}
    assert fields["Runs"] == "runs_conceded"
    assert fields["Economy"] == "economy"


# ---------------------------------------------------------------- batting maths
def _bat_records() -> list[dict]:
    tables, profiles = [], []
    for name in ("batting_innings.csv",):
        for t in read_file(FIXTURES / name, name, DEFAULT_CONFIG.limits):
            t.source_path = name
            tables.append(t)
            profiles.append(profile_table(t))
    return build_canonical(tables, profiles).batting


def test_batting_totals_match_hand_calculation() -> None:
    raw = compute_batting_raw(_bat_records())
    opener = raw["Fixture Opener"]
    # 50+30+0+45+60+22 = 207 runs off 40+20+2+35+40+15 = 152 balls
    assert opener.runs == 207
    assert opener.balls == 152
    assert opener.innings == 6
    assert opener.not_outs == 2
    assert opener.dismissals == 4
    assert opener.average == pytest.approx(207 / 4)
    assert opener.strike_rate == pytest.approx(207 * 100 / 152)
    assert opener.highest == 60
    assert sorted(opener.scores) == [0, 22, 30, 45, 50, 60]
    assert opener.boundary_runs == 4 * 21 + 6 * 7

    anchor = raw["Fixture Anchor"]
    assert anchor.runs == 218 and anchor.balls == 215
    assert anchor.average == pytest.approx(218 / 4)
    assert anchor.strike_rate == pytest.approx(218 * 100 / 215)

    finisher = raw["Fixture Finisher"]
    assert finisher.runs == 142 and finisher.balls == 59
    assert finisher.dismissals == 3
    assert finisher.average == pytest.approx(142 / 3)


def test_scores_counts_and_ducks() -> None:
    from royalscout.batting import score_batting_population
    scored = score_batting_population(compute_batting_raw(_bat_records()), DEFAULT_CONFIG)
    opener = scored["Fixture Opener"]
    assert opener["scores_30"] == 4          # 50, 30, 45, 60
    assert opener["scores_50"] == 2          # 50, 60
    assert opener["scores_100"] == 0
    assert opener["ducks"] == 1              # the 0(2)
    assert opener["boundary_pct"] == pytest.approx(100 * (4 * 21 + 6 * 7) / 207, abs=0.01)


def test_not_out_handling_never_inflates_average() -> None:
    raw = compute_batting_raw(_bat_records())
    # Finisher has 3 not-outs; a naive "innings as dismissals" average would be 142/6
    assert raw["Fixture Finisher"].average == pytest.approx(142 / 3)
    assert raw["Fixture Finisher"].average != pytest.approx(142 / 6)


# ---------------------------------------------------------------- bowling maths
def _bowl_records() -> list[dict]:
    tables, profiles = [], []
    for t in read_file(FIXTURES / "bowling_innings.csv", "b.csv", DEFAULT_CONFIG.limits):
        t.source_path = "b.csv"
        tables.append(t)
        profiles.append(profile_table(t))
    return build_canonical(tables, profiles).bowling


def test_bowling_totals_match_hand_calculation() -> None:
    raw = compute_bowling_raw(_bowl_records())
    pacer = raw["Fixture Pacer"]
    # 6 spells of 4 overs = 144 legal balls; 28+20+40+30+25+33 = 176 runs; 9 wickets
    assert pacer.legal_balls == 144
    assert pacer.runs_conceded == 176
    assert pacer.wickets == 9
    assert pacer.economy == pytest.approx(176 * 6 / 144)
    assert pacer.average == pytest.approx(176 / 9)
    assert pacer.strike_rate == pytest.approx(144 / 9)

    spinner = raw["Fixture Spinner"]
    assert spinner.legal_balls == 120
    assert spinner.runs_conceded == 115
    assert spinner.wickets == 10
    assert spinner.economy == pytest.approx(115 * 6 / 120)
    assert spinner.average == pytest.approx(115 / 10)


def test_bowling_overs_never_use_decimal_arithmetic(tmp_path: Path) -> None:
    """3.4 overs is 22 balls. A decimal reading (3.4*6 = 20.4) must not appear."""
    csv_path = tmp_path / "overs.csv"
    csv_path.write_text(
        "Bowler,Overs,Runs Conceded,Wickets\n"
        "Fixture Decimal,3.4,20,1\n"
        "Fixture Illegal,4.7,30,2\n", encoding="utf-8")
    tables, profiles = [], []
    for t in read_file(csv_path, "overs.csv", DEFAULT_CONFIG.limits):
        t.source_path = "overs.csv"
        tables.append(t)
        profiles.append(profile_table(t))
    cd = build_canonical(tables, profiles)
    raw = compute_bowling_raw(cd.bowling)
    assert raw["Fixture Decimal"].legal_balls == 22
    assert raw["Fixture Decimal"].economy == pytest.approx(20 * 6 / 22)
    # illegal notation is rejected (not guessed) and flagged, never silently parsed as 4.7 overs
    assert raw["Fixture Illegal"].legal_balls == 0
    assert "invalid_overs" in raw["Fixture Illegal"].flags


def test_small_sample_shrinkage_moves_score_toward_baseline() -> None:
    baseline = 130.0
    small = shrink(300.0, 12, 240, baseline)     # 12 balls faced
    large = shrink(300.0, 2400, 240, baseline)   # 2400 balls faced
    assert small is not None and large is not None
    assert small < large < 300.0
    assert small > baseline
    # zero exposure returns the baseline, it never returns the player's own value
    assert shrink(300.0, 0, 240, baseline) == baseline


# ---------------------------------------------------------------- statistics
def test_percentile_rank_is_bounded_and_monotone() -> None:
    pct = percentile_rank({"a": 1, "b": 2, "c": 3})
    assert pct["a"] == 0 and pct["c"] == 100
    assert pct["a"] < pct["b"] < pct["c"]
    inverted = percentile_rank({"a": 1, "b": 2, "c": 3}, higher_is_better=False)
    assert inverted["a"] == 100 and inverted["c"] == 0


def test_composite_renormalises_over_available_components() -> None:
    score, coverage, applied = composite({"a": 80, "b": 60, "c": None}, {"a": 0.5, "b": 0.3, "c": 0.2})
    assert score == pytest.approx((80 * 0.5 + 60 * 0.3) / 0.8)
    assert coverage == pytest.approx(0.8)
    assert set(applied) == {"a", "b"}
    # nothing available => no score invented
    assert composite({"a": None}, {"a": 1.0})[0] is None


def test_confidence_grading_thresholds_and_coverage_cap() -> None:
    cfg = DEFAULT_CONFIG.stats
    a = confidence_grade(1200, 1.0, None, cfg)
    assert a.grade == "A"
    d = confidence_grade(50, 1.0, None, cfg)
    assert d.grade == "D"
    # strong exposure but a partial model cannot hold grade A
    partial = confidence_grade(1200, 0.55, None, cfg)
    assert partial.grade == "C"
    assert any("coverage" in r for r in partial.reasons)


def test_consistency_from_cv_is_bounded() -> None:
    assert consistency_from_cv(0) == 100
    assert consistency_from_cv(1.0) == 50
    assert 0 < consistency_from_cv(5.0) < 20


# ---------------------------------------------------------------- eligibility
def test_eligibility_excludes_small_samples_with_a_reason() -> None:
    scored = score_batting_population(compute_batting_raw(_bat_records()), DEFAULT_CONFIG)
    eligible, reason = eligibility_bat(scored["Fixture Rookie"], DEFAULT_CONFIG)
    assert eligible is False
    assert "below the ranked threshold" in reason
    ok, _ = eligibility_bat(scored["Fixture Opener"], DEFAULT_CONFIG)
    assert ok is True


def test_leaderboard_is_ordered_and_capped() -> None:
    cfg = Config()
    cfg.eligibility.leaderboard_size = 30
    scored = score_batting_population(compute_batting_raw(_bat_records()), cfg)
    lb = build_leaderboard(scored, cfg, "batting")
    values = [r["rabi"] for r in lb.rows]
    assert values == sorted(values, reverse=True)
    assert lb.eligible_count == len(lb.rows) == 2      # only Opener and Anchor clear the floors
    assert {e["player"] for e in lb.excluded} == {"Fixture Finisher", "Fixture Rookie"}


# ---------------------------------------------------------------- data quality
def test_quality_audit_detects_cricket_rule_violations() -> None:
    tables, profiles = [], []
    for t in read_file(FIXTURES / "quality_probe.csv", "q.csv", DEFAULT_CONFIG.limits):
        t.source_path = "q.csv"
        tables.append(t)
        profiles.append(profile_table(t))
    cd = build_canonical(tables, profiles)
    report = run_quality_audit(tables, profiles, cd)
    codes = {f["code"] for f in report.findings}
    assert "invalid_overs" in codes            # "4.7" overs
    assert "boundary_exceeds_runs" in codes    # 9 fours in 45 runs
    assert "impossible_run_totals" in codes    # 200 runs off 60 balls
    assert "negative_balls" not in codes       # no negative balls in the fixture
    assert report.score < 100


def test_duplicate_aggregate_rows_are_superseded_not_summed() -> None:
    """The workbook aggregate for 2024 must be dropped once innings rows exist."""
    bundle = run_pipeline(
        sources=[FIXTURES / "dataset_bundle.zip"], storage_root=Path("/tmp/rs-test-dedup"),
        project_id="t", dataset_id="d_dedup", dataset_name="dedup",
        cfg=DEFAULT_CONFIG, is_fixture=True, progress=lambda *a: None, export=False)
    opener = next(r for r in bundle["batting"]["players"].values()
                  if r["player"] == "Fixture Opener")
    assert opener["runs"] == 207, "aggregate + innings rows were summed (double counting)"
    assert opener["balls_faced"] == 152
    kinds = {d["kind"] for d in bundle["schema"]["derivations"]}
    assert "aggregate_row_superseded" in kinds
