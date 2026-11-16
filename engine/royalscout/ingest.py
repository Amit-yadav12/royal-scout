"""Universal ingestion: format detection, safe archive extraction, table readers.

Every file that enters the system receives an explicit status and reason. Nothing
is skipped silently: if we cannot read a file, that fact is part of the report.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from .config import IngestionLimits
from .schema import MappingCandidate, detect_record_type, map_columns, normalise, pick_record_type

# ---------------------------------------------------------------------------
# Format support matrix (declared, not assumed)
# ---------------------------------------------------------------------------
TABULAR_EXT = {".csv", ".tsv", ".txt", ".psv", ".xls", ".xlsx", ".xlsm", ".xlsb", ".ods",
               ".json", ".jsonl", ".ndjson", ".xml", ".parquet", ".feather", ".arrow"}
DOC_EXT = {".pdf", ".docx"}
ARCHIVE_EXT = {".zip", ".tar", ".gz", ".tgz", ".tar.gz", ".7z"}
UNSAFE_EXT = {".exe", ".dll", ".so", ".dylib", ".bat", ".cmd", ".sh", ".ps1", ".jar", ".msi",
              ".scr", ".com", ".vbs", ".js", ".php", ".py", ".rb", ".apk", ".lnk"}
MACRO_EXT = {".xlsm", ".xltm", ".docm", ".dotm", ".pptm"}

MAX_NAME_LEN = 180


class IngestionError(Exception):
    pass


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------
def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(chunk), b""):
            h.update(blk)
    return h.hexdigest()


def sniff_is_text(sample: bytes) -> bool:
    if not sample:
        return True
    if b"\x00" in sample[:4096]:
        return False
    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        # allow windows-1252 / latin-1 text
        try:
            sample.decode("cp1252")
            non_print = sum(1 for b in sample if b < 9 or (13 < b < 32))
            return non_print / max(1, len(sample)) < 0.02
        except UnicodeDecodeError:
            return False


def detect_encoding(raw: bytes) -> tuple[str, str]:
    """Return (encoding, evidence). BOM first, then strict decodes, then cp1252."""
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", "UTF-8 BOM"
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return "utf-16", "UTF-16 BOM"
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            raw.decode(enc)
            return enc, f"decoded cleanly as {enc}"
        except UnicodeDecodeError:
            continue
    return "latin-1", "fallback"


def detect_delimiter(text: str) -> tuple[str, str]:
    sample = "\n".join([ln for ln in text.splitlines() if ln.strip()][:30])
    if not sample.strip():
        return ",", "empty sample"
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|:")
        return dialect.delimiter, "csv.Sniffer"
    except csv.Error:
        pass
    # fallback: pick the delimiter with the most consistent per-line count
    best, best_score = ",", -1.0
    for delim in [",", ";", "\t", "|"]:
        counts = [ln.count(delim) for ln in sample.splitlines()]
        if not counts or max(counts) == 0:
            continue
        mode = max(set(counts), key=counts.count)
        consistency = counts.count(mode) / len(counts)
        score = consistency * (1 if mode > 0 else 0)
        if score > best_score:
            best, best_score = delim, score
    return best, f"consistency heuristic ({best_score:.2f})"


# ---------------------------------------------------------------------------
# Raw table container
# ---------------------------------------------------------------------------
@dataclass
class RawTable:
    """A single logical table discovered inside a file."""

    source_path: str          # path inside the dataset (archive-relative)
    container: str            # "csv" | "sheet" | "json" | "xml" | "pdf-page" | "docx-table" ...
    table_name: str           # sheet name / "table 3" / "records"
    rows: list[list[Any]]
    header_row: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def columns(self) -> list[str]:
        if not self.rows:
            return []
        hdr = self.rows[self.header_row] if self.header_row < len(self.rows) else []
        cols = []
        for i, c in enumerate(hdr):
            name = str(c).strip() if c is not None else ""
            cols.append(name or f"column_{i + 1}")
        return cols

    @property
    def data_rows(self) -> list[list[Any]]:
        return self.rows[self.header_row + 1:]


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------
def _split_blocks(rows: list[list[Any]], min_blank: int = 2) -> list[list[list[Any]]]:
    """Split a sheet into blocks separated by >= min_blank blank rows."""
    blocks: list[list[list[Any]]] = []
    cur: list[list[Any]] = []
    blanks = 0
    for row in rows:
        empty = all(c is None or str(c).strip() == "" for c in row)
        if empty:
            blanks += 1
            if blanks >= min_blank and cur:
                blocks.append(cur)
                cur = []
            continue
        if blanks:
            blanks = 0
        cur.append(row)
    if cur:
        blocks.append(cur)
    return blocks


def find_header_row(rows: list[list[Any]], scan: int = 25) -> tuple[int, int]:
    """Return (header_index, alias_hits). Highest alias hit count wins."""
    best_idx, best_hits = 0, -1
    for idx, row in enumerate(rows[:scan]):
        cells = [str(c) for c in row if c is not None and str(c).strip() != ""]
        if len(cells) < 2:
            continue
        mapped = map_columns(cells)
        hits = sum(1 for m in mapped if m.field and m.confidence >= 0.72)
        # prefer rows with many non-numeric cells (headers are textual)
        numeric = sum(1 for c in cells if re.fullmatch(r"-?\d+(\.\d+)?", c.strip()))
        score = hits - numeric * 0.5
        if score > best_hits:
            best_idx, best_hits = idx, hits
    return max(0, best_idx), max(0, best_hits)


def _block_header_hits(block: list[list[Any]]) -> int:
    hdr, hits = find_header_row(block)
    return hits


def read_delimited(path: Path, rel: str, limits: IngestionLimits) -> list[RawTable]:
    raw = path.open("rb").read(limits.sniff_bytes * 8)
    enc, enc_ev = detect_encoding(raw)
    text = raw.decode(enc, errors="replace")
    if path.suffix.lower() == ".tsv":
        delim, delim_ev = "\t", "declared by extension"
    elif path.suffix.lower() == ".psv":
        delim, delim_ev = "|", "declared by extension"
    else:
        delim, delim_ev = detect_delimiter(text)
    with path.open("r", encoding=enc, errors="replace", newline="") as fh:
        reader = csv.reader(fh, delimiter=delim)
        raw_rows = [list(r) for r in reader]
    if not any(any(str(c).strip() for c in r) for r in raw_rows):
        raise IngestionError("file contains no data rows")
    # Blank rows are kept until after block splitting: they are the only signal
    # that a file contains more than one table.
    blocks = _split_blocks(raw_rows, min_blank=2)
    if len(blocks) == 1:
        single = _split_blocks(raw_rows, min_blank=1)
        if len(single) > 1 and all(_block_header_hits(b) >= 2 for b in single):
            blocks = single
    tables: list[RawTable] = []
    for bi, blk in enumerate(blocks):
        block = [r for r in blk if any(str(c).strip() for c in r)]
        if len(block) < 2:
            continue
        hdr, hits = find_header_row(block)
        name = "table" if len(blocks) == 1 else f"table {bi + 1}"
        tables.append(RawTable(
            source_path=rel, container="delimited", table_name=name,
            rows=block, header_row=hdr,
            meta={"encoding": enc, "encoding_evidence": enc_ev, "delimiter": delim,
                  "delimiter_evidence": delim_ev, "header_alias_hits": hits,
                  "header_row": hdr + 1}))
    return tables


def read_excel(path: Path, rel: str, limits: IngestionLimits) -> list[RawTable]:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True, keep_links=False)
        out: list[RawTable] = []
        for ws in wb.worksheets[: limits.max_sheets_per_workbook]:
            rows: list[list[Any]] = []
            for r in ws.iter_rows(values_only=True):
                rows.append(list(r))
                if len(rows) > limits.max_table_rows_per_file:
                    raise IngestionError(f"sheet '{ws.title}' exceeds configured row limit")
            rows = [r for r in rows if any(c is not None and str(c).strip() != "" for c in r)]
            if not rows:
                continue
            for bi, block in enumerate(_split_blocks(rows)):
                hdr, hits = find_header_row(block)
                label = ws.title if len(_split_blocks(rows)) == 1 else f"{ws.title} [block {bi + 1}]"
                out.append(RawTable(rel, "sheet", label, block, hdr,
                                    meta={"worksheet": ws.title, "header_alias_hits": hits,
                                          "header_row": hdr + 1, "macro_enabled": suffix == ".xlsm"}))
        wb.close()
        return out
    if suffix == ".xls":
        try:
            import xlrd  # type: ignore
        except ImportError as exc:
            raise IngestionError("legacy .xls requires the 'xlrd' package (declared in requirements)") from exc
        book = xlrd.open_workbook(str(path), on_demand=True)
        out = []
        for sh in book.sheets()[: limits.max_sheets_per_workbook]:
            rows = [sh.row_values(i) for i in range(sh.nrows)]
            rows = [r for r in rows if any(str(c).strip() for c in r)]
            if not rows:
                continue
            hdr, hits = find_header_row(rows)
            out.append(RawTable(rel, "sheet", sh.name, rows, hdr,
                                meta={"worksheet": sh.name, "header_alias_hits": hits, "header_row": hdr + 1}))
        return out
    if suffix == ".ods":
        try:
            from odf.opendocument import load  # type: ignore
            from odf.table import Table, TableCell, TableRow  # type: ignore
            from odf.text import P  # type: ignore
        except ImportError as exc:
            raise IngestionError("OpenDocument spreadsheets require the 'odfpy' package") from exc
        doc = load(str(path))
        out = []
        for tbl in doc.spreadsheet.getElementsByType(Table)[: limits.max_sheets_per_workbook]:
            rows = []
            for tr in tbl.getElementsByType(TableRow):
                row = []
                for tc in tr.getElementsByType(TableCell):
                    repeat = int(tc.getAttribute("numbercolumnsrepeated") or 1)
                    text = "".join(str(p) for p in tc.getElementsByType(P))
                    row.extend([text] * min(repeat, 200))
                rows.append(row)
            rows = [r for r in rows if any(str(c).strip() for c in r)]
            if not rows:
                continue
            hdr, hits = find_header_row(rows)
            out.append(RawTable(rel, "sheet", tbl.getAttribute("name") or "sheet", rows, hdr,
                                meta={"header_alias_hits": hits, "header_row": hdr + 1}))
        return out
    if suffix == ".xlsb":
        raise IngestionError("binary .xlsb is not supported by the installed readers; "
                             "convert to .xlsx or declare an xlsb reader in requirements")
    raise IngestionError(f"unhandled spreadsheet extension {suffix}")


def _rows_from_records(records: list[dict[str, Any]]) -> tuple[list[list[Any]], int]:
    cols: list[str] = []
    for rec in records:
        for k in rec:
            if k not in cols:
                cols.append(k)
    rows = [cols] + [[rec.get(c) for c in cols] for rec in records]
    return rows, 0


def read_json_like(path: Path, rel: str, limits: IngestionLimits) -> list[RawTable]:
    text = path.read_text(encoding="utf-8", errors="replace")
    suffix = path.suffix.lower()
    if suffix in {".jsonl", ".ndjson"}:
        records = []
        for i, line in enumerate(text.splitlines()):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise IngestionError(f"invalid JSON on line {i + 1}: {exc}") from exc
            if isinstance(obj, dict):
                records.append(obj)
        if not records:
            raise IngestionError("no JSON objects found")
        rows, hdr = _rows_from_records(records)
        return [RawTable(rel, "json", "records", rows, hdr, meta={"record_count": len(records)})]

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise IngestionError(f"invalid JSON: {exc}") from exc

    tables: list[RawTable] = []
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        rows, hdr = _rows_from_records(payload)
        tables.append(RawTable(rel, "json", "records", rows, hdr, meta={"record_count": len(payload)}))
    elif isinstance(payload, dict):
        # find the largest list-of-dicts value; keep siblings as context meta
        best_key, best_val = None, []
        for k, v in payload.items():
            if isinstance(v, list) and v and isinstance(v[0], dict) and len(v) > len(best_val):
                best_key, best_val = k, v
            if isinstance(v, dict):
                for k2, v2 in v.items():
                    if isinstance(v2, list) and v2 and isinstance(v2[0], dict) and len(v2) > len(best_val):
                        best_key, best_val = f"{k}.{k2}", v2
        if best_key:
            rows, hdr = _rows_from_records(best_val)
            tables.append(RawTable(rel, "json", best_key, rows, hdr,
                                   meta={"record_count": len(best_val), "source_key": best_key}))
        else:
            rows, hdr = _rows_from_records([payload])
            tables.append(RawTable(rel, "json", "object", rows, hdr, meta={"record_count": 1}))
    else:
        raise IngestionError("JSON payload is neither a record list nor an object")
    return tables


def read_xml(path: Path, rel: str) -> list[RawTable]:
    import xml.etree.ElementTree as ET

    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise IngestionError(f"malformed XML: {exc}") from exc
    # Group children by tag; the tag with the most children-of-children becomes the table.
    groups: dict[str, list[Any]] = {}
    for child in root.iter():
        groups.setdefault(child.tag, []).append(child)
    best_tag, best_nodes = None, []
    for tag, nodes in groups.items():
        with_children = [n for n in nodes if len(n) > 0]
        if len(with_children) > len(best_nodes):
            best_tag, best_nodes = tag, with_children
    if not best_nodes:
        raise IngestionError("no repeating record elements found in XML")
    cols: list[str] = []
    for n in best_nodes:
        for c in n:
            if c.tag not in cols:
                cols.append(c.tag)
    rows = [cols]
    for n in best_nodes:
        vals = {c.tag: (c.text.strip() if c.text else None) for c in n}
        for attr, v in n.attrib.items():
            if attr not in cols:
                cols.append(attr)
                rows[0] = cols
        rows.append([vals.get(c, n.attrib.get(c)) for c in cols])
    return [RawTable(rel, "xml", f"<{best_tag}>", rows, 0, meta={"record_count": len(best_nodes)})]


def read_parquet(path: Path, rel: str) -> list[RawTable]:
    import pyarrow.parquet as pq
    import pyarrow.feather as feather

    if path.suffix.lower() == ".feather":
        tbl = feather.read_table(path)
    else:
        tbl = pq.read_table(path)
    data = tbl.to_pylist()
    if not data:
        raise IngestionError("parquet/feather file has no rows")
    rows, hdr = _rows_from_records(data)
    return [RawTable(rel, "parquet", "table", rows, hdr, meta={"record_count": len(data)})]


def read_pdf(path: Path, rel: str) -> list[RawTable]:
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        raise IngestionError(
            "PDF table extraction requires 'pdfplumber', which is not installed in this "
            "worker image. Install it (see WORKER_SETUP.md) to enable PDF ingestion. "
            "OCR is not enabled in this deployment.")
    out: list[RawTable] = []
    with pdfplumber.open(str(path)) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            for tno, table in enumerate(page.extract_tables() or [], start=1):
                rows = [[("" if c is None else c) for c in row] for row in table]
                rows = [r for r in rows if any(str(c).strip() for c in r)]
                if len(rows) < 2:
                    continue
                hdr, hits = find_header_row(rows)
                out.append(RawTable(rel, "pdf-page", f"page {pno} table {tno}", rows, hdr,
                                    meta={"page": pno, "table": tno, "header_alias_hits": hits,
                                          "extraction_confidence": 0.9}))
    if not out:
        raise IngestionError("no extractable tables found in PDF (page may be scanned; "
                             "OCR is an optional capability and is not enabled)")
    return out


def read_docx(path: Path, rel: str) -> list[RawTable]:
    import xml.etree.ElementTree as ET

    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(path) as zf:
        if "word/document.xml" not in zf.namelist():
            raise IngestionError("not a valid .docx package (missing word/document.xml)")
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    out: list[RawTable] = []
    for idx, tbl in enumerate(root.iter(f"{ns}tbl"), start=1):
        rows: list[list[Any]] = []
        for tr in tbl.iter(f"{ns}tr"):
            row = []
            for tc in tr.iter(f"{ns}tc"):
                txt = "".join(t.text or "" for t in tc.iter(f"{ns}t"))
                row.append(txt)
            rows.append(row)
        rows = [r for r in rows if any(str(c).strip() for c in r)]
        if len(rows) < 2:
            continue
        hdr, hits = find_header_row(rows)
        out.append(RawTable(rel, "docx-table", f"table {idx}", rows, hdr,
                            meta={"header_alias_hits": hits, "extraction_confidence": 0.85}))
    if not out:
        raise IngestionError("no tables found in .docx document")
    return out


READERS: dict[str, Callable[..., list[RawTable]]] = {
    ".csv": read_delimited, ".tsv": read_delimited, ".txt": read_delimited, ".psv": read_delimited,
    ".xlsx": read_excel, ".xlsm": read_excel, ".xls": read_excel, ".ods": read_excel,
    ".json": read_json_like, ".jsonl": read_json_like, ".ndjson": read_json_like,
    ".xml": read_xml,
    ".parquet": read_parquet, ".feather": read_parquet, ".arrow": read_parquet,
    ".pdf": read_pdf, ".docx": read_docx,
}


def read_file(path: Path, rel: str, limits: IngestionLimits) -> list[RawTable]:
    suffix = path.suffix.lower()
    if suffix in UNSAFE_EXT:
        raise IngestionError(f"blocked file type '{suffix}' (executable/script content is never processed)")
    fn = READERS.get(suffix)
    if fn is None:
        raise IngestionError(f"unsupported file type '{suffix}'")
    return fn(path, rel, limits) if fn in (read_delimited, read_excel, read_json_like) else fn(path, rel)


# ---------------------------------------------------------------------------
# Safe archive handling
# ---------------------------------------------------------------------------
@dataclass
class ArchiveEntry:
    name: str
    size: int
    compressed_size: int
    is_dir: bool = False
    encrypted: bool = False
    reason: str | None = None
    duplicate_of: str | None = None
    nested_depth: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "size_bytes": self.size, "compressed_size": self.compressed_size,
            "is_dir": self.is_dir, "encrypted": self.encrypted, "reason": self.reason,
            "duplicate_of": self.duplicate_of, "nested_depth": self.nested_depth,
            "supported": self.reason is None and not self.is_dir,
        }


def _is_unsafe_name(name: str) -> str | None:
    if not name or name.strip() in {"", ".", ".."}:
        return "empty entry name"
    if len(name) > MAX_NAME_LEN * 4:
        return "entry path too long"
    n = name.replace("\\", "/")
    if n.startswith("/") or re.match(r"^[a-zA-Z]:", n):
        return "absolute path in archive"
    parts = n.split("/")
    if any(p == ".." for p in parts):
        return "path traversal ('..') in archive"
    if n.count("/") > 12:
        return "excessive directory depth"
    base = parts[-1]
    if base.lower() in {".ds_store", "thumbs.db"}:
        return "system metadata file"
    if base.startswith("__MACOSX/") or "/__MACOSX/" in f"/{n}":
        return "macOS resource fork"
    return None


def inspect_archive(path: Path, limits: IngestionLimits) -> list[ArchiveEntry]:
    """Inspect contents WITHOUT extracting. Never raises for per-entry problems."""
    entries: list[ArchiveEntry] = []
    suffix = path.suffix.lower()
    if suffix == ".7z":
        raise IngestionError("7z archives require the 'py7zr' package, which is not installed; "
                             "upload a zip or tar archive instead")
    if suffix in {".zip"} or zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
            if len(infos) > limits.max_archive_entries:
                raise IngestionError(
                    f"archive contains {len(infos)} entries which exceeds the configured limit "
                    f"of {limits.max_archive_entries}")
            total_uncompressed = 0
            seen: dict[str, str] = {}
            for info in infos:
                is_dir = info.is_dir()
                name = info.filename
                entry = ArchiveEntry(name=name, size=info.file_size,
                                     compressed_size=info.compress_size, is_dir=is_dir)
                entry.encrypted = bool(info.flag_bits & 0x1)
                if entry.encrypted:
                    entry.reason = "encrypted archive entry (cannot read without password)"
                unsafe = _is_unsafe_name(name)
                if unsafe and not entry.reason:
                    entry.reason = unsafe
                if not is_dir and not entry.reason:
                    ext = Path(name).suffix.lower()
                    if ext in UNSAFE_EXT:
                        entry.reason = f"blocked file type '{ext}'"
                    elif ext in MACRO_EXT:
                        entry.reason = f"macro-enabled document '{ext}' is rejected (macros are never executed)"
                    elif ext not in TABULAR_EXT | DOC_EXT | ARCHIVE_EXT:
                        entry.reason = f"unsupported file type '{ext or 'none'}'"
                    if info.compress_size > 0:
                        ratio = info.file_size / info.compress_size
                        if ratio > limits.max_compression_ratio:
                            entry.reason = (f"compression ratio {ratio:.0f}:1 exceeds limit "
                                            f"{limits.max_compression_ratio:.0f}:1 (zip-bomb guard)")
                    total_uncompressed += info.file_size
                    if info.file_size > limits.max_single_file_bytes:
                        entry.reason = f"entry exceeds single-file limit ({info.file_size} bytes)"
                if name in seen and not entry.reason:
                    entry.duplicate_of = seen[name]
                    entry.reason = f"duplicate entry path (first seen at {seen[name]})"
                seen.setdefault(name, name)
                entries.append(entry)
            if total_uncompressed > limits.max_total_extracted_bytes:
                raise IngestionError(
                    f"archive expands to {total_uncompressed} bytes which exceeds the configured "
                    f"total-extraction limit of {limits.max_total_extracted_bytes} bytes")
        return entries
    if tarfile.is_tarfile(path):
        with tarfile.open(path) as tf:
            members = tf.getmembers()
            if len(members) > limits.max_archive_entries:
                raise IngestionError("tar archive entry count exceeds configured limit")
            total = 0
            for m in members:
                entry = ArchiveEntry(name=m.name, size=m.size, compressed_size=m.size, is_dir=m.isdir())
                if m.issym() or m.islnk():
                    entry.reason = "symbolic/hard link entries are rejected"
                elif not m.isfile():
                    entry.is_dir = True
                unsafe = _is_unsafe_name(m.name)
                if unsafe and not entry.reason:
                    entry.reason = unsafe
                if m.isfile() and not entry.reason:
                    ext = Path(m.name).suffix.lower()
                    if ext in UNSAFE_EXT:
                        entry.reason = f"blocked file type '{ext}'"
                    elif ext not in TABULAR_EXT | DOC_EXT | ARCHIVE_EXT:
                        entry.reason = f"unsupported file type '{ext or 'none'}'"
                    total += m.size
                entries.append(entry)
            if total > limits.max_total_extracted_bytes:
                raise IngestionError("tar archive exceeds configured total-extraction limit")
        return entries
    raise IngestionError("file is not a recognised archive")


def safe_extract(path: Path, dest: Path, limits: IngestionLimits,
                 depth: int = 0) -> tuple[list[ArchiveEntry], list[Path]]:
    """Extract supported entries only, after validating every entry name."""
    dest.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    entries = inspect_archive(path, limits)
    dest_root = dest.resolve()
    if zipfile.is_zipfile(path) and path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            # `inspect_archive` emits one entry per ZipInfo in infolist order
            for info, entry in zip(zf.infolist(), entries):
                if entry.reason or entry.is_dir:
                    continue
                target = (dest / entry.name).resolve()
                if not str(target).startswith(str(dest_root) + os.sep) and target != dest_root:
                    entry.reason = "resolved path escapes extraction directory"
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out, length=1 << 20)
                written.append(target)
    elif tarfile.is_tarfile(path):
        with tarfile.open(path) as tf:
            by_name = {m.name: m for m in tf.getmembers()}
            for entry in entries:
                if entry.reason or entry.is_dir:
                    continue
                m = by_name.get(entry.name)
                if m is None or not m.isfile():
                    continue
                target = (dest / entry.name).resolve()
                if not str(target).startswith(str(dest_root) + os.sep) and target != dest_root:
                    entry.reason = "resolved path escapes extraction directory"
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                src = tf.extractfile(m)
                if src is None:
                    entry.reason = "archive member could not be read"
                    continue
                with src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out, length=1 << 20)
                written.append(target)
    return entries, written


# ---------------------------------------------------------------------------
# Table profiling (schema discovery)
# ---------------------------------------------------------------------------
@dataclass
class TableProfile:
    source_path: str
    container: str
    table_name: str
    row_count: int
    column_count: int
    columns: list[str]
    mapping: list[MappingCandidate]
    record_type: str
    record_type_scores: list[dict[str, Any]]
    header_row: int
    needs_review: bool
    notes: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path, "container": self.container,
            "table_name": self.table_name, "row_count": self.row_count,
            "column_count": self.column_count, "columns": self.columns,
            "record_type": self.record_type,
            "record_type_scores": self.record_type_scores,
            "header_row": self.header_row + 1,
            "needs_review": self.needs_review,
            "notes": self.notes,
            "meta": self.meta,
            "mapping": [m.to_dict() for m in self.mapping],
        }

    @property
    def field_map(self) -> dict[str, str]:
        return {m.field: m.column for m in self.mapping if m.field and not m.needs_review or
                (m.field and m.confidence >= 0.9)}


def profile_table(t: RawTable) -> TableProfile:
    cols = t.columns
    samples: dict[str, list[Any]] = {}
    data = t.data_rows
    for i, c in enumerate(cols):
        vals = [r[i] for r in data[:50] if i < len(r) and r[i] not in (None, "")]
        samples[c] = vals[:5]
    mapped = map_columns(cols, samples)
    from .schema import apply_contextual_rules
    mapped, contextual_adjustments = apply_contextual_rules(mapped)
    # detect duplicated player-ish columns (batter + bowler in ball-by-ball)
    multi: set[str] = set()
    seen: dict[str, int] = {}
    for m in mapped:
        if m.field:
            seen[m.field] = seen.get(m.field, 0) + 1
    for f, n in seen.items():
        if n > 1:
            multi.add(f)
    hyps = detect_record_type(mapped, multi)
    rt = pick_record_type(hyps)
    notes: list[str] = []
    if any(m.ambiguous_with for m in mapped):
        notes.append("some columns match multiple canonical fields within the ambiguity margin")
    if rt == "unknown":
        notes.append("no cricket record type could be identified with confidence; manual mapping required")
    if not any(m.field == "player_name" or m.field == "batter_name" or m.field == "bowler_name" for m in mapped):
        notes.append("no player-identifying column detected")
    needs_review = rt == "unknown" or any(m.needs_review and m.confidence < 0.9 for m in mapped)
    return TableProfile(
        source_path=t.source_path, container=t.container, table_name=t.table_name,
        row_count=len(data), column_count=len(cols), columns=cols, mapping=mapped,
        record_type=rt, record_type_scores=[h.to_dict() for h in hyps],
        header_row=t.header_row, needs_review=needs_review, notes=notes,
        meta={**t.meta, "contextual_adjustments": contextual_adjustments})


def iter_source_files(root: Path) -> Iterator[Path]:
    for p in sorted(root.rglob("*")):
        if p.is_file():
            yield p
