"""Pressure tagging, phase splits, ranking robustness and the job queue."""
from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from royalscout.config import Config, DEFAULT_CONFIG
from royalscout.db import JOB_QUEUED, JOB_RUNNING, LocalQueue, new_job
from royalscout.ingest import profile_table, read_file
from royalscout.canonical import build_canonical
from royalscout.pipeline import analyse_scope, run_pipeline
from royalscout.pressure import (phase_aggregates, pressure_batting_metrics,
                                 pressure_proxy_from_records, scenario_table, tag_ball_events)
from royalscout.ranking import build_leaderboard, candidate_scopes, stability_analysis

FIXTURES = Path(__file__).parent / "fixtures" / "generated"


def _events() -> pl.DataFrame:
    tables, profiles = [], []
    for t in read_file(FIXTURES / "ball_by_ball.csv", "bbb.csv", DEFAULT_CONFIG.limits):
        t.source_path = "bbb.csv"
        tables.append(t)
        profiles.append(profile_table(t))
    cd = build_canonical(tables, profiles)
    assert cd.ball_events is not None
    return cd.ball_events


def test_ball_events_are_detected_and_derived_into_innings() -> None:
    tables, profiles = [], []
    for t in read_file(FIXTURES / "ball_by_ball.csv", "bbb.csv", DEFAULT_CONFIG.limits):
        t.source_path = "bbb.csv"
        tables.append(t)
        profiles.append(profile_table(t))
    cd = build_canonical(tables, profiles)
    assert cd.capabilities["ball_by_ball"] is True
    assert cd.capabilities["actual_match_pressure"] is True
    # every delivery becomes an innings-level batting and bowling record
    assert any("derived_from_ball_by_ball" in r["flags"] for r in cd.batting)
    assert any("derived_from_ball_by_ball" in r["flags"] for r in cd.bowling)


def test_pressure_tags_require_a_difficult_situation_not_just_a_late_over() -> None:
    tagged = tag_ball_events(_events(), DEFAULT_CONFIG)
    for col in ("is_pressure", "pressure_tags", "rrr", "wkts_left", "balls_left"):
        assert col in tagged.columns
    # Some deliveries are tagged, and not all of them are death overs
    pres = tagged.filter(pl.col("is_pressure"))
    assert pres.height > 0
    assert pres.height < tagged.height
    assert pres["over_number"].min() <= 15, "pressure must not be synonymous with death overs"
    # A wide-open first over of the first innings can never be 'pressure'
    first_ball = tagged.filter((pl.col("innings_number") == 1) & (pl.col("over_number") == 1)
                               & (pl.col("ball_number") == 1)).to_dicts()[0]
    assert first_ball["is_pressure"] is False


def test_pressure_scores_are_labelled_with_their_basis() -> None:
    tagged = tag_ball_events(_events(), DEFAULT_CONFIG)
    metrics = pressure_batting_metrics(tagged, DEFAULT_CONFIG)
    assert metrics
    for pid, m in metrics.items():
        assert m["basis"] == "ball_by_ball"
        assert m["detail"]["status"] in {"supported", "provisional"}
        assert "tagged_deliveries_pressure" in m["detail"]


def test_phase_aggregates_split_by_over() -> None:
    phases = phase_aggregates(tag_ball_events(_events(), DEFAULT_CONFIG))
    assert phases["available"] is True
    some = next(iter(phases["batting"].values()))
    assert set(some) & {"powerplay", "middle", "death"}
    assert abs(sum(some["phase_ball_shares"].values()) - 1.0) < 0.01


def test_pressure_is_unavailable_without_ball_by_ball() -> None:
    tables, profiles = [], []
    for t in read_file(FIXTURES / "batting_innings.csv", "bat.csv", DEFAULT_CONFIG.limits):
        t.source_path = "bat.csv"
        tables.append(t)
        profiles.append(profile_table(t))
    cd = build_canonical(tables, profiles)
    assert cd.capabilities["ball_by_ball"] is False

    # with an innings index only a clearly-labelled proxy exists
    proxy = pressure_proxy_from_records(cd.batting, cd.bowling, DEFAULT_CONFIG)
    for v in proxy.values():
        assert v["basis"] == "innings_index_proxy"
        assert v["detail"]["status"] == "proxy_only"
        assert v["score"] is None, "a proxy must never be presented as a pressure score"

    # with neither, the component is simply unavailable
    no_innings = [{**b, "innings_number": None} for b in cd.batting]
    assert pressure_proxy_from_records(no_innings, [], DEFAULT_CONFIG) == {}


