"""Export centre: CSV, Excel workbooks and PDF scouting reports.

Every export carries a provenance block (calculation date, dataset, model
version, config fingerprint, ranking method, sample-size rules and the known
limitations of the data) so a downloaded artefact can always be reproduced.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

BAT_COLUMNS = [
    ("rank", "Rank"), ("player", "Player"), ("teams", "State Team"), ("primary_role", "Role"),
    ("matches", "Matches"), ("innings", "Innings"), ("runs", "Runs"), ("balls_faced", "Balls"),
    ("average", "Average"), ("strike_rate", "Strike Rate"), ("fours", "4s"), ("sixes", "6s"),
    ("boundary_pct", "Boundary %"), ("dot_pct", "Dot %"), ("consistency", "Consistency"),
    ("pressure_score", "Pressure"), ("grade", "Confidence"), ("rabi", "Final Score"),
    ("score_coverage", "Score Coverage"),
]
BOWL_COLUMNS = [
    ("rank", "Rank"), ("player", "Player"), ("teams", "State Team"), ("primary_role", "Role"),
    ("innings", "Innings"), ("overs", "Overs"), ("wickets", "Wickets"),
    ("runs_conceded", "Runs Conceded"), ("average", "Average"), ("economy", "Economy"),
    ("bowling_strike_rate", "Strike Rate"), ("dot_pct", "Dot %"), ("consistency", "Consistency"),
    ("pressure_score", "Pressure"), ("grade", "Confidence"), ("rabi_bowl", "Final Score"),
    ("score_coverage", "Score Coverage"),
]


def _fmt(v: Any) -> Any:
    if isinstance(v, list):
        return "; ".join(str(x) for x in v)
    if isinstance(v, dict):
        return json.dumps(v, separators=(",", ":"))
    if v is None:
        return ""
    return v


def provenance_block(bundle: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    meta = bundle.get("meta", {})
    cfg = meta.get("config", {})
    q = bundle.get("quality", {}).get("summary", {})
    return {
        "calculation_date_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset_id": meta.get("dataset_id"),
        "dataset_name": meta.get("name"),
        "dataset_version": meta.get("dataset_version"),
        "model_version": meta.get("model_version"),
        "metric_semantics_version": meta.get("metric_semantics_version"),
        "config_fingerprint": meta.get("config_fingerprint"),
        "ranking_method": "Reliability-Adjusted Index (coverage-weighted composite with shrinkage and "
                          "confidence grading)",
        "sample_size_rules": {
            "batting_ranked_minimum_balls": cfg.get("eligibility", {}).get("bat_min_balls_ranked"),
            "batting_ranked_minimum_innings": cfg.get("eligibility", {}).get("bat_min_innings_ranked"),
            "bowling_ranked_minimum_balls": cfg.get("eligibility", {}).get("bowl_min_balls_ranked"),
            "shrunk_prior_k_balls": cfg.get("stats", {}).get("prior_strength_balls_bat"),
        },
        "data_limitations": bundle.get("meta", {}).get("limitations", []),
        "ball_by_ball_available": q.get("ball_events", 0) > 0,
        "quality_score": bundle.get("quality", {}).get("score"),
        "filters": extra or {},
        "fixture_data": meta.get("is_fixture", False),
    }


def write_csv(path: Path, columns: list[tuple[str, str]], rows: Iterable[dict[str, Any]],
              provenance: dict[str, Any] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        if provenance:
            for k, v in provenance.items():
                fh.write(f"# {k}: {_fmt(v) if not isinstance(v, dict) else json.dumps(v)}\n")
            fh.write("#\n")
        w = csv.writer(fh)
        w.writerow([label for _, label in columns])
        for r in rows:
            w.writerow([_fmt(r.get(key)) for key, _ in columns])
    return path


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def write_excel(path: Path, sheets: dict[str, tuple[list[tuple[str, str]], list[dict[str, Any]]]],
                provenance: dict[str, Any] | None = None) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    wb.remove(wb.active)
    header_fill = PatternFill("solid", fgColor="0B1B33")
    header_font = Font(color="FFFFFF", bold=True)
    if provenance:
        ws = wb.create_sheet("Provenance")
        ws.append(["Field", "Value"])
        for c in ws[1]:
            c.fill, c.font = header_fill, header_font
        for k, v in provenance.items():
            ws.append([k, _fmt(v) if not isinstance(v, (dict, list)) else json.dumps(v, default=str)])
        ws.column_dimensions["A"].width = 34
        ws.column_dimensions["B"].width = 90
    for name, (cols, rows) in sheets.items():
        ws = wb.create_sheet(name[:31])
        ws.append([label for _, label in cols])
        for c in ws[1]:
            c.fill, c.font = header_fill, header_font
            c.alignment = Alignment(horizontal="center")
        for r in rows:
            ws.append([_fmt(r.get(k)) for k, _ in cols])
        for i, _ in enumerate(cols, start=1):
            width = max(10, min(38, max([len(str(label)) for _, label in cols] + [12]) + 2))
            ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = width
        ws.freeze_panes = "A2"
    wb.save(path)
    return path


def write_pdf(path: Path, bundle: dict[str, Any], discipline: str = "batting",
              rows: list[dict[str, Any]] | None = None, player: str | None = None) -> Path:
    """A one-to-two page scouting report. Requires reportlab (declared dependency)."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                        TableStyle)
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "PDF export requires the 'reportlab' package, which is not installed in this worker. "
            "Install it (see WORKER_SETUP.md) or export CSV/Excel instead.") from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    meta = bundle.get("meta", {})
    styles = getSampleStyleSheet()
    navy = colors.HexColor("#0B1B33")
    pink = colors.HexColor("#E8117F")
    title = ParagraphStyle("t", parent=styles["Title"], textColor=navy, fontSize=19, spaceAfter=2)
    sub = ParagraphStyle("s", parent=styles["Normal"], textColor=colors.HexColor("#555555"), fontSize=9)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], textColor=navy, fontSize=12, spaceBefore=10)
    body = ParagraphStyle("b", parent=styles["Normal"], fontSize=8.5, leading=11.5)

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=14 * mm, bottomMargin=12 * mm)
    story: list[Any] = [
        Paragraph("ROYAL SCOUT INTELLIGENCE HUB", title),
        Paragraph(f"{discipline.title()} scouting report — {meta.get('name', 'dataset')}", sub),
        Spacer(1, 6 * mm),
    ]
    prov = provenance_block(bundle)
    story.append(Paragraph("Provenance", h2))
    prov_rows = [["Field", "Value"]] + [[k, str(_fmt(v))[:160]] for k, v in prov.items()]
    t = Table(prov_rows, colWidths=[52 * mm, 118 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), navy), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 7.4), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDDDDD")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F8FA")]),
    ]))
    story.append(t)
    if rows:
        story.append(Paragraph(f"Ranked {'batters' if discipline == 'batting' else 'bowlers'}", h2))
        if discipline == "batting":
            cols = [("rank", "Rank"), ("player", "Player"), ("teams", "Team"), ("runs", "Runs"),
                    ("average", "Avg"), ("strike_rate", "SR"), ("pressure_score", "Pressure"),
                    ("grade", "Grade"), ("rabi", "Index")]
        else:
            cols = [("rank", "Rank"), ("player", "Player"), ("teams", "Team"), ("wickets", "Wkts"),
                    ("economy", "Econ"), ("bowling_strike_rate", "SR"), ("pressure_score", "Pressure"),
                    ("grade", "Grade"), ("rabi_bowl", "Index")]
        data = [[label for _, label in cols]] + [[str(_fmt(r.get(k)))[:26] for k, _ in cols] for r in rows[:30]]
        tt = Table(data, repeatRows=1)
        tt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), navy), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 7.2),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDDDDD")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F8FA")]),
        ]))
        story.append(tt)
    story.append(Paragraph("Interpretation & limitations", h2))
    for lim in prov.get("data_limitations", []) or ["No limitations were recorded for this dataset."]:
        story.append(Paragraph(f"• {lim}", body))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(
        "Scores are population-relative, shrunk toward the population baseline on limited exposure and "
        "coverage-weighted: components that the data cannot support are excluded and the coverage is "
        "reported beside every score. A player's rank is only comparable within the stated scope.", body))
    doc.build(story)
    return path


