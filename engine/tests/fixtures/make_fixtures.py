"""Generate SYNTHETIC test fixtures with hand-verifiable expectations.

Everything produced here is fictitious and is used only by the automated tests.
Fixture players are named "Fixture ..." so they can never be mistaken for real
cricketers, and the datasets are flagged `is_fixture=True` in the pipeline.

Run: python tests/fixtures/make_fixtures.py
"""
from __future__ import annotations

import csv
import json
import random
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "generated"


def w(name: str, rows: list[list]) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / name
    with p.open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)
    return p


# ---------------------------------------------------------------------------
# 1. Batting: one row per innings. Hand-calculated expectations in test_batting.py
# ---------------------------------------------------------------------------
BATTING_HEADER = ["Player", "State Team", "Competition", "Season", "Match ID", "Opposition",
                  "Innings", "Runs", "Balls", "4s", "6s", "Not Out", "Dismissal", "Venue"]
BATTING_ROWS = [
    # Fixture Opener: runs 50+30+0+45+60+22 = 207 | balls 40+20+2+35+40+15 = 152
    # dismissals 4 (innings 1,3,4,5) | not-outs 2 | HS 60 | 30+ = 4 | 50+ = 2 | ducks 1
    ["Fixture Opener", "Fixture State A", "Fixture Trophy", "2024", "M1", "Fixture State B", 1, 50, 40, 6, 1, "No", "Caught", "Fixture Ground 1"],
    ["Fixture Opener", "Fixture State A", "Fixture Trophy", "2024", "M2", "Fixture State C", 2, 30, 20, 2, 2, "Yes", "Not Out", "Fixture Ground 2"],
    ["Fixture Opener", "Fixture State A", "Fixture Trophy", "2024", "M3", "Fixture State B", 1, 0, 2, 0, 0, "No", "Bowled", "Fixture Ground 1"],
    ["Fixture Opener", "Fixture State A", "Fixture Trophy", "2025", "M4", "Fixture State C", 1, 45, 35, 5, 1, "No", "LBW", "Fixture Ground 3"],
    ["Fixture Opener", "Fixture State A", "Fixture Trophy", "2025", "M5", "Fixture State B", 2, 60, 40, 7, 2, "No", "Caught", "Fixture Ground 2"],
    ["Fixture Opener", "Fixture State A", "Fixture Trophy", "2025", "M6", "Fixture State C", 2, 22, 15, 1, 1, "Yes", "Not Out", "Fixture Ground 3"],
    # Fixture Anchor: runs 60+40+35+28+55 = 218 | balls 50+45+40+30+50 = 215
    # dismissals 4 | not-outs 1 | HS 60 | 30+ = 5 | 50+ = 2
    ["Fixture Anchor", "Fixture State B", "Fixture Trophy", "2024", "M1", "Fixture State A", 2, 60, 50, 5, 0, "No", "LBW", "Fixture Ground 1"],
    ["Fixture Anchor", "Fixture State B", "Fixture Trophy", "2024", "M4", "Fixture State C", 1, 40, 45, 3, 0, "No", "Caught", "Fixture Ground 3"],
    ["Fixture Anchor", "Fixture State B", "Fixture Trophy", "2024", "M7", "Fixture State A", 2, 35, 40, 2, 0, "Yes", "Not Out", "Fixture Ground 1"],
    ["Fixture Anchor", "Fixture State B", "Fixture Trophy", "2025", "M8", "Fixture State C", 1, 28, 30, 2, 0, "No", "Bowled", "Fixture Ground 3"],
    ["Fixture Anchor", "Fixture State B", "Fixture Trophy", "2025", "M9", "Fixture State A", 2, 55, 50, 4, 1, "No", "Caught", "Fixture Ground 2"],
    # Fixture Finisher: runs 20+15+25+30+12+40 = 142 | balls 8+6+10+12+5+18 = 59
    # dismissals 3 | not-outs 3 | HS 40 | 30+ = 2 | 50+ = 0
    ["Fixture Finisher", "Fixture State C", "Fixture Trophy", "2024", "M2", "Fixture State A", 1, 20, 8, 1, 2, "No", "Caught", "Fixture Ground 2"],
    ["Fixture Finisher", "Fixture State C", "Fixture Trophy", "2024", "M3", "Fixture State B", 2, 15, 6, 0, 2, "Yes", "Not Out", "Fixture Ground 1"],
    ["Fixture Finisher", "Fixture State C", "Fixture Trophy", "2025", "M5", "Fixture State A", 2, 25, 10, 2, 2, "No", "Run Out", "Fixture Ground 2"],
    ["Fixture Finisher", "Fixture State C", "Fixture Trophy", "2025", "M10", "Fixture State B", 1, 30, 12, 1, 3, "Yes", "Not Out", "Fixture Ground 1"],
    ["Fixture Finisher", "Fixture State C", "Fixture Trophy", "2025", "M11", "Fixture State A", 1, 12, 5, 0, 1, "No", "Caught", "Fixture Ground 3"],
    ["Fixture Finisher", "Fixture State C", "Fixture Trophy", "2025", "M12", "Fixture State B", 2, 40, 18, 3, 3, "Yes", "Not Out", "Fixture Ground 2"],
    # Fixture Rookie: 8 balls — must be EXCLUDED from the ranked Top 30 with a stated reason
    ["Fixture Rookie", "Fixture State C", "Fixture Trophy", "2025", "M13", "Fixture State A", 1, 10, 8, 1, 0, "No", "Bowled", "Fixture Ground 3"],
]

