"""Data quality & forensics center.

Produces the per-column audit table, cricket-specific validation findings and a
transparent 0-100 data-quality score. Findings always reference lineage.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from .canonical import CanonicalData, GRANULARITY_INNINGS, name_key
from .ingest import RawTable, TableProfile
from .schema import is_nullish, parse_overs, to_float, to_int

STATUS_OK = "ok"
STATUS_WARN = "warn"
STATUS_FAIL = "fail"


@dataclass
class ColumnAudit:
    file: str
    worksheet: str
    column: str
    canonical_field: str
    total: int
    missing: int
    invalid: int
    duplicate: int
    status: str = STATUS_OK
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file, "worksheet": self.worksheet, "column": self.column,
            "canonical_field": self.canonical_field, "total_records": self.total,
            "missing": self.missing, "invalid": self.invalid, "duplicate": self.duplicate,
            "missing_pct": round(100 * self.missing / self.total, 2) if self.total else None,
            "invalid_pct": round(100 * self.invalid / self.total, 2) if self.total else None,
            "status": self.status, "notes": self.notes,
        }


def _validate_value(field_name: str, raw: Any) -> str | None:
    """Return an error string when a value is impossible for the canonical field."""
    if is_nullish(raw):
        return None
    if field_name in {"runs", "runs_conceded", "wickets", "balls_faced", "legal_balls", "fours",
                      "sixes", "innings", "matches", "not_outs", "dismissals", "dot_balls_faced",
                      "dot_balls_bowled", "over_number", "ball_number", "batter_runs"}:
        v = to_int(raw)
        if v is None:
            return "non-integer value"
        if v < 0:
            return "negative value"
        if field_name == "wickets" and v > 10:
            return "more than 10 wickets in a bowling record"
        if field_name == "fours" and v > 100:
            return "implausible four count"
        if field_name == "sixes" and v > 100:
            return "implausible six count"
        if field_name == "ball_number" and v > 12:
            return "ball number outside 1-12"
        return None
    if field_name in {"overs", "economy", "strike_rate", "batting_average", "required_run_rate"}:
        if field_name == "overs":
            balls, err = parse_overs(raw)
            return err
        v = to_float(raw)
        if v is None:
            return "non-numeric value"
        if v < 0:
            return "negative value"
        if field_name == "strike_rate" and v > 500:
            return "strike rate above 500 is implausible"
        if field_name == "economy" and v > 60:
            return "economy above 60 is implausible"
        return None
    return None


def audit_tables(tables: list[RawTable], profiles: list[TableProfile]) -> list[ColumnAudit]:
    audits: list[ColumnAudit] = []
    for t, p in zip(tables, profiles):
        mapping = {m.column: m for m in p.mapping}
        rows = t.data_rows
        total = len(rows)
        # duplicate rows across the whole table
        seen: Counter[str] = Counter()
        for r in rows:
            seen["|".join(str(c).strip() for c in r)] += 1
        dup_rows = sum(v - 1 for v in seen.values() if v > 1)
        for ci, col in enumerate(p.columns):
            m = mapping.get(col)
            field_name = m.field if m else ""
            missing = invalid = 0
            notes: list[str] = []
            for r in rows:
                val = r[ci] if ci < len(r) else None
                if is_nullish(val):
                    missing += 1
                elif field_name:
                    err = _validate_value(field_name, val)
                    if err:
                        invalid += 1
                        if err not in notes and len(notes) < 4:
                            notes.append(err)
            if m and m.needs_review:
                notes.append("mapping needs review: " + (", ".join(m.ambiguous_with) or "low confidence"))
            status = STATUS_OK
            if total and (missing / total) > 0.5:
                status = STATUS_WARN
                notes.append("more than 50% missing")
            if total and (invalid / total) > 0.02:
                status = STATUS_FAIL
            if m and m.needs_review:
                status = STATUS_WARN if status == STATUS_OK else status
            audits.append(ColumnAudit(
                file=t.source_path, worksheet=t.meta.get("worksheet") or t.table_name,
                column=col, canonical_field=field_name, total=total, missing=missing,
                invalid=invalid, duplicate=dup_rows, status=status, notes=notes))
    return audits


@dataclass
class QualityReport:
    audited_columns: list[ColumnAudit]
    findings: list[dict[str, Any]]
    summary: dict[str, Any]
    score: float
    components: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 2),
            "components": {k: round(v, 2) for k, v in self.components.items()},
            "summary": self.summary,
            "columns": [a.to_dict() for a in self.audited_columns],
            "findings": self.findings,
        }


def _finding(code: str, severity: str, message: str, count: int,
             impact: str, sample: list[Any] | None = None) -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message, "count": count,
            "impact": impact, "sample": (sample or [])[:5]}


def run_quality_audit(tables: list[RawTable], profiles: list[TableProfile],
                      cd: CanonicalData) -> QualityReport:
    audits = audit_tables(tables, profiles)
    findings: list[dict[str, Any]] = []

    # ---- structural ----
    total_cells = sum(a.total for a in audits) or 1
    total_missing = sum(a.missing for a in audits)
    missing_pct = 100 * total_missing / total_cells
    failed_cols = [a for a in audits if a.status == STATUS_FAIL]
    warn_cols = [a for a in audits if a.status == STATUS_WARN]
    if cd.unmapped_tables:
        findings.append(_finding(
            "unmapped_tables", "high",
            f"{len(cd.unmapped_tables)} table(s) could not be mapped to a cricket record type and were "
            "excluded from analytics. They are listed for manual schema review.",
            len(cd.unmapped_tables), "records in these tables are absent from all metrics",
            [u["source_path"] + " / " + u["table"] for u in cd.unmapped_tables]))

    # ---- duplicate rows ----
    dup_total = 0
    dup_files: list[str] = []
    for a in audits:
        if a.duplicate:
            dup_files.append(a.file)
    if dup_files:
        dup_total = len(set(dup_files))

    # ---- cricket-specific validations on canonical records ----
    bat = cd.batting
    bowl = cd.bowling
    issues: dict[str, list[Any]] = defaultdict(list)

    for b in bat:
        label = f"{b['player']} ({b.get('season') or 'n/a'}) @ {b.get('source_file')}"
        if b.get("balls_faced") is not None and b["runs"] is not None:
            if b["balls_faced"] < 0:
                issues["negative_balls"].append(label)
            elif b["runs"] > b["balls_faced"] * 6:
                issues["impossible_run_totals"].append(
                    f"{label}: {b['runs']} runs off {b['balls_faced']} balls")
        boundary_runs = 4 * (b.get("fours") or 0) + 6 * (b.get("sixes") or 0)
        if boundary_runs > b["runs"]:
            issues["boundary_exceeds_runs"].append(
                f"{label}: boundary runs {boundary_runs} > total runs {b['runs']}")
        if b.get("not_outs") is not None and b["not_outs"] > (b.get("innings_count") or 1):
            issues["notouts_exceed_innings"].append(label)
        if b.get("dismissals") is not None and b["dismissals"] < 0:
            issues["negative_dismissals"].append(label)
        if b.get("dismissals") is not None and b.get("innings_count") and \
                b["dismissals"] + (b.get("not_outs") or 0) != b["innings_count"]:
            issues["innings_notouts_dismissals_mismatch"].append(
                f"{label}: innings {b['innings_count']} != dismissals {b['dismissals']} + "
                f"not-outs {b.get('not_outs')}")

    for w in bowl:
        label = f"{w['player']} ({w.get('season') or 'n/a'}) @ {w.get('source_file')}"
        if "invalid_overs" in (w.get("flags") or []):
            issues["invalid_overs"].append(f"{label}: '{w.get('overs_value')}'")
        if w.get("legal_balls") is not None and w["legal_balls"] > 300 and w["granularity"] == GRANULARITY_INNINGS:
            issues["implausible_balls_in_innings"].append(f"{label}: {w['legal_balls']} balls")
        if w.get("wickets") is not None and w["wickets"] > 10:
            issues["wickets_above_limit"].append(f"{label}: {w['wickets']} wickets")
        if w.get("runs_conceded") is not None and w["runs_conceded"] < 0:
            issues["negative_runs_conceded"].append(label)
        if w.get("dot_balls") and w.get("legal_balls") and w["dot_balls"] > w["legal_balls"]:
            issues["dots_exceed_balls"].append(label)

    # ---- cross-field consistency checks (recomputation vs stated value) ----
    recalc = {"strike_rate": [0, 0], "economy": [0, 0], "batting_average": [0, 0]}
    for t, p in zip(tables, profiles):
        mapping = {m.field: m.column for m in p.mapping if m.field}
        if not mapping:
            continue
        cols = p.columns
        for ri, row in enumerate(t.data_rows):
            def get(fname: str) -> Any:
                c = mapping.get(fname)
                return row[cols.index(c)] if c in cols else None
            runs, balls, sr = to_int(get("runs")), to_int(get("balls_faced")), to_float(get("strike_rate"))
            if runs is not None and balls and sr:
                recalc["strike_rate"][1] += 1
                if abs(sr - runs * 100 / balls) > max(3.0, 0.05 * sr):
                    recalc["strike_rate"][0] += 1
                    if len(issues["strike_rate_mismatch"]) < 20:
                        issues["strike_rate_mismatch"].append(
                            f"{t.source_path} row {t.header_row + 2 + ri}: stated SR {sr} vs "
                            f"recomputed {runs * 100 / balls:.1f}")
            rc, ov, econ = to_int(get("runs_conceded")), get("overs"), to_float(get("economy"))
            if rc is not None and not is_nullish(ov) and econ:
                balls_b, err = parse_overs(ov)
                if balls_b:
                    recalc["economy"][1] += 1
                    if abs(econ - rc * 6 / balls_b) > max(0.35, 0.08 * econ):
                        recalc["economy"][0] += 1
                        if len(issues["economy_mismatch"]) < 20:
                            issues["economy_mismatch"].append(
                                f"{t.source_path} row {t.header_row + 2 + ri}: stated econ {econ} vs "
                                f"recomputed {rc * 6 / balls_b:.2f}")
            ravg, dismissals = to_float(get("batting_average")), to_int(get("dismissals"))
            if runs is not None and dismissals and ravg:
                recalc["batting_average"][1] += 1
                if abs(ravg - runs / dismissals) > max(1.0, 0.08 * ravg):
                    recalc["batting_average"][0] += 1
                    if len(issues["average_mismatch"]) < 20:
                        issues["average_mismatch"].append(
                            f"{t.source_path} row {t.header_row + 2 + ri}: stated avg {ravg} vs "
                            f"recomputed {runs / dismissals:.2f}")

    severity_map = {
        "impossible_run_totals": ("high", "record excluded from rate metrics where invalid",
                                  "Runs cannot exceed 6 per ball faced."),
        "boundary_exceeds_runs": ("high", "counts may indicate swapped 4s/6s columns",
                                  "Boundary runs cannot exceed total runs."),
        "notouts_exceed_innings": ("high", "batting average may be understated",
                                   "Not-outs cannot exceed innings."),
        "innings_notouts_dismissals_mismatch": ("medium", "dismissal counts inconsistently derived",
                                                "Innings must equal dismissals + not-outs."),
        "invalid_overs": ("high", "bowling workload and economy unreliable for affected rows",
                          "Overs use cricket notation; the fractional part must be 0-5."),
        "wickets_above_limit": ("high", "row excluded from bowling aggregates", "Max 10 wickets per innings."),
        "implausible_balls_in_innings": ("medium", "possibly an aggregate row misclassified as an innings",
                                         "An innings cannot exceed 300 legal balls."),
        "dots_exceed_balls": ("high", "dot-ball percentage invalid", "Dots cannot exceed deliveries."),
        "negative_balls": ("high", "record rejected", "Negative deliveries."),
        "negative_dismissals": ("high", "record rejected", "Negative dismissals."),
        "negative_runs_conceded": ("high", "record rejected", "Negative runs."),
        "strike_rate_mismatch": ("medium", "uses recomputed value where possible",
                                 "Stated SR differs from runs/balls by >5%."),
        "economy_mismatch": ("medium", "uses recomputed value where possible",
                             "Stated economy differs from runs/overs by >8%."),
        "average_mismatch": ("medium", "flags possible dismissal-count errors",
                             "Stated average differs from runs/dismissals by >8%."),
    }
    for code, items in issues.items():
        if not items:
            continue
        sev, impact, explanation = severity_map.get(code, ("medium", "review recommended", ""))
        findings.append(_finding(code, sev, f"{explanation} {len(items)} affected record(s).",
                                 len(items), impact, items))

    # ---- player identity ----
    if cd.registry.suggestions:
        findings.append(_finding(
            "player_identity_suggestions", "medium",
            f"{len(cd.registry.suggestions)} pair(s) of similar player names require manual merge review. "
            "They were NOT merged automatically.", len(cd.registry.suggestions),
            "players may appear split across rows until resolved",
            [f"{s['a']} <> {s['b']} ({s['similarity']:.3f})" for s in cd.registry.suggestions]))
    if cd.registry.conflicts:
        findings.append(_finding(
            "player_team_conflicts", "medium",
            f"{len(cd.registry.conflicts)} player(s) map to multiple teams.", len(cd.registry.conflicts),
            "team filters may split a player's record", [c["player"] for c in cd.registry.conflicts]))

    # ---- derived values ----
    derived_balls = sum(1 for d in cd.derivations if d["kind"] == "balls_from_strike_rate")
    derived_econ = sum(1 for d in cd.derivations if d["kind"] == "balls_from_economy")
    if derived_balls or derived_econ:
        findings.append(_finding(
            "derived_exposure", "low",
            f"{derived_balls} batting balls figure(s) and {derived_econ} bowling workload(s) were "
            "back-calculated from stated rates. These are approximations and are flagged on every "
            "affected record.", derived_balls + derived_econ,
            "works beside directly reported values; confidence scores are reduced for derived exposure"))

    # ---- aggregate-only warning ----
    if cd.capabilities.get("aggregate_only_batting") or (
            cd.batting and not cd.capabilities.get("innings_granularity_batting")):
        findings.append(_finding(
            "aggregate_only_batting", "medium",
            "Batting data contains only multi-innings aggregates.", 1,
            "match-level consistency, form trend and phase splits are unavailable; aggregate-level "
            "dispersion is used and labelled as such"))

    # ---- score ----
    completeness = max(0.0, 100 - missing_pct * 1.6)
    invalid_cells = sum(a.invalid for a in audits)
    validity = max(0.0, 100 - 100 * invalid_cells / total_cells * 25)
    unmapped_penalty = min(25.0, 5.0 * len(cd.unmapped_tables))
    high_findings = len([f for f in findings if f["severity"] == "high"])
    med_findings = len([f for f in findings if f["severity"] == "medium"])
    findings_penalty = min(30.0, 5.0 * high_findings + 2.0 * med_findings)
    identity_penalty = min(10.0, 1.0 * len(cd.registry.suggestions) + 2.0 * len(cd.registry.conflicts))
    score = (
        0.30 * completeness
        + 0.30 * validity
        + 0.15 * (100 - unmapped_penalty)
        + 0.15 * (100 - findings_penalty)
        + 0.10 * (100 - identity_penalty)
    )
    components = {
        "completeness": completeness,
        "validity": validity,
        "schema_coverage": 100 - unmapped_penalty,
        "cricket_rule_conformance": 100 - findings_penalty,
        "identity_confidence": 100 - identity_penalty,
    }
    summary = {
        "tables_profiled": len(profiles),
        "columns_audited": len(audits),
        "total_cells": total_cells,
        "missing_cells": total_missing,
        "missing_pct": round(missing_pct, 2),
        "invalid_cells": invalid_cells,
        "columns_failed": len(failed_cols),
        "columns_warned": len(warn_cols),
        "batting_records": len(cd.batting),
        "bowling_records": len(cd.bowling),
        "ball_events": cd.ball_events.height if cd.ball_events is not None else 0,
        "unique_players": len(cd.registry.aliases),
        "unmapped_tables": len(cd.unmapped_tables),
        "derivations": len(cd.derivations),
        "duplicate_files": dup_total,
        "findings_high": high_findings,
        "findings_medium": med_findings,
    }
    return QualityReport(audits, findings, summary, score, components)
