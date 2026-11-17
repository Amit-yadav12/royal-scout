from pathlib import Path
import zipfile

import polars as pl

from royalscout.canonical import reduce_ball_events_to_innings
from royalscout.config import DEFAULT_CONFIG
from royalscout.pipeline import _superr_pressure_analysis, run_pipeline
from royalscout.providers.superr import detect
from royalscout.superr.load import derive_ball_state, load_raw


def _write_pack(root: Path, include_teams: bool = False) -> Path:
    pack = root / "deep" / "uploaded-pack"
    pack.mkdir(parents=True)
    # Deliberately use staged, prefixed names rather than provider basenames.
    pl.DataFrame({
        "match_id": [101] * 5, "innings": [1, 1, 1, 2, 2],
        "overid": [1] * 5, "over_ball_num": [1, 2, 3, 1, 2],
        "batting_team_id": [10, 10, 10, 20, 20], "bowling_team_id": [20, 20, 20, 10, 10],
        "striker_id": [1, 1, 1, 3, 3], "striker_name": ["A Batter"] * 3 + ["C Batter"] * 2,
        "non_striker_id": [2, 2, 2, 4, 4], "non_striker_name": ["B Batter"] * 3 + ["D Batter"] * 2,
        "bowler_id": [5, 5, 5, 6, 6], "bowler_name": ["E Bowler"] * 3 + ["F Bowler"] * 2,
        "runs": [0, 1, 4, 0, 2], "is_four": [False, False, True, False, False], "is_six": [False] * 5,
        "is_wicket": [False, False, False, False, True], "dismissal_type_id": [None, None, None, None, 1],
        "dismissal_type": [None, None, None, None, "RunOut"], "dismissed_player_id": [None, None, None, None, 4],
        "extras_type": ["wide", "None", "None", "None", "None"],
        "extras1_runs": [1, 0, 0, 0, 0], "extras_2_runs": [0] * 5,
        "comp_id": [7] * 5, "pace_or_spin": ["pace"] * 5,
    }).write_csv(pack / "upload-a-ball.csv")
    pl.DataFrame({
        "match_id": [101], "comp_id": [7], "match_date": ["2025-01-01"],
        "revised_target": [None], "first_inn_revised_overs": [None], "second_inn_revised_overs": [None],
        "knock_out": [0], "stage": ["League"], "win_team_id": [10], "result": ["normal"],
        "venue_id": [1], "home_team_id": [10], "away_team_id": [20],
    }).write_csv(pack / "upload-b-match.csv")
    pl.DataFrame({"comp_id": [7], "comp_name": ["IPL test"], "match_format": ["T20"],
                  "season": ["2025"]}).write_csv(pack / "upload-c-comp.csv")
    pl.DataFrame({"match_id": [101] * 6, "player_id": [1, 2, 3, 4, 5, 6],
                  "is_played": [True] * 6, "batting_order": [1, 2, 1, 2, None, None]}).write_csv(
                      pack / "upload-d-xi.csv")
    pl.DataFrame({"player_id": [1, 2, 3, 4, 5, 6],
                  "player_name": ["A Batter", "B Batter", "C Batter", "D Batter", "E Bowler", "F Bowler"],
                  "team_id": [10, 10, 20, 20, 20, 10], "comp_id": [7] * 6}).write_csv(
                      pack / "upload-e-mapping.csv")
    if include_teams:
        pl.DataFrame({"team_id": [10, 20], "team_name": ["Rajasthan", "Delhi"]}).write_csv(
            pack / "upload-f-teams.csv")
    return pack


def test_detects_prefixed_nested_five_file_pack_without_teams(tmp_path: Path) -> None:
    pack = _write_pack(tmp_path)
    assert detect([tmp_path]) == tmp_path.resolve()
    raw = load_raw(tmp_path)
    assert raw.ball.height == 5
    assert raw.matches.height == 1
    assert raw.teams.height == 0
    assert len(raw.source_files) == 5


def test_pipeline_uses_provider_pressure_method_and_labels_missing_team_names(tmp_path: Path) -> None:
    pack = _write_pack(tmp_path)
    inner = tmp_path / "inner.zip"
    with zipfile.ZipFile(inner, "w") as archive:
        for source in pack.glob("*.csv"):
            archive.write(source, f"provider_tables/{source.name}")
    outer = tmp_path / "outer.zip"
    with zipfile.ZipFile(outer, "w") as archive:
        archive.write(inner, "nested/inner.zip")
    result = run_pipeline([outer], tmp_path / "storage", "p", "d", "Nested pack",
                          cfg=DEFAULT_CONFIG, progress=lambda *_: None, export=False)
    provider = next(d for d in result["schema"]["derivations"] if d.get("kind") == "provider_adapter")
    assert provider["deliveries"] == 5
    assert provider["team_identity"]["unresolved_team_ids"] == ["10", "20"]
    assert result["pressure_rankings"]["facts"]["primary_deliveries"] == 5
    assert result["pressure_rankings"]["facts"]["eligible_primary"] == {"batters": 0, "bowlers": 0}
    assert result["counts"]["ball_events"] == 5
    assert result["batting"]["players"]["A Batter"]["runs"] == 5
    assert result["batting"]["players"]["A Batter"]["balls_faced"] == 2
    assert result["bowling"]["players"]["E Bowler"]["runs_conceded"] == 6
    assert result["bowling"]["players"]["E Bowler"]["legal_balls"] == 2
    dismissed = next(r for r in result["batting"]["players"].values() if r.get("player") == "D Batter")
    assert dismissed["dismissals"] == 1 and dismissed["runs"] == 0
    cache = tmp_path / "storage/projects/p/datasets/d/superr_cache"
    assert (cache / "ball_state.parquet").exists()
    assert (cache / "pressure_ball_state.parquet").exists()
    assert (cache / "player_match_bat.parquet").exists()