# ---------------------------------------------------------------------------
# 2. Bowling: overs in cricket notation (4, 3.4, 4 ...)
# ---------------------------------------------------------------------------
BOWLING_HEADER = ["Player", "State Team", "Competition", "Season", "Match ID", "Opposition",
                  "Innings", "Overs", "Maidens", "Runs Conceded", "Wickets", "Dot Balls", "Best Bowling"]
BOWLING_ROWS = [
    # Fixture Pacer: 6 x 4 overs = 144 legal balls | runs 28+20+40+30+25+33 = 176
    # wickets 2+1+0+2+1+3 = 9 | economy 176*6/144 = 7.333 | average 19.56 | SR 16.0
    ["Fixture Pacer", "Fixture State A", "Fixture Trophy", "2024", "M1", "Fixture State B", 1, "4", 0, 28, 2, 10, "3/33"],
    ["Fixture Pacer", "Fixture State A", "Fixture Trophy", "2024", "M2", "Fixture State C", 1, "4", 0, 20, 1, 12, "3/33"],
    ["Fixture Pacer", "Fixture State A", "Fixture Trophy", "2024", "M3", "Fixture State B", 2, "4", 0, 40, 0, 6, "3/33"],
    ["Fixture Pacer", "Fixture State A", "Fixture Trophy", "2025", "M4", "Fixture State C", 1, "4", 0, 30, 2, 8, "3/33"],
    ["Fixture Pacer", "Fixture State A", "Fixture Trophy", "2025", "M5", "Fixture State B", 2, "4", 0, 25, 1, 11, "3/33"],
    ["Fixture Pacer", "Fixture State A", "Fixture Trophy", "2025", "M6", "Fixture State C", 2, "4", 0, 33, 3, 9, "3/33"],
    # Fixture Spinner: 5 x 4 = 120 legal balls | runs 20+25+30+22+18 = 115
    # wickets 3+1+2+3+1 = 10 | economy 5.75 | average 11.5 | SR 12.0
    ["Fixture Spinner", "Fixture State B", "Fixture Trophy", "2024", "M1", "Fixture State A", 2, "4", 1, 20, 3, 14, "3/18"],
    ["Fixture Spinner", "Fixture State B", "Fixture Trophy", "2024", "M7", "Fixture State C", 1, "4", 0, 25, 1, 11, "3/18"],
    ["Fixture Spinner", "Fixture State B", "Fixture Trophy", "2025", "M8", "Fixture State A", 2, "4", 0, 30, 2, 9, "3/18"],
    ["Fixture Spinner", "Fixture State B", "Fixture Trophy", "2025", "M9", "Fixture State C", 1, "4", 1, 22, 3, 15, "3/18"],
    ["Fixture Spinner", "Fixture State B", "Fixture Trophy", "2025", "M10", "Fixture State A", 1, "4", 0, 18, 1, 13, "3/18"],
    # Fixture Rookie: 12 balls — below the ranked workload floor, excluded with a stated reason
    ["Fixture Rookie", "Fixture State C", "Fixture Trophy", "2025", "M13", "Fixture State A", 1, "2", 0, 30, 0, 2, "0/30"],
]

