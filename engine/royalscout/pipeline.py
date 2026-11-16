"""End-to-end dataset pipeline.

ingest -> discover -> canonicalise -> audit -> analyse -> rank -> export

Every stage reports through `progress(stage, pct, detail)` so the database-backed
job queue can show live progress, and every stage writes durable artefacts so a
failure can be retried from a checkpoint.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import polars as pl

from . import bowling as bowl_mod
from . import batting as bat_mod
from .config import MODEL_VERSION, Config, DEFAULT_CONFIG
from .providers import superr as provider_superr
from .canonical import (CanonicalData, build_canonical, build_player_registry,
                        GRANULARITY_INNINGS)
from .context import opposition_adjusted
from .exports import (BAT_COLUMNS, BOWL_COLUMNS, export_workbook, provenance_block, write_csv,
                      write_json, write_pdf)
from .ingest import (ArchiveEntry, IngestionError, TableProfile, RawTable, UNSAFE_EXT,
                     iter_source_files, profile_table, read_file, safe_extract, sha256_file)
from .pressure import (match_impact, phase_aggregates, pressure_batting_metrics,
                       pressure_bowling_metrics, pressure_performance_index,
                       pressure_proxy_from_records, scenario_table, tag_ball_events)
from .quality import run_quality_audit
from .ranking import (attach_recent_form, build_leaderboard, candidate_scopes,
                      stability_analysis)
from .roles import classify_roles
from .store import ArtifactStore

Progress = Callable[[str, float, str], None]


def _noop(stage: str, pct: float, detail: str) -> None:  # pragma: no cover
    pass


# ---------------------------------------------------------------------------
# File level ingestion
# ---------------------------------------------------------------------------
@dataclass
class FileLog:
    path: str
    display_name: str
    size_bytes: int
    kind: str = "data"          # data | archive | nested_archive | unsupported
    status: str = "pending"     # processed | failed | unsupported | skipped
    reason: str | None = None
    sha256: str | None = None
    tables_found: int = 0
    record_type: str | None = None
    rows: int = 0
    origin: str | None = None   # upload | archive:<name>

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "display_name": self.display_name, "size_bytes": self.size_bytes,
                "kind": self.kind, "status": self.status, "reason": self.reason,
                "sha256": self.sha256, "tables_found": self.tables_found,
                "record_type": self.record_type, "rows": self.rows, "origin": self.origin}


@dataclass
class IngestionResult:
    tables: list[RawTable] = field(default_factory=list)
    profiles: list[TableProfile] = field(default_factory=list)
    files: list[FileLog] = field(default_factory=list)
    archive_entries: list[ArchiveEntry] = field(default_factory=list)
    originals: list[dict[str, Any]] = field(default_factory=list)
    duplicates: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        statuses = [f.status for f in self.files]
        return {
            "files_seen": len(self.files),
            "files_processed": statuses.count("processed"),
            "files_failed": statuses.count("failed"),
            "files_unsupported": statuses.count("unsupported"),
            "files_skipped": statuses.count("skipped"),
            "archives": len([f for f in self.files if f.kind in ("archive", "nested_archive")]),
            "archive_entries": len(self.archive_entries),
            "tables_detected": len(self.profiles),
            "worksheets": len({(p.source_path, p.table_name) for p in self.profiles}),
            "rows_discovered": sum(p.row_count for p in self.profiles),
            "original_bytes": sum(f.size_bytes for f in self.files if f.origin == "upload"),
            "extracted_bytes": sum(e.size for e in self.archive_entries if e.reason is None),
            "duplicate_files": len(self.duplicates),
            "duplicate_archive_entries": len([e for e in self.archive_entries if "duplicate" in (e.reason or "")]),
        }


def _register_file(files: list[FileLog], path: Path, display: str, origin: str) -> FileLog:
    fl = FileLog(path=str(path), display_name=display, size_bytes=path.stat().st_size, origin=origin)
    files.append(fl)
    return fl


def ingest_sources(sources: list[Path], workdir: Path, cfg: Config,
                   progress: Progress = _noop) -> IngestionResult:
    """Copy originals, expand archives safely, read and profile every supported file."""
    from .ingest import ARCHIVE_EXT, DOC_EXT, TABULAR_EXT, inspect_archive

    res = IngestionResult()
    originals_dir = workdir / "originals"
    extracted_dir = workdir / "extracted"
    originals_dir.mkdir(parents=True, exist_ok=True)
    extracted_dir.mkdir(parents=True, exist_ok=True)

    # ---- 1. stage originals (never overwritten, never mutated) ----
    staged: list[tuple[Path, str]] = []
    for src in sources:
        src = Path(src)
        candidates = [src] if src.is_file() else list(iter_source_files(src))
        for c in candidates:
            if len(res.files) >= cfg.limits.max_files_per_upload:
                raise IngestionError(
                    f"upload exceeds the configured limit of {cfg.limits.max_files_per_upload} files")
            if c.stat().st_size > cfg.limits.max_single_file_bytes:
                fl = _register_file(res.files, c, c.name, "upload")
                fl.status = "rejected"
                fl.reason = (f"file size {c.stat().st_size} bytes exceeds the configured limit of "
                             f"{cfg.limits.max_single_file_bytes} bytes")
                continue
            dest = ArtifactStore(workdir).copy_in(c, originals_dir)
            digest = sha256_file(dest)
            fl = _register_file(res.files, dest, c.name, "upload")
            fl.sha256 = digest
            res.originals.append({"name": c.name, "stored_as": dest.name, "bytes": dest.stat().st_size,
                                  "sha256": digest})
            staged.append((dest, dest.name))
    progress("staging uploads", 5, f"{len(staged)} original file(s) staged")

    # ---- 2. duplicate detection across uploads ----
    seen_hash: dict[str, str] = {}
    for fl in list(res.files):
        if not fl.sha256:
            continue
        if fl.sha256 in seen_hash:
            res.duplicates.append({"file": fl.display_name, "duplicate_of": seen_hash[fl.sha256],
                                   "sha256": fl.sha256})
            fl.status = "skipped"
            fl.reason = f"byte-identical duplicate of '{seen_hash[fl.sha256]}'; original preserved"
        else:
            seen_hash[fl.sha256] = fl.display_name

    # ---- 3. expand archives recursively, then read ----
    to_read: list[tuple[Path, FileLog]] = []
    queue: list[tuple[Path, FileLog, int]] = []
    for dest, name in staged:
        fl = next((f for f in res.files if f.path == str(dest)), None)
        if fl is None or fl.status in {"skipped", "rejected"}:
            continue
        suffix = dest.suffix.lower()
        if suffix in ARCHIVE_EXT:
            fl.kind = "archive"
            queue.append((dest, fl, 1))
        else:
            to_read.append((dest, fl))

    while queue:
        archive, fl, depth = queue.pop(0)
        try:
            entries, written = safe_extract(archive, extracted_dir / Path(archive).stem,
                                            cfg.limits, depth=depth)
        except IngestionError as exc:
            fl.status = "failed"
            fl.reason = str(exc)
            continue
        res.archive_entries.extend(entries)
        fl.tables_found = len(written)
        fl.status = "processed"
        nested = 0
        for w in written:
            sub = _register_file(res.files, w, w.name, f"archive:{fl.display_name}")
            sub.sha256 = sha256_file(w)
            if sub.sha256 in seen_hash and seen_hash[sub.sha256] != sub.display_name:
                res.duplicates.append({"file": sub.display_name, "duplicate_of": seen_hash[sub.sha256],
                                       "sha256": sub.sha256})
                sub.status = "skipped"
                sub.reason = (f"byte-identical duplicate of '{seen_hash[sub.sha256]}'; skipped so records "
                              "are not counted twice (the first copy is used)")
                continue
            seen_hash.setdefault(sub.sha256, sub.display_name)
            if w.suffix.lower() in ARCHIVE_EXT:
                if depth >= cfg.limits.max_nested_archive_depth:
                    sub.kind = "nested_archive"
                    sub.status = "skipped"
                    sub.reason = (f"nesting depth {depth} reached the configured limit "
                                  f"{cfg.limits.max_nested_archive_depth}")
                    continue
                sub.kind = "nested_archive"
                nested += 1
                queue.append((w, sub, depth + 1))
            else:
                to_read.append((w, sub))
        progress("extracting archives", 12, f"{Path(archive).name}: {len(written)} entr(ies) extracted, "
                                            f"{nested} nested archive(s) queued")

    files_total = max(1, len(to_read))
    for i, (path, fl) in enumerate(to_read):
        suffix = path.suffix.lower()
        if suffix in UNSAFE_EXT:
            fl.status = "unsupported"
            fl.reason = f"blocked file type '{suffix}'"
            continue
        try:
            tables = read_file(path, path.name, cfg.limits)
        except IngestionError as exc:
            fl.status = "unsupported" if "unsupported" in str(exc) or "requires" in str(exc) else "failed"
            fl.reason = str(exc)
            continue
        except Exception as exc:
            fl.status = "failed"
            fl.reason = f"{type(exc).__name__}: {exc}"
            continue
        fl.status = "processed"
        fl.tables_found = len(tables)
        fl.rows = sum(len(t.data_rows) for t in tables)
        types = []
        for t in tables:
            rel = _rel_to(path, workdir)
            t.source_path = rel
            try:
                p = profile_table(t)
            except Exception as exc:
                fl.status = "failed"
                fl.reason = f"profiling failed: {type(exc).__name__}: {exc}"
                continue
            types.append(p.record_type)
            res.tables.append(t)
            res.profiles.append(p)
        detected = [t for t in types if t != "unknown"]
        fl.record_type = detected[0] if detected else (types[0] if types else None)
        progress("reading files", 15 + 35 * (i + 1) / files_total,
                 f"{fl.display_name}: {len(tables)} table(s), types={sorted(set(types))}")
    return res


def _rel_to(path: Path, root: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path(root).resolve()))
    except ValueError:
        return Path(path).name


# ---------------------------------------------------------------------------
# Scope analysis (shared by global ranking and precomputed filter scopes)
# ---------------------------------------------------------------------------
def filter_records(records: list[dict[str, Any]], flt: dict[str, list[str]] | None) -> list[dict[str, Any]]:
    if not flt:
        return records
    out = []
    for r in records:
        ok = True
        for key, values in flt.items():
            if not values:
                continue
            if key == "team":
                if str(r.get("team") or "").strip() not in values:
                    ok = False
                    break
            else:
                if str(r.get(key) or "").strip() not in values:
                    ok = False
                    break
        if ok:
            out.append(r)
    return out


def filter_events(events: pl.DataFrame | None, flt: dict[str, list[str]] | None) -> pl.DataFrame | None:
    if events is None or not flt:
        return events
    expr = None
    for key, values in flt.items():
        if not values:
            continue
        if key == "competition":
            e = pl.col("competition").is_in(values)
        elif key == "season":
            e = pl.col("season").is_in(values)
        elif key == "team":
            e = pl.col("team_batting").is_in(values) | pl.col("team_bowling").is_in(values)
        else:
            continue
        expr = e if expr is None else (expr & e)
    return events if expr is None else events.filter(expr)


@dataclass
class ScopeAnalysis:
    batting: dict[str, dict[str, Any]]
    bowling: dict[str, dict[str, Any]]
    bat_raw: dict[str, Any]
    bowl_raw: dict[str, Any]
    pressure_bat: dict[str, dict[str, Any]]
    pressure_bowl: dict[str, dict[str, Any]]
    ppi_bat: dict[str, dict[str, Any]]
    ppi_bowl: dict[str, dict[str, Any]]
    phases: dict[str, Any] | None
    pressure_basis: str


def analyse_scope(bat_records: list[dict[str, Any]], bowl_records: list[dict[str, Any]],
                  events: pl.DataFrame | None, roles: dict[str, dict[str, Any]],
                  cfg: Config) -> ScopeAnalysis:
    bat_raw = bat_mod.compute_batting_raw(bat_records)
    bowl_raw = bowl_mod.compute_bowling_raw(bowl_records)

    phases = None
    pressure_bat: dict[str, dict[str, Any]] = {}
    pressure_bowl: dict[str, dict[str, Any]] = {}
    pressure_basis = "unavailable"
    impact: dict[str, dict[str, Any]] = {}
    if events is not None and events.height > 0:
        tagged = tag_ball_events(events, cfg)
        phases = phase_aggregates(tagged)
        pressure_bat = pressure_batting_metrics(tagged, cfg)
        pressure_bowl = pressure_bowling_metrics(tagged, cfg)
        impact = match_impact(tagged)
        pressure_basis = "ball_by_ball"
    elif any(b.get("innings_number") for b in bat_records):
        pressure_bat = pressure_proxy_from_records(bat_records, bowl_records, cfg)
        pressure_bowl = {k: v for k, v in pressure_bat.items()}
        pressure_basis = "innings_index_proxy"

    # provisional scored pass (needed for opposition adjustment inputs)
    scored_bat = bat_mod.score_batting_population(bat_raw, cfg, pressure_bat, roles)
    scored_bowl = bowl_mod.score_bowling_population(
        bowl_raw, cfg, pressure_bowl, phases["bowling"] if phases else None, roles)

    ctx = opposition_adjusted(bat_records, bowl_records, scored_bat, scored_bowl)
    for pid, m in scored_bat.items():
        m["opposition_adjusted"] = ctx["batting"].get(pid, {"score": None, "coverage": 0.0,
                                                            "basis": "unavailable",
                                                            "detail": {"reason": "opposition data missing"}})
        m["match_impact"] = impact.get(pid, {"score": None, "basis": "unavailable"})
    for pid, m in scored_bowl.items():
        m["opposition_adjusted"] = ctx["bowling"].get(pid, {"score": None, "coverage": 0.0,
                                                            "basis": "unavailable",
                                                            "detail": {"reason": "opposition data missing"}})
        m["match_impact"] = impact.get(pid, {"score": None, "basis": "unavailable"})

    # attach recent form
    attach_recent_form(scored_bat,
                       {p: raw.season_runs for p, raw in bat_raw.items()},
                       {p: raw.season_balls for p, raw in bat_raw.items()}, "batting")
    attach_recent_form(scored_bowl,
                       {p: raw.season_runs for p, raw in bowl_raw.items()},
                       {p: raw.season_balls for p, raw in bowl_raw.items()}, "bowling")

    # roles onto metrics
    for pid, m in scored_bat.items():
        r = roles.get(pid, {})
        m["primary_role"] = r.get("primary_role")
        m["secondary_role"] = r.get("secondary_role")
        m["role_basis"] = r.get("role_basis")
    for pid, m in scored_bowl.items():
        r = roles.get(pid, {})
        m["primary_role"] = r.get("primary_role")
        m["secondary_role"] = r.get("secondary_role")
        m["role_basis"] = r.get("role_basis")

    ppi_bat = pressure_performance_index(scored_bat, cfg, "batting")
    ppi_bowl = pressure_performance_index(scored_bowl, cfg, "bowling")
    for pid, v in ppi_bat.items():
        scored_bat[pid]["ppi"] = v
    for pid, v in ppi_bowl.items():
        scored_bowl[pid]["ppi"] = v

    return ScopeAnalysis(scored_bat, scored_bowl, bat_raw, bowl_raw, pressure_bat, pressure_bowl,
                         ppi_bat, ppi_bowl, phases, pressure_basis)


# ---------------------------------------------------------------------------
# Metric availability classification (Part 5 A/B/C/D)
# ---------------------------------------------------------------------------
def metric_availability(caps: dict[str, bool], tables: list[TableProfile]) -> list[dict[str, Any]]:
    has_bbb = caps.get("ball_by_ball", False)
    has_inns = caps.get("innings_granularity_batting", False)
    has_opp = caps.get("opposition_data", False)
    has_venue = caps.get("venue_data", False)
    fields_present = set()
    for t in tables:
        fields_present |= {m["field"] for m in t.to_dict()["mapping"] if m["field"]}

    def status(available: bool, derivable: bool = False, needs_verify: bool = False) -> str:
        if available:
            return "available"
        if derivable:
            return "derivable"
        if needs_verify:
            return "requires_verification"
        return "unavailable"

    rows = [
        {"metric": "Total runs / balls faced / 4s / 6s", "category": "batting",
         "status": status("runs" in fields_present), "note": "Counted directly from source records."},
        {"metric": "Batting average & strike rate", "category": "batting",
         "status": status("runs" in fields_present, derivable=True),
         "note": "Derived from runs, dismissals and balls faced; a separate value is never trusted over the components."},
        {"metric": "Not-outs and dismissals", "category": "batting",
         "status": status(("not_outs" in fields_present) or ("not_out" in fields_present) or ("dismissal" in fields_present), derivable=True),
         "note": "Recovered from explicit not-out flags, dismissal text, or innings-minus-not-outs."},
        {"metric": "Boundary and dot-ball percentages", "category": "batting",
         "status": status(("fours" in fields_present or "sixes" in fields_present) and "dot_balls_faced" in fields_present,
                          derivable=True),
         "note": "Boundary % is derivable from 4s/6s; dot % needs a dot-ball count or ball-by-ball data."},
        {"metric": "Innings-level scores (30+/50+/100+, ducks)", "category": "batting",
         "status": status(has_inns), "note": "Requires one row per innings."},
        {"metric": "Phase splits (powerplay/middle/death)", "category": "batting",
         "status": status(has_bbb), "note": "Requires ball-by-ball data with over numbers."},
        {"metric": "Performance vs pace / spin", "category": "batting",
         "status": status("bowling_style" in fields_present),
         "note": "Requires a bowling-style attribute; without it pace/spin splits cannot be inferred."},
        {"metric": "Performance after early wickets / recovery", "category": "batting",
         "status": status(has_bbb), "note": "Requires ball-level scoreboard state."},
        {"metric": "Overs, economy, bowling average & strike rate", "category": "bowling",
         "status": status("wickets" in fields_present and ("overs" in fields_present or "legal_balls" in fields_present),
                          derivable=True),
         "note": "Overs are converted to legal balls before any arithmetic."},
        {"metric": "Dot-ball percentage (bowling)", "category": "bowling",
         "status": status("dot_balls_bowled" in fields_present or has_bbb),
         "note": "Needs an explicit dot count or ball-by-ball data."},
        {"metric": "Boundary prevention rate", "category": "bowling",
         "status": status(has_bbb), "note": "Requires ball-level boundary events."},
        {"metric": "Wickets per match", "category": "bowling",
         "status": status("matches" in fields_present),
         "note": "Needs a match count per player, which aggregate exports often omit."},
        {"metric": "Actual match-pressure performance", "category": "pressure",
         "status": status(has_bbb),
         "note": "Only computable from ball-by-ball data. Aggregate exports cannot support it."},
        {"metric": "Leverage / win-expectancy weighting", "category": "pressure",
         "status": status(has_bbb and caps.get("targets_available", False)),
         "note": "Requires ball-by-ball data with a target; the estimator is a documented heuristic, not a validated model."},
        {"metric": "Chasing vs defending (innings index)", "category": "pressure",
         "status": status(has_inns and ("innings_number" in fields_present), derivable=False),
         "note": "A record-level proxy only, never a substitute for match-pressure performance."},
        {"metric": "Opposition-adjusted performance", "category": "context",
         "status": status(has_opp and ("opposition" in fields_present)),
         "note": "First-order ratio adjustment using observed team strength."},
        {"metric": "Venue splits", "category": "context",
         "status": status(has_venue), "note": "Requires a venue column."},
        {"metric": "Competition & season adjustment", "category": "context",
         "status": status("competition" in fields_present and "season" in fields_present),
         "note": "Available as filters and as slices; no cross-competition normalisation is applied unless configured."},
        {"metric": "Wicketkeeper identification", "category": "role",
         "status": status("role" in fields_present or "dismissal" in fields_present),
         "note": "Only from a declared role; never inferred from statistics alone."},
    ]
    return rows


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def run_pipeline(sources: list[Path], storage_root: Path, project_id: str, dataset_id: str,
                 dataset_name: str, cfg: Config | None = None, version: int = 1,
                 is_fixture: bool = False, progress: Progress = _noop,
                 export: bool = True) -> dict[str, Any]:
    cfg = cfg or DEFAULT_CONFIG
    t0 = time.time()
    workdir = ArtifactStore(storage_root).dataset_dir(project_id, dataset_id)
    progress("starting", 1, f"dataset {dataset_id} ({dataset_name})")
    progress("scanning files", 2, f"{len(sources)} source(s)")

    ing = ingest_sources(sources, workdir, cfg, progress)
    progress("canonicalising", 52, f"{len(ing.profiles)} table(s) profiled")

    pack_dir = provider_superr.detect(sources)
    if pack_dir is not None:
        progress("canonicalising", 52, f"SupeRR provider pack detected at {pack_dir.name}")
        cd = provider_superr.build(pack_dir, cfg)
    else:
        cd = build_canonical(ing.tables, ing.profiles, include_aggregates=True)
    progress("auditing quality", 62, f"{len(cd.batting)} batting / {len(cd.bowling)} bowling records")

    quality = run_quality_audit(ing.tables, ing.profiles, cd)
    progress("classifying roles", 68, "")

    declared = {p: a["declared_role"] for p, a in cd.player_attributes.items()
                if a.get("declared_role")}
    for r in cd.batting + cd.bowling:
        if r.get("declared_role"):
            declared.setdefault(r["player"], r["declared_role"])
    bat_raw = bat_mod.compute_batting_raw(cd.batting)
    bowl_raw = bowl_mod.compute_bowling_raw(cd.bowling)
    roles = classify_roles(bat_raw, bowl_raw, declared, cfg)

    progress("computing analytics", 72, "")
    events = cd.ball_events
    global_scope = analyse_scope(cd.batting, cd.bowling, events, roles, cfg)
    progress("ranking", 80, "")

    bat_lb = build_leaderboard(global_scope.batting, cfg, "batting",
                               {"type": "global", "label": "All data", "filter": {}})
    bowl_lb = build_leaderboard(global_scope.bowling, cfg, "bowling",
                               {"type": "global", "label": "All data", "filter": {}})

    # ---- precomputed filter scopes ----
    scopes_out: list[dict[str, Any]] = []
    scope_defs = candidate_scopes(cd.batting, cd.bowling)
    for i, sc in enumerate(scope_defs):
        flt = sc["filter"]
        if not flt:
            lb_b, lb_w = bat_lb, bowl_lb
        else:
            sb = analyse_scope(filter_records(cd.batting, flt), filter_records(cd.bowling, flt),
                               filter_events(events, flt), roles, cfg)
            lb_b = build_leaderboard(sb.batting, cfg, "batting", sc)
            lb_w = build_leaderboard(sb.bowling, cfg, "bowling", sc)
        scopes_out.append({
            "scope": {"type": sc["type"], "label": sc["label"], "filter": flt},
            "batters": [_slim_row(r) for r in lb_b.rows[:60]],
            "bowlers": [_slim_row(r) for r in lb_w.rows[:60]],
            "batters_evaluated": lb_b.evaluated_count,
            "bowlers_evaluated": lb_w.evaluated_count,
            "batters_eligible": lb_b.eligible_count,
            "bowlers_eligible": lb_w.eligible_count,
        })
        progress("precomputing filter scopes", 80 + 8 * (i + 1) / max(1, len(scope_defs)),
                 sc["label"])

    # ---- stability ----
    progress("testing ranking stability", 89, "perturbing weights, priors and eligibility floors")
    stab_bat = stability_analysis(
        lambda c: bat_mod.score_batting_population(bat_raw, c, global_scope.pressure_bat, roles),
        cfg, "rabi", "batting")
    stab_bowl = stability_analysis(
        lambda c: bowl_mod.score_bowling_population(
            bowl_raw, c, global_scope.pressure_bowl,
            global_scope.phases["bowling"] if global_scope.phases else None, roles),
        cfg, "rabi_bowl", "bowling")

    caps = cd.capabilities
    limitations = _limitations(caps, quality, ing)
    bundle: dict[str, Any] = {
        "meta": {
            "project_id": project_id, "dataset_id": dataset_id, "name": dataset_name,
            "dataset_version": version, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model_version": MODEL_VERSION, "config_fingerprint": cfg.fingerprint(),
            "config": cfg.to_dict(), "is_fixture": is_fixture,
            "processing_seconds": None, "limitations": limitations,
            "data_source_note": ("SYNTHETIC TEST FIXTURE — not real player data. Excluded from any "
                                 "production ranking." if is_fixture else
                                 "Imported scouting dataset."),
        },
        "ingestion": {
            "summary": ing.summary(),
            "files": [f.to_dict() for f in ing.files],
            "archive_entries": [e.to_dict() for e in ing.archive_entries],
            "originals": ing.originals,
            "duplicates": ing.duplicates,
            "duration_seconds": round(time.time() - t0, 2),
        },
        "schema": {
            "tables": [p.to_dict() for p in ing.profiles],
            "capabilities": caps,
            "unmapped_tables": cd.unmapped_tables,
            "players": cd.registry.to_dict(),
            "derivations": cd.derivations[:500],
            "derivations_total": len(cd.derivations),
            "player_attributes": cd.player_attributes,
        },
        "quality": quality.to_dict(),
        "roles": roles,
        "batting": {
            "players": global_scope.batting,
            "splits": bat_mod.batting_situational_splits(cd.batting),
            "leaderboard": bat_lb.to_dict(),
        },
        "bowling": {
            "players": global_scope.bowling,
            "splits": bowl_mod.bowling_situational_splits(cd.bowling),
            "leaderboard": bowl_lb.to_dict(),
        },
        "leaderboards": {
            "global": {
                "batters": [_export_row(r) for r in bat_lb.rows[:cfg.eligibility.leaderboard_size]],
                "bowlers": [_export_row(r) for r in bowl_lb.rows[:cfg.eligibility.leaderboard_size]],
                "batters_eligible": bat_lb.eligible_count,
                "bowlers_eligible": bowl_lb.eligible_count,
                "batters_evaluated": bat_lb.evaluated_count,
                "bowlers_evaluated": bowl_lb.evaluated_count,
                "batters_excluded": bat_lb.excluded[:40],
                "bowlers_excluded": bowl_lb.excluded[:40],
                "alternative_ranks": bat_lb.alternative_ranks,
                "alternative_ranks_bowling": bowl_lb.alternative_ranks,
            },
            "scopes": scopes_out,
        },
        "pressure": {
            "phases": global_scope.phases,
            "scenarios": scenario_table(cfg),
            "basis": global_scope.pressure_basis,
            "batting": global_scope.pressure_bat,
            "bowling": global_scope.pressure_bowl,
            "ppi_batting": global_scope.ppi_bat,
            "ppi_bowling": global_scope.ppi_bowl,
            "phases_available": global_scope.phases is not None,
        },
        "stability": {"batting": stab_bat, "bowling": stab_bowl},
        "metric_availability": metric_availability(caps, ing.profiles),
        "settings": cfg.to_dict(),
        "counts": {
            "players": len(roles), "batters": len(global_scope.batting),
            "bowlers": len(global_scope.bowling),
            "batting_records": len(cd.batting), "bowling_records": len(cd.bowling),
            "ball_events": events.height if events is not None else 0,
            "matches": len({r.get("match_id") for r in cd.batting + cd.bowling if r.get("match_id")}),
            "competitions": len({r.get("competition") for r in cd.batting + cd.bowling if r.get("competition")}),
            "seasons": len({r.get("season") for r in cd.batting + cd.bowling if r.get("season")}),
            "teams": len({r.get("team") for r in cd.batting + cd.bowling if r.get("team")}),
        },
    }
    bundle["meta"]["processing_seconds"] = round(time.time() - t0, 2)
    progress("writing artefacts", 93, "")

    # ---- durable artefacts ----
    canon = workdir / "canonical"
    cd.batting_frame().write_parquet(canon / "batting_records.parquet") if cd.batting else None
    cd.bowling_frame().write_parquet(canon / "bowling_records.parquet") if cd.bowling else None
    if events is not None and events.height:
        events.write_parquet(canon / "ball_events.parquet")
    write_json(workdir / "bundle.json", bundle)
    write_json(workdir / "ingestion_report.json", bundle["ingestion"])
    write_json(workdir / "quality_report.json", bundle["quality"])
    write_json(workdir / "config.json", cfg.to_dict())

    if export:
        exports_dir = workdir / "exports"
        prov = provenance_block(bundle)
        write_csv(exports_dir / "top30_batters.csv", BAT_COLUMNS, bundle["leaderboards"]["global"]["batters"], prov)
        write_csv(exports_dir / "top30_bowlers.csv", BOWL_COLUMNS, bundle["leaderboards"]["global"]["bowlers"], prov)
        try:
            export_workbook(bundle, exports_dir)
        except Exception as exc:
            write_json(exports_dir / "workbook_error.json", {"error": f"{type(exc).__name__}: {exc}"})
        try:
            write_pdf(exports_dir / "scouting_report_batting.pdf", bundle, "batting",
                      bundle["leaderboards"]["global"]["batters"])
            write_pdf(exports_dir / "scouting_report_bowling.pdf", bundle, "bowling",
                      bundle["leaderboards"]["global"]["bowlers"])
        except Exception as exc:
            write_json(exports_dir / "pdf_error.json", {"error": f"{type(exc).__name__}: {exc}"})

    progress("complete", 100, f"{len(bundle['leaderboards']['global']['batters'])} batters / "
                              f"{len(bundle['leaderboards']['global']['bowlers'])} bowlers ranked")
    return bundle


_EXPORT_KEYS = ["rank", "player", "teams", "primary_role", "secondary_role", "matches", "innings",
                "runs", "balls_faced", "fours", "sixes", "boundary_pct", "dot_pct", "not_outs",
                "dismissals", "average", "strike_rate", "runs_per_innings", "highest_score",
                "scores_30", "scores_50", "scores_100", "ducks", "consistency", "reliability",
                "performance_score", "pressure_score", "role_adjusted_score", "confidence_score",
                "grade", "rabi", "score_coverage", "exposure_balls", "granularity",
                "overs", "legal_balls", "runs_conceded", "wickets", "economy",
                "bowling_strike_rate", "wickets_per_innings", "best_bowling", "multi_wicket_innings",
                "wicket_taking_score", "economy_containment_score", "bowler_type", "rabi_bowl",
                "recent_form_score", "ppi"]


def _export_row(row: dict[str, Any]) -> dict[str, Any]:
    out = {k: row.get(k) for k in _EXPORT_KEYS if k in row}
    out["eligibility_reason"] = row.get("eligibility_reason")
    out["teams"] = row.get("teams") or []
    return out


def _slim_row(row: dict[str, Any]) -> dict[str, Any]:
    keep = ["rank", "player", "teams", "primary_role", "innings", "matches", "runs", "balls_faced",
            "average", "strike_rate", "fours", "sixes", "overs", "legal_balls", "wickets",
            "runs_conceded", "economy", "bowling_strike_rate", "dot_pct", "consistency",
            "pressure_score", "grade", "rabi", "rabi_bowl", "score_coverage", "exposure_balls",
            "wicket_taking_score", "economy_containment_score"]
    return {k: row.get(k) for k in keep if k in row}


def _limitations(caps: dict[str, bool], quality, ing: IngestionResult) -> list[str]:
    lim: list[str] = []
    if not caps.get("ball_by_ball"):
        lim.append("No ball-by-ball data was supplied, so phase splits, actual match-pressure "
                   "performance, boundary prevention and leverage weighting are unavailable. "
                   "Record-level chasing proxies are labelled as proxies.")
    if caps.get("aggregate_only_batting"):
        lim.append("Batting data is aggregate-only: match-level consistency, form trend and "
                   "innings-level score counts cannot be computed.")
    if not caps.get("opposition_data"):
        lim.append("No opposition column was found: opposition-adjusted PPI component unavailable.")
    if not caps.get("venue_data"):
        lim.append("No venue column was found: venue splits unavailable.")
    if quality.summary.get("unmapped_tables"):
        lim.append(f"{quality.summary['unmapped_tables']} table(s) could not be mapped and were excluded; "
                   "they are listed in the schema section for manual review.")
    failed = [f for f in ing.files if f.status in ("failed", "unsupported")]
    if failed:
        lim.append(f"{len(failed)} file(s) could not be processed and are listed with explicit reasons "
                   "in the ingestion report.")
    if quality.findings:
        lim.append(f"{len(quality.findings)} data-quality finding(s) were raised; see the Data Audit "
                   "page before acting on any ranking.")
    return lim