def export_workbook(bundle: dict[str, Any], out_dir: Path) -> Path:
    lb = bundle.get("leaderboards", {})
    sheets: dict[str, tuple[list[tuple[str, str]], list[dict[str, Any]]]] = {
        "Top 30 Batters": (BAT_COLUMNS, lb.get("global", {}).get("batters", []) or []),
        "Top 30 Bowlers": (BOWL_COLUMNS, lb.get("global", {}).get("bowlers", []) or []),
        "All Batting Metrics": (_all_bat_cols(), _flatten(bundle.get("batting", {}).get("players", {}))),
        "All Bowling Metrics": (_all_bowl_cols(), _flatten(bundle.get("bowling", {}).get("players", {}))),
        "Data Audit": ([("file", "File"), ("worksheet", "Worksheet"), ("column", "Column"),
                        ("canonical_field", "Canonical field"), ("total_records", "Total"),
                        ("missing", "Missing"), ("invalid", "Invalid"), ("status", "Status")],
                       bundle.get("quality", {}).get("columns", []) or []),
        "Methodology": ([("field", "Field"), ("value", "Value")], _methodology_rows(bundle)),
    }
    pressure = bundle.get("pressure_rankings")
    if pressure:
        cols = [(key, label) for key, label in (
            ("rank", "Rank"), ("player_id", "Player ID"), ("player_name", "Player"),
            ("pri", "SupeRR PRI"), ("p_balls", "Pressure balls"),
            ("pressure_matches", "Pressure matches"), ("pressure_innings", "Pressure innings"),
            ("p_sr", "Pressure strike rate"), ("p_econ", "Pressure economy"),
            ("rank_median", "Bootstrap median rank"), ("rank_p05", "Bootstrap rank p05"),
            ("rank_p95", "Bootstrap rank p95"), ("p_top10", "Bootstrap top-10 probability"),
            ("ipl_rank", "IPL rank"), ("t20i_rank", "T20I rank"),
            ("median_rank_across_methods", "Median rank across methods"),
            ("methods_with_top10", "Methods with top-10 rank"), ("methods_available", "Methods available"),
            ("seasons_above_baseline", "Seasons above baseline"), ("seasons_evaluated", "Seasons evaluated"),
            ("confirmed", "Robustness gate confirmed"),
        )]
        final = pressure.get("final", {})
        sheets["Pressure Top 10 Batters"] = (cols, (final.get("batters", []) or [])[:10])
        sheets["Pressure Top 10 Bowlers"] = (cols, (final.get("bowlers", []) or [])[:10])
        facts = pressure.get("facts", {})
        sheets["Pressure Methodology"] = ([("field", "Field"), ("value", "Value")], [
            {"field": "ranking_method", "value": "SupeRR Pressure Reliability Index (PRI)"},
            {"field": "primary_competitions", "value": ", ".join(facts.get("primary_competitions", ["IPL", "T20I"]))},
            {"field": "eligibility", "value": facts.get("eligibility", {})},
            {"field": "bootstrap_resamples", "value": facts.get("bootstrap_resamples")},
            {"field": "selection_gates", "value": "median rank <=15 across available alternatives; pressure evidence in >=2 seasons"},
            {"field": "other_t20", "value": "sensitivity only; excluded from the primary pressure ranking"},
            {"field": "super_overs", "value": "excluded from ratings"},
            {"field": "dataset_id", "value": bundle.get("meta", {}).get("dataset_id")},
            {"field": "config_fingerprint", "value": bundle.get("meta", {}).get("config_fingerprint")},
        ])
    return write_excel(out_dir / "royal_scout_export.xlsx", sheets, provenance_block(bundle))