# ---------------------------------------------------------------------------
# 2b. Deliberately dirty table so the audit engine has real violations to find
# ---------------------------------------------------------------------------
QUALITY_PROBE_HEADER = ["Player", "State Team", "Competition", "Season", "Innings", "Runs",
                        "Balls Faced", "4s", "6s", "Overs", "Runs Conceded", "Wickets"]
QUALITY_PROBE_ROWS = [
    # illegal overs notation (4.7)
    ["Fixture Probe One", "Fixture State A", "Fixture Trophy", "2024", 4, 60, 50, 4, 1, "4.7", 30, 2],
    # boundary runs (9 fours = 36) exceed total runs (45 -> fine) ; make 6 fours on 20 runs
    ["Fixture Probe Two", "Fixture State B", "Fixture Trophy", "2024", 3, 20, 15, 6, 0, "3", 40, 0],
    # impossible run total: 200 runs off 60 balls
    ["Fixture Probe Three", "Fixture State C", "Fixture Trophy", "2024", 5, 400, 60, 12, 8, "4", 44, 1],
]


def quality_probe() -> Path:
    return w("quality_probe.csv", [QUALITY_PROBE_HEADER] + QUALITY_PROBE_ROWS)


# ---------------------------------------------------------------------------
# 3. Ball-by-ball: two matches, deterministic synthetic scoring
# ---------------------------------------------------------------------------
def ball_by_ball() -> Path:
    rng = random.Random(20260315)
    rows = [["Match ID", "Innings", "Over", "Ball", "Batter", "Bowler", "Team", "Opposition",
             "Competition", "Season", "Batter Runs", "Extras", "Wicket", "Wicket Type", "Target"]]
    batters = ["Fixture Opener", "Fixture Anchor", "Fixture Finisher"]
    bowlers = ["Fixture Pacer", "Fixture Spinner"]
    match_specs = [
        # (target, first-innings total profile)
        {"M100": {"target": 165, "first_total": 164}},
        {"M101": {"target": 129, "first_total": 128}},
    ]
    seq = 0
    for spec in match_specs:
        for match_id, meta in spec.items():
            for innings in (1, 2):
                for over in range(1, 21):
                    for ball in range(1, 7):
                        seq += 1
                        batter = batters[seq % len(batters)]
                        bowler = bowlers[(over + seq) % len(bowlers)]
                        r = rng.choice([0, 0, 0, 1, 1, 2, 4, 6])
                        # make the chase progressively harder for innings 2
                        if innings == 2 and over >= 16:
                            r = rng.choice([0, 1, 1, 4])
                        wicket = 1 if (rng.random() < 0.05) else 0
                        rows.append([match_id, innings, over, ball, batter, bowler,
                                     "Fixture State A" if innings == 1 else "Fixture State B",
                                     "Fixture State B" if innings == 1 else "Fixture State A",
                                     "Fixture Trophy", "2025", r, 0, wicket,
                                     "Caught" if wicket else "", meta["target"]])
    return w("ball_by_ball.csv", rows)