def test_scenario_definitions_are_published() -> None:
    rows = scenario_table(DEFAULT_CONFIG)
    assert len(rows) >= 8
    assert all(r["definition"] for r in rows)
    assert any("required run rate" in r["definition"] for r in rows)


def test_coverage_drops_when_pressure_is_unavailable() -> None:
    tables, profiles = [], []
    for t in read_file(FIXTURES / "batting_innings.csv", "bat.csv", DEFAULT_CONFIG.limits):
        t.source_path = "bat.csv"
        tables.append(t)
        profiles.append(profile_table(t))
    cd = build_canonical(tables, profiles)
    analysis = analyse_scope(cd.batting, cd.bowling, None, {}, Config())
    for m in analysis.batting.values():
        assert m["pressure_score"] is None
        assert m["score_coverage"] < 1.0
        assert "pressure" not in m["component_weights_applied"]


def test_ranking_stability_reports_rank_spread() -> None:
    out = run_pipeline(sources=[FIXTURES / "batting_innings.csv"], storage_root=Path("/tmp/rs-test-stab"),
                       project_id="t", dataset_id="d_stab", dataset_name="stab",
                       cfg=DEFAULT_CONFIG, is_fixture=True, progress=lambda *a: None, export=False)
    bat = out["stability"]["batting"]
    assert bat["variants"], "stability analysis must produce variants"
    assert {v["variant"] for v in bat["variants"]} >= {"baseline", "prior_k_60", "prior_k_960"}
    assert bat["interpretation"]
    for p in bat["per_player"]:
        assert p["min_rank"] <= p["max_rank"]
        assert p["rank_spread"] == p["max_rank"] - p["min_rank"]


def test_leaderboard_never_pads_to_thirty() -> None:
    out = run_pipeline(sources=[FIXTURES / "batting_innings.csv"], storage_root=Path("/tmp/rs-test-pad"),
                       project_id="t", dataset_id="d_pad", dataset_name="pad",
                       cfg=DEFAULT_CONFIG, is_fixture=True, progress=lambda *a: None, export=False)
    rows = out["leaderboards"]["global"]["batters"]
    assert len(rows) == 2 < 30, "the leaderboard must not invent players to fill 30 places"
    assert out["leaderboards"]["global"]["batters_excluded"], "exclusions must be listed with reasons"


def test_scopes_are_generated_for_competition_season_and_team() -> None:
    tables, profiles = [], []
    for name in ("batting_innings.csv",):
        for t in read_file(FIXTURES / name, name, DEFAULT_CONFIG.limits):
            t.source_path = name
            tables.append(t)
            profiles.append(profile_table(t))
    cd = build_canonical(tables, profiles)
    scopes = candidate_scopes(cd.batting, cd.bowling)
    types = {s["type"] for s in scopes}
    assert types == {"global", "competition", "season", "team", "competition_season"}


# ------------------------------------------------------------------ job queue
def test_local_queue_claim_and_retry(tmp_path: Path) -> None:
    q = LocalQueue(tmp_path / "queue")
    job = new_job("p", "d", "name", [{"local_path": "/tmp/x.csv"}])
    q.create(job)
    assert q.get(job.id).status == JOB_QUEUED
    claimed = q.claim_next()
    assert claimed is not None and claimed.id == job.id
    assert claimed.status == JOB_RUNNING and claimed.attempts == 1
    q.update(job.id, status="failed", error="boom")
    q.log(job.id, "reading files", "12 rows", 40)
    again = q.claim_next()
    assert again is not None and again.attempts == 2, "failed jobs must be retryable"
    stored = json.loads((tmp_path / "queue" / f"{job.id}.json").read_text())
    assert stored["logs"][0]["message"] == "12 rows"
    assert stored["progress"] == 40


def test_worker_processes_a_queued_job(tmp_path: Path) -> None:
    from royalscout.worker import process_job
    q = LocalQueue(tmp_path / "queue")
    job = new_job("proj", "ds1", "Worker test",
                  [{"local_path": str(FIXTURES / "batting_innings.csv")}], is_fixture=True)
    q.create(job)
    claimed = q.claim_next()
    assert claimed is not None
    result = process_job(claimed, q, tmp_path / "storage", export=False)
    assert result["batters_ranked"] == 2
    assert Path(result["bundle_path"]).exists()
    assert q.get(job.id).logs, "the worker must write progress logs"