def test_primary_pressure_shortlist_carries_bootstrap_and_robustness_gates(tmp_path: Path) -> None:
    pack = tmp_path / "candidate-pack"
    pack.mkdir()
    balls = []
    for match_no in range(10):
        match_id = 200 + match_no
        comp_id = 7 if match_no < 5 else 8
        for innings in (1, 2):
            bat_team, bowl_team = (10, 20) if innings == 1 else (20, 10)
            for index in range(50):
                wicket = index < 6
                balls.append({
                    "match_id": match_id, "innings": innings, "overid": index // 6 + 1,
                    "over_ball_num": index % 6 + 1, "batting_team_id": bat_team,
                    "bowling_team_id": bowl_team,
                    "striker_id": 1 if index % 2 == 0 else 3,
                    "striker_name": "Test Batter" if index % 2 == 0 else "Second Batter",
                    "non_striker_id": 999, "non_striker_name": "Runner",
                    "bowler_id": 2 if index % 2 == 0 else 4,
                    "bowler_name": "Test Bowler" if index % 2 == 0 else "Second Bowler",
                    "runs": 1, "is_four": False, "is_six": False,
                    "is_wicket": wicket, "dismissal_type_id": 1 if wicket else None,
                    "dismissal_type": "RunOut" if wicket else None,
                    "dismissed_player_id": 999 if wicket else None, "extras_type": "None",
                    "extras1_runs": 0, "extras_2_runs": 0, "comp_id": comp_id,
                    "pace_or_spin": "pace",
                })
    pl.DataFrame(balls).write_csv(pack / "staged-ball.csv")
    matches = []
    xi = []
    for match_no in range(10):
        match_id = 200 + match_no
        comp_id = 7 if match_no < 5 else 8
        matches.append({
            "match_id": match_id, "comp_id": comp_id, "match_date": f"202{4 + (match_no >= 5)}-01-01",
            "revised_target": None, "first_inn_revised_overs": None, "second_inn_revised_overs": None,
            "knock_out": 0, "stage": "League", "win_team_id": 10, "result": "normal",
            "venue_id": 1, "home_team_id": 10, "away_team_id": 20,
        })
        for pid in (1, 2, 3, 4, 999):
            xi.append({"match_id": match_id, "player_id": pid, "is_played": True, "batting_order": 1})
    pl.DataFrame(matches).write_csv(pack / "staged-matches.csv")
    pl.DataFrame({"comp_id": [7, 8], "comp_name": ["IPL 2024", "IPL 2025"],
                  "match_format": ["T20", "T20"], "season": ["2024", "2025"]}).write_csv(
                      pack / "staged-comps.csv")
    pl.DataFrame(xi).write_csv(pack / "staged-xi.csv")
    pl.DataFrame({"player_id": [1, 2, 3, 4, 999],
                  "player_name": ["Test Batter", "Test Bowler", "Second Batter", "Second Bowler", "Runner"],
                  "team_id": [10, 20, 10, 20, 10], "comp_id": [7] * 5}).write_csv(
                      pack / "staged-mapping.csv")

    result = _superr_pressure_analysis(pack, tmp_path / "cache")
    assert result["facts"]["eligible_primary"] == {"batters": 2, "bowlers": 2}
    assert result["facts"]["bootstrap_resamples"] == 400
    assert result["final"]["batters"] and result["final"]["bowlers"]
    assert result["primary"]["batters"][0]["rank_p05"] is not None
    assert result["final"]["batters"][0]["confirmed"] is True
    assert result["final"]["batters"][0]["seasons_evaluated"] == 2
    assert result["robustness"]["batters"]
    assert (tmp_path / "cache/robustness_ranks_bat.parquet").exists()


def test_unknown_dismissal_is_not_credited_to_bowler(tmp_path: Path) -> None:
    pack = _write_pack(tmp_path)
    ball_path = pack / "upload-a-ball.csv"
    ball = pl.read_csv(ball_path).with_columns(
        pl.when(pl.col("dismissal_type") == "RunOut").then(pl.lit("Unmapped dismissal"))
          .otherwise(pl.col("dismissal_type")).alias("dismissal_type"))
    ball.write_csv(ball_path)
    state = derive_ball_state(load_raw(tmp_path))
    unknown = state.filter(pl.col("is_wicket")).row(0, named=True)
    assert unknown["bowler_wicket"] is None


def test_non_striker_run_out_is_attributed_to_dismissed_batter() -> None:
    events = pl.DataFrame({
        "match_id": [1], "innings_number": [1], "batter": ["Striker"], "team_batting": ["A"],
        "competition": ["IPL"], "season": ["2025"], "batter_runs": [1], "batter_ball": [True],
        "is_four": [False], "is_six": [False], "batter_dismissed": [False], "is_wicket": [False],
        "bowler_wicket": [False], "legal_delivery": [True], "bowler": ["Bowler"], "team_bowling": ["B"],
        "bowler_runs": [1], "extras": [0], "over_number": [1], "dismissed_batter": ["Non Striker"],
    })
    batting, _ = reduce_ball_events_to_innings(events)
    dismissed = next(row for row in batting if row["player"] == "Non Striker")
    assert dismissed["runs"] == 0
    assert dismissed["dismissals"] == 1
    assert dismissed["not_outs"] == 0
