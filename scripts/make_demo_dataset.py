"""Generate the SYNTHETIC demonstration dataset used by the dashboard preview.

This dataset is entirely fictitious. Player names are prefixed "Fixture" so they
can never be confused with real cricketers, and the resulting bundle is flagged
`is_fixture = true`; the UI renders a persistent "SYNTHETIC TEST DATA" banner.
Replace it with a real import before using any ranking for scouting decisions.

Usage:  python scripts/make_demo_dataset.py --out ../data/demo
"""
from __future__ import annotations

import argparse
import csv
import random
import zipfile
from pathlib import Path

STATE_TEAMS = ["Rajasthan", "Delhi", "Mumbai", "Karnataka", "Tamil Nadu", "Bengal",
               "Punjab", "Gujarat"]
COMPETITIONS = [
    ("Fixture Elite Cup", "T20", ["2023", "2024", "2025"]),
    ("Fixture State League", "T20", ["2022", "2023", "2024"]),
    ("Fixture Emerging Trophy", "T20", ["2024", "2025"]),
]
VENUES = ["Sawai Mansingh Stadium, Jaipur", "Arun Jaitley Stadium, Delhi", "Wankhede Stadium, Mumbai",
          "M. Chinnaswamy Stadium, Bengaluru", "Eden Gardens, Kolkata", "Narendra Modi Stadium, Ahmedabad"]
ROLES = ["batter", "batter", "bowler", "bowler", "bowler", "all rounder", "wicket keeper"]

SURNAMES = ["Agarwal", "Bhatia", "Chauhan", "Deshmukh", "Fernandes", "Gill", "Hooda", "Iyer", "Jadeja",
            "Kohli", "Lakra", "Mehta", "Nair", "Ojha", "Patel", "Qureshi", "Rathore", "Sharma", "Tiwari",
            "Uday", "Verma", "Wangdu", "Yadav", "Zope", "Bishnoi", "Chahal", "Dagar", "Fazal", "Gowda",
            "Harpreet", "Iqbal", "Jaiswal", "Kumar", "Lal", "Mishra", "Nagar", "Oberoi", "Pandey",
            "Rawat", "Shekhawat", "Tomar", "Upadhyay", "Vasudev", "Walia", "Xavier", "Yash"]
FIRSTS = ["Aarav", "Bhavesh", "Chirag", "Dev", "Eshan", "Farhan", "Gaurav", "Harsh", "Ishan", "Jatin",
          "Karan", "Lakhan", "Manav", "Nikhil", "Om", "Pranav", "Rehan", "Sahil", "Tanmay", "Umesh",
          "Varun", "Yash", "Zaid", "Aditya", "Bharat", "Chetan", "Dhruv", "Ekansh"]


def build_players(rng: random.Random, n: int = 58) -> list[dict]:
    players = []
    used: set[str] = set()
    for i in range(n):
        while True:
            name = f"Fixture {rng.choice(FIRSTS)} {rng.choice(SURNAMES)}"
            if name not in used and len(name) < 34:
                used.add(name)
                break
        role = ROLES[i % len(ROLES)]
        players.append({
            "name": name,
            "team": STATE_TEAMS[i % len(STATE_TEAMS)],
            "role": role,
            "bat_skill": rng.uniform(0.30, 1.0),
            "bowl_skill": rng.uniform(0.20, 1.0),
            "batting_hand": "Left" if rng.random() < 0.3 else "Right",
            "bowling_style": rng.choice(["Right-arm fast", "Right-arm medium", "Left-arm orthodox",
                                         "Right-arm leg-spin", "Left-arm fast"]),
            "declared_keeper": role == "wicket keeper",
        })
    return players


