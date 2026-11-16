"use client";

import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import type { QualityColumn } from "@/lib/types";
import { num, pct } from "@/lib/format";
import { Badge } from "./ui/badge";
import { DataTable, TBody, TD, TH, THead } from "./ui/table";
import { MiniBar } from "./charts/bars";

type SortKey = "file" | "missing_pct" | "invalid" | "total_records";

export function ColumnAuditTable({ columns }: { columns: QualityColumn[] }) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; dir: "asc" | "desc" }>({ key: "missing_pct", dir: "desc" });

  const rows = useMemo(() => {
    const term = search.trim().toLowerCase();
    const filtered = columns.filter((c) => {
      if (status && c.status !== status) return false;
      if (!term) return true;
      return (
        c.column.toLowerCase().includes(term) ||
        c.canonical_field.toLowerCase().includes(term) ||
        c.file.toLowerCase().includes(term) ||
        c.worksheet.toLowerCase().includes(term)
      );
    });
    return [...filtered].sort((a, b) => {
      const av = a[sort.key];
      const bv = b[sort.key];
      const cmp = typeof av === "number" && typeof bv === "number" ? av - bv : String(av).localeCompare(String(bv));
      return sort.dir === "asc" ? cmp : -cmp;
    });
  }, [columns, search, status, sort]);

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 border-b border-surface-line px-4 py-2.5">
        <label className="relative">
          <Search className="pointer-events-none absolute top-2 left-2 h-3.5 w-3.5 text-ink-faint" />
          <input className="input w-56 pl-7" placeholder="Filter columns or files" value={search} onChange={(e) => setSearch(e.target.value)} />
        </label>
        <select className="input" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
          <option value="">All statuses</option>
          <option value="ok">ok</option>
          <option value="warn">warn</option>
          <option value="fail">fail</option>
        </select>
        <span className="ml-auto text-2xs text-ink-faint">{rows.length} column(s)</span>
      </div>
      <DataTable className="max-h-[540px] overflow-y-auto">
        <THead>
          <TH>File</TH>
          <TH>Worksheet</TH>
          <TH>Column</TH>
          <TH>Canonical field</TH>
          <TH align="right">Total</TH>
          <TH align="right">Missing</TH>
          <TH align="right">Invalid</TH>
          <TH align="right">Duplicate</TH>
          <TH align="right">Completeness</TH>
          <TH>Status</TH>
        </THead>
        <TBody>
          {rows.map((c, i) => (
            <tr key={`${c.file}-${c.worksheet}-${c.column}-${i}`}>
              <TD className="max-w-[210px] truncate text-ink-soft">{c.file}</TD>
              <TD className="text-ink-soft">{c.worksheet}</TD>
              <TD className="font-medium">{c.column}</TD>
              <TD className="font-mono text-2xs text-ink-soft">{c.canonical_field || "—"}</TD>
              <TD align="right" mono>{num(c.total_records)}</TD>
              <TD align="right" mono>{pct(c.missing_pct ?? 0)}</TD>
              <TD align="right" mono className={c.invalid ? "text-rose-700" : ""}>{num(c.invalid)}</TD>
              <TD align="right" mono>{num(c.duplicate)}</TD>
              <TD align="right"><div className="w-24"><MiniBar value={100 - (c.missing_pct ?? 0)} /></div></TD>
              <TD>
                <Badge tone={c.status === "fail" ? "danger" : c.status === "warn" ? "warning" : "positive"}>{c.status}</Badge>
                {c.notes.length ? <span className="ml-1 text-2xs text-ink-faint" title={c.notes.join(" · ")}>i</span> : null}
              </TD>
            </tr>
          ))}
        </TBody>
      </DataTable>
    </div>
  );
}