# ---------------------------------------------------------------------------
# 4. Messy workbook: multiple sheets, one with an unmapped table
# ---------------------------------------------------------------------------
def messy_workbook() -> Path:
    from openpyxl import Workbook

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "messy_workbook.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Batting Summary"
    ws.append(["Batter Name", "Team", "Tournament", "Year", "Innings", "Total Runs", "Balls Faced",
               "Not Outs", "Highest Score", "Strike Rate"])
    ws.append(["Fixture Opener", "Fixture State A", "Fixture Trophy", 2024, 3, 80, 62, 1, "50", 129.03])
    ws.append(["Fixture Anchor", "Fixture State B", "Fixture Trophy", 2024, 2, 100, 95, 0, "60", 105.26])
    ws2 = wb.create_sheet("Bowling Summary")
    ws2.append([])  # leading blank row on purpose
    ws2.append(["Bowler", "Team", "Tournament", "Year", "Overs", "Runs", "Wickets", "Economy"])
    ws2.append(["Fixture Pacer", "Fixture State A", "Fixture Trophy", 2024, "11.4", 88, 3, 7.54])
    ws2.append(["Fixture Spinner", "Fixture State B", "Fixture Trophy", 2024, "8", 45, 4, 5.63])
    ws3 = wb.create_sheet("Budget")
    ws3.append(["Item", "Cost"])
    ws3.append(["Travel", 120000])
    ws3.append(["Kit", 45000])
    wb.save(path)
    return path


# ---------------------------------------------------------------------------
# 5. Archives, including hostile entries that must be refused
# ---------------------------------------------------------------------------
def archives() -> list[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    csv1 = w("archive_batting.csv", [BATTING_HEADER] + BATTING_ROWS)
    csv2 = w("archive_bowling.csv", [BOWLING_HEADER] + BOWLING_ROWS)
    nested_csv = w("nested_inner.csv",
                   [["Player", "Runs", "Balls", "Season", "Competition", "Team"],
                    ["Fixture Opener", 80, 62, 2024, "Fixture Trophy", "Fixture State A"]])

    # nested archive
    inner = OUT / "inner.zip"
    with zipfile.ZipFile(inner, "w") as zf:
        zf.write(nested_csv, "inner/nested_inner.csv")
    with zipfile.ZipFile(OUT / "dataset_bundle.zip", "w") as zf:
        zf.write(csv1, "batting/archive_batting.csv")
        zf.write(csv2, "bowling/archive_bowling.csv")
        zf.write(messy_workbook(), "workbook/messy_workbook.xlsx")
        zf.writestr("readme.txt", "synthetic fixture archive")
        zf.writestr("notes.exe", b"MZ fake executable - must be refused")
        zf.writestr("macro.xlsm", b"fake macro workbook")
        zf.write(inner, "nested/inner.zip")
        zf.writestr("batting/duplicate.csv", csv1.read_bytes())
        zf.writestr("../escape.csv", csv1.read_bytes())          # path traversal
        zf.writestr("/absolute.csv", csv1.read_bytes())          # absolute path
    return [OUT / "dataset_bundle.zip"]


def json_and_parquet() -> list[Path]:
    import polars as pl

    OUT.mkdir(parents=True, exist_ok=True)
    recs = [
        {"player": "Fixture Opener", "runs": 80, "balls": 62, "season": 2024, "team": "Fixture State A",
         "competition": "Fixture Trophy", "innings": 3, "not_outs": 1},
        {"player": "Fixture Anchor", "runs": 100, "balls": 95, "season": 2024, "team": "Fixture State B",
         "competition": "Fixture Trophy", "innings": 2, "not_outs": 0},
    ]
    j = OUT / "aggregates.json"
    j.write_text(json.dumps({"season_aggregates": recs}, indent=2), encoding="utf-8")
    p = OUT / "aggregates.parquet"
    pl.DataFrame(recs).write_parquet(p)
    return [j, p]


def main() -> None:
    w("batting_innings.csv", [BATTING_HEADER] + BATTING_ROWS)
    w("bowling_innings.csv", [BOWLING_HEADER] + BOWLING_ROWS)
    ball_by_ball()
    quality_probe()
    messy_workbook()
    archives()
    json_and_parquet()
    print(f"fixtures written to {OUT}")


if __name__ == "__main__":
    main()