def batting_rows(rng: random.Random, players: list[dict]) -> list[list]:
    rows = [["Player", "State Team", "Role", "Competition", "Season", "Match ID", "Opposition",
             "Venue", "Innings", "Batting Position", "Runs", "Balls Faced", "4s", "6s",
             "Not Out", "Dismissal", "Dot Balls"]]
    match_no = 0
    for p in players:
        if p["role"] == "bowler" and rng.random() < 0.35:
            continue  # some specialist bowlers have no meaningful batting sample
        innings_target = rng.randint(12, 20)
        for comp, fmt, seasons in COMPETITIONS:
            if rng.random() < 0.18:
                continue
            for _ in range(max(3, innings_target // 3)):
                match_no += 1
                season = rng.choice(seasons)
                skill = p["bat_skill"]
                position = rng.choice([1, 1, 2, 2, 3, 3, 4, 5, 5, 6, 7])
                balls = max(1, int(rng.gauss(14 + 18 * skill, 8)))
                if position >= 6:
                    balls = max(1, int(rng.gauss(8 + 8 * skill, 5)))
                strike = 95 + 95 * skill + (25 if position >= 6 else 0) + rng.gauss(0, 18)
                runs = max(0, int(round(balls * max(45, strike) / 100)))
                fours = min(runs // 4, int(runs * 0.09))
                sixes = min((runs - 4 * fours) // 6, int(runs * 0.03 * (1 + skill)))
                not_out = rng.random() < (0.18 + 0.12 * skill)
                dismissal = "Not Out" if not_out else rng.choice(
                    ["Caught", "Bowled", "LBW", "Run Out", "Stumped", "Caught & Bowled"])
                dots = max(0, int(balls * max(0.15, 0.55 - 0.35 * skill) + rng.gauss(0, 2)))
                rows.append([p["name"], p["team"], p["role"], comp, season, f"M{match_no:04d}",
                             rng.choice([t for t in STATE_TEAMS if t != p["team"]]),
                             rng.choice(VENUES), rng.choice([1, 2]), position, runs, balls, fours,
                             sixes, "Yes" if not_out else "No", dismissal, min(dots, balls)])
    return rows


def bowling_rows(rng: random.Random, players: list[dict]) -> list[list]:
    rows = [["Player", "State Team", "Role", "Competition", "Season", "Match ID", "Opposition",
             "Venue", "Innings", "Overs", "Maidens", "Runs Conceded", "Wickets", "Dot Balls",
             "Best Bowling"]]
    match_no = 5000
    for p in players:
        if p["role"] in ("batter", "wicket keeper"):
            if rng.random() < 0.92:
                continue
        spells = rng.randint(8, 14)
        best = (0, 999)
        for comp, fmt, seasons in COMPETITIONS:
            if rng.random() < 0.2:
                continue
            for _ in range(max(3, spells // 3)):
                match_no += 1
                season = rng.choice(seasons)
                skill = p["bowl_skill"]
                overs = rng.choice([3, 4, 4, 4, 2])
                balls = overs * 6
                economy = 10.5 - 4.2 * skill + rng.gauss(0, 1.4)
                economy = max(4.0, economy)
                runs = int(round(balls * economy / 6))
                wkt_rate = max(0.02, 0.32 - 0.20 * skill)
                wickets = 0
                for _b in range(balls):
                    if rng.random() < wkt_rate:
                        wickets += 1
                wickets = min(wickets, 6)
                maidens = 1 if (economy < 6.5 and rng.random() < 0.25) else 0
                dots = max(0, int(balls * (0.30 + 0.28 * skill) + rng.gauss(0, 2)))
                if wickets > best[0] or (wickets == best[0] and runs < best[1]):
                    best = (wickets, runs)
                rows.append([p["name"], p["team"], p["role"], comp, season, f"M{match_no:04d}",
                             rng.choice([t for t in STATE_TEAMS if t != p["team"]]),
                             rng.choice(VENUES), rng.choice([1, 2]), f"{overs}.{rng.choice([0, 0, 1, 2, 3, 4])}",
                             maidens, runs, wickets, min(dots, balls), "0/0"])
    for r in rows[1:]:
        idx = rows.index(r)
        rows[idx][-1] = f"{r[12]}/{r[11]}"
    return rows


def ball_by_ball(rng: random.Random, players: list[dict], matches: int = 16) -> list[list]:
    rows = [["Match ID", "Innings", "Over", "Ball", "Batter", "Bowler", "Team", "Opposition",
             "Competition", "Season", "Batter Runs", "Extras", "Wicket", "Wicket Type", "Target"]]
    batters = [p["name"] for p in players if p["role"] in ("batter", "wicket keeper", "all rounder")][:26]
    bowlers = [p["name"] for p in players if p["role"] in ("bowler", "all rounder")][:18]
    for m in range(matches):
        match_id = f"BBB{m:04d}"
        target = rng.randint(120, 205)
        for innings in (1, 2):
            bat_lineup = rng.sample(batters, min(11, len(batters)))
            bowl_lineup = rng.sample(bowlers, min(5, len(bowlers)))
            striker = 0
            for over in range(1, 21):
                bowler = bowl_lineup[(over - 1) % len(bowl_lineup)]
                for ball in range(1, 7):
                    batter = bat_lineup[(striker + over // 3) % len(bat_lineup)]
                    r = rng.choices([0, 1, 2, 3, 4, 6], weights=[38, 30, 12, 2, 13, 5])[0]
                    if innings == 2 and over >= 16 and rng.random() < 0.25:
                        r = rng.choice([0, 1, 1, 4])
                    wicket = rng.random() < 0.045
                    rows.append([match_id, innings, over, ball, batter, bowler,
                                 "Rajasthan" if innings == 1 else "Delhi",
                                 "Delhi" if innings == 1 else "Rajasthan",
                                 "Fixture Elite Cup", "2025", r, 0, 1 if wicket else 0,
                                 "Caught" if wicket else "", target])
    return rows


def quality_probe_rows() -> list[list]:
    """A deliberately dirty table so the Data Audit screen has real findings."""
    return [
        ["Player", "State Team", "Competition", "Season", "Innings", "Runs", "Balls Faced", "4s",
         "6s", "Overs", "Runs Conceded", "Wickets", "Strike Rate", "Economy"],
        ["Fixture Karan Yadav", "Delhi", "Fixture State League", "2024", 5, 120, 90, 8, 3, "4.7", 30, 1,
         133.33, 6.42],
        ["Fixture Om Verma", "Mumbai", "Fixture State League", "2024", 4, 45, 20, 9, 1, "3", 40, 0,
         225.0, 13.33],
        ["Fixture Zaid Sharma", "Punjab", "Fixture State League", "2024", 3, -5, 30, 1, 0, "4", 28, 12,
         -16.67, 7.0],
        ["Fixture Dev Nair", "Bengal", "Fixture State League", "2024", 6, 400, 60, 4, 4, "4", 44, 2,
         400.0, 11.0],
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="../data/demo")
    ap.add_argument("--seed", type=int, default=20260315)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)

    players = build_players(rng)
    bat = batting_rows(rng, players)
    bowl = bowling_rows(rng, players)
    bbb = ball_by_ball(rng, players)

    def write(name: str, rows: list[list]) -> Path:
        p = out / name
        with p.open("w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows(rows)
        return p

    bat_path = write("fixture_batting_innings.csv", bat)
    bowl_path = write("fixture_bowling_innings.csv", bowl)
    bbb_path = write("fixture_ball_by_ball.csv", bbb)
    dirty_path = write("fixture_quality_probe.csv", quality_probe_rows())

    # a small workbook with declared roles (so keeper roles are declared, not inferred)
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Player Register"
    ws.append(["Player", "State Team", "Role", "Batting Hand", "Bowling Style"])
    for p in players:
        ws.append([p["name"], p["team"], p["role"], p["batting_hand"], p["bowling_style"]])
    register = out / "fixture_player_register.xlsx"
    wb.save(register)

    # an archive that also demonstrates the hostile-file guards
    with zipfile.ZipFile(out / "fixture_scouting_archive.zip", "w") as zf:
        zf.write(bat_path, "season_csv/fixture_batting_innings.csv")
        zf.write(bowl_path, "season_csv/fixture_bowling_innings.csv")
        zf.write(register, "registers/fixture_player_register.xlsx")
        zf.write(dirty_path, "quality/fixture_quality_probe.csv")
        zf.writestr("docs/readme.txt", "Synthetic demonstration archive for Royal Scout.\n")
        zf.writestr("tools/scraper.exe", b"not a real executable - refused by the ingestion guard")
        zf.writestr("../../etc/passwd", b"path traversal attempt - refused")
    print(f"demo sources written to {out}")


if __name__ == "__main__":
    main()