def _all_bat_cols() -> list[tuple[str, str]]:
    keys = ["player", "teams", "primary_role", "innings", "runs", "balls_faced", "average", "strike_rate",
            "fours", "sixes", "boundary_pct", "dot_pct", "not_outs", "dismissals", "highest_score",
            "scores_30", "scores_50", "scores_100", "ducks", "consistency", "performance_score",
            "reliability", "pressure_score", "role_adjusted_score", "confidence_score", "grade",
            "rabi", "score_coverage", "exposure_balls"]
    return [(k, k.replace("_", " ").title()) for k in keys]


def _all_bowl_cols() -> list[tuple[str, str]]:
    keys = ["player", "teams", "primary_role", "innings", "overs", "legal_balls", "runs_conceded",
            "wickets", "average", "economy", "bowling_strike_rate", "dot_pct", "bowler_type",
            "wickets_per_innings", "economy_containment_score", "wicket_taking_score", "consistency",
            "pressure_score", "confidence_score", "grade", "rabi_bowl", "score_coverage", "exposure_balls"]
    return [(k, k.replace("_", " ").title()) for k in keys]


def _flatten(players: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return list(players.values())


def _methodology_rows(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    cfg = bundle.get("meta", {}).get("config", {})
    rows = [{"field": "model_version", "value": bundle.get("meta", {}).get("model_version")}]
    for section in ("stats", "eligibility", "batting_weights", "bowling_weights", "pressure_weights",
                    "scenarios"):
        for k, v in (cfg.get(section) or {}).items():
            rows.append({"field": f"{section}.{k}", "value": v})
    for cap, val in (bundle.get("schema", {}).get("capabilities") or {}).items():
        rows.append({"field": f"capability.{cap}", "value": val})
    return rows
