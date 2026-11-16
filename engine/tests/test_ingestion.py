"""Ingestion tests: formats, encodings, headers, archives and hostile content."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from royalscout.config import DEFAULT_CONFIG
from royalscout.ingest import (IngestionError, detect_delimiter, detect_encoding, find_header_row,
                                 inspect_archive, profile_table, read_file, safe_extract)


def test_csv_delimiter_and_encoding(tmp_path: Path) -> None:
    p = tmp_path / "semi.csv"
    p.write_text("Player;Runs;Balls\nFixture A;10;12\nFixture B;20;15\n", encoding="cp1252")
    enc, _ = detect_encoding(p.read_bytes())
    assert enc in {"cp1252", "latin-1", "utf-8"}
    tables = read_file(p, "semi.csv", DEFAULT_CONFIG.limits)
    assert len(tables) == 1
    assert tables[0].columns == ["Player", "Runs", "Balls"]
    assert len(tables[0].data_rows) == 2


def test_tab_delimited(tmp_path: Path) -> None:
    p = tmp_path / "t.tsv"
    p.write_text("Player\tRuns\tBalls\nFixture A\t10\t12\n", encoding="utf-8")
    t = read_file(p, "t.tsv", DEFAULT_CONFIG.limits)[0]
    assert t.columns[:3] == ["Player", "Runs", "Balls"]


def test_header_row_detection_with_preamble(tmp_path: Path) -> None:
    p = tmp_path / "preamble.csv"
    p.write_text("Rajasthan Royals scouting export\nGenerated 2026\n\n"
                 "Player,Runs,Balls,4s,6s\nFixture A,10,12,1,0\n", encoding="utf-8")
    t = read_file(p, "preamble.csv", DEFAULT_CONFIG.limits)[0]
    assert t.rows[t.header_row][0] == "Player", "header row must be located below the preamble"
    assert t.columns[0] == "Player"
    assert len(t.data_rows) == 1


def test_multiple_tables_in_one_csv(tmp_path: Path) -> None:
    p = tmp_path / "two.csv"
    p.write_text("Player,Runs,Balls\nFixture A,10,12\n\n\nBowler,Overs,Wickets\n"
                 "Fixture B,4,2\n", encoding="utf-8")
    tables = read_file(p, "two.csv", DEFAULT_CONFIG.limits)
    assert len(tables) == 2


def test_excel_sheets_from_fixture() -> None:
    from tests.conftest import FIXTURES
    path = FIXTURES / "messy_workbook.xlsx"
    tables = read_file(path, "messy_workbook.xlsx", DEFAULT_CONFIG.limits)
    names = {t.table_name for t in tables}
    assert {"Batting Summary", "Bowling Summary", "Budget"} <= names
    bowling = next(t for t in tables if t.table_name == "Bowling Summary")
    # a leading blank row must not defeat header detection
    assert bowling.columns[0] == "Bowler"
    profiles = {p.table_name: p for p in (profile_table(t) for t in tables)}
    assert profiles["Bowling Summary"].record_type.startswith("bowling")
    # a "Runs" column in a bowling table must never become batting runs
    fields = {m.field for m in profiles["Bowling Summary"].mapping}
    assert "runs_conceded" in fields
    assert "runs" not in fields


def test_json_and_jsonl(tmp_path: Path) -> None:
    p = tmp_path / "records.json"
    p.write_text('{"aggregates": [{"player": "Fixture A", "runs": 11, "balls": 9}]}', encoding="utf-8")
    t = read_file(p, "records.json", DEFAULT_CONFIG.limits)[0]
    assert t.columns[:3] == ["player", "runs", "balls"]
    assert t.data_rows[0][0] == "Fixture A"

    jl = tmp_path / "records.jsonl"
    jl.write_text('{"player": "Fixture A", "runs": 5}\n{"player": "Fixture B", "runs": 7}\n',
                  encoding="utf-8")
    t2 = read_file(jl, "records.jsonl", DEFAULT_CONFIG.limits)[0]
    assert len(t2.data_rows) == 2


def test_parquet_roundtrip(tmp_path: Path) -> None:
    import polars as pl
    p = tmp_path / "agg.parquet"
    pl.DataFrame({"player": ["Fixture A"], "runs": [42], "balls": [30]}).write_parquet(p)
    t = read_file(p, "agg.parquet", DEFAULT_CONFIG.limits)[0]
    assert t.data_rows[0][1] == 42


def test_empty_file_is_reported_not_silently_skipped(tmp_path: Path) -> None:
    p = tmp_path / "empty.csv"
    p.write_text("", encoding="utf-8")
    with pytest.raises(IngestionError):
        read_file(p, "empty.csv", DEFAULT_CONFIG.limits)


def test_unsupported_extension(tmp_path: Path) -> None:
    p = tmp_path / "data.bin"
    p.write_bytes(b"\x00\x01\x02")
    with pytest.raises(IngestionError, match="unsupported"):
        read_file(p, "data.bin", DEFAULT_CONFIG.limits)


def test_executable_is_blocked(tmp_path: Path) -> None:
    p = tmp_path / "malware.exe"
    p.write_bytes(b"MZ")
    with pytest.raises(IngestionError, match="blocked"):
        read_file(p, "malware.exe", DEFAULT_CONFIG.limits)


def test_zip_inspection_flags_hostile_entries(archive_zip: Path) -> None:
    entries = inspect_archive(archive_zip, DEFAULT_CONFIG.limits)
    by_name = {e.name: e for e in entries}
    assert by_name["../escape.csv"].reason and "traversal" in by_name["../escape.csv"].reason
    assert by_name["/absolute.csv"].reason and "absolute" in by_name["/absolute.csv"].reason
    assert by_name["notes.exe"].reason and "blocked" in by_name["notes.exe"].reason
    assert by_name["macro.xlsm"].reason and "macro" in by_name["macro.xlsm"].reason
    assert by_name["batting/archive_batting.csv"].reason is None
    assert by_name["nested/inner.zip"].reason is None  # nested archives are supported


def test_safe_extract_never_escapes(tmp_path: Path) -> None:
    entries, written = safe_extract(Path(__file__).parent / "fixtures" / "generated" / "dataset_bundle.zip",
                                    tmp_path / "out", DEFAULT_CONFIG.limits)
    root = (tmp_path / "out").resolve()
    for f in written:
        assert str(f.resolve()).startswith(str(root))
    assert not (tmp_path / "escape.csv").exists()
    assert not list(tmp_path.glob("**/notes.exe"))
    assert any(f.name == "archive_batting.csv" for f in written)


def test_zip_bomb_ratio_guard(tmp_path: Path) -> None:
    p = tmp_path / "bomb.zip"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("zeros.csv", b"0" * (4 * 1024 * 1024))
    entries = inspect_archive(p, DEFAULT_CONFIG.limits)
    assert entries[0].reason and "compression ratio" in entries[0].reason


def test_archive_entry_count_limit(tmp_path: Path) -> None:
    from dataclasses import replace
    limits = replace(DEFAULT_CONFIG.limits, max_archive_entries=3)
    p = tmp_path / "many.zip"
    with zipfile.ZipFile(p, "w") as zf:
        for i in range(10):
            zf.writestr(f"f{i}.csv", "Player,Runs\nFixture A,1\n")
    with pytest.raises(IngestionError, match="entry count|exceeds"):
        inspect_archive(p, limits)


def test_encrypted_zip_is_flagged_not_silently_ignored(tmp_path: Path) -> None:
    # Python cannot write encrypted zips; simulate by patching the flag bits.
    p = tmp_path / "enc.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("a.csv", "Player,Runs\nFixture A,1\n")
    data = bytearray(p.read_bytes())
    # zipfile reads flag_bits from the *central directory* record: PK\x01\x02 + 8
    idx = data.rfind(b"PK\x01\x02")
    assert idx > 0
    data[idx + 8] |= 0x01
    p.write_bytes(bytes(data))
    entries = inspect_archive(p, DEFAULT_CONFIG.limits)
    assert entries[0].encrypted is True
    assert "encrypted" in (entries[0].reason or "")


def test_path_traversal_names_rejected() -> None:
    from royalscout.ingest import _is_unsafe_name
    assert _is_unsafe_name("../x.csv")
    assert _is_unsafe_name("/etc/passwd")
    assert _is_unsafe_name("C:/windows/x.csv")
    assert _is_unsafe_name("a/" * 14 + "x.csv")
    assert _is_unsafe_name(".DS_Store")
    assert _is_unsafe_name("ok/data.csv") is None


def test_delimiter_detection() -> None:
    assert detect_delimiter("a,b,c\n1,2,3\n")[0] == ","
    assert detect_delimiter("a;b;c\n1;2;3\n")[0] == ";"
    assert detect_delimiter("a\tb\tc\n1\t2\t3\n")[0] == "\t"


def test_header_detection_scores() -> None:
    rows = [["ignore me"], ["Player", "Runs", "Balls"], ["A", "10", "12"]]
    idx, hits = find_header_row(rows)
    assert idx == 1 and hits >= 2
