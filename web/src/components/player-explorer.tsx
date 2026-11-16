"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowDown, ArrowUp, Search } from "lucide-react";
import type { PlayerRow } from "@/lib/types";
import { dec, num, titleCase } from "@/lib/format";
import { Badge, GradeBadge } from "./ui/badge";
import { DataTable, TBody, TD, TH, THead } from "./ui/table";

interface Row {
  player: string;
  teams: string[];
  role: string | null;
  roleBasis?: string | null;
  batting: PlayerRow | null;
  bowling: PlayerRow | null;
  exposure: number;
  grade?: string | null;
}

const COLS: { key: keyof Row | "bat_runs" | "bat_sr" | "bat_avg" | "bowl_wkts" | "bowl_econ" | "bat_rabi" | "bowl_rabi"; label: string; align?: "right" }[] = [
  { key: "player", label: "Player" },
  { key: "teams", label: "State Team" },
  { key: "role", label: "Role" },
  { key: "bat_runs", label: "Runs", align: "right" },
  { key: "bat_sr", label: "Bat SR", align: "right" },
  { key: "bat_avg", label: "Bat Avg", align: "right" },
  { key: "bowl_wkts", label: "Wkts", align: "right" },
  { key: "bowl_econ", label: "Econ", align: "right" },
  { key: "exposure", label: "Exposure", align: "right" },
  { key: "grade", label: "Grade" },
  { key: "bat_rabi", label: "Bat Index", align: "right" },
  { key: "bowl_rabi", label: "Bowl Index", align: "right" },
];

function valueOf(row: Row, key: string): string | number | null {
  switch (key) {
    case "bat_runs": return row.batting?.runs ?? null;
    case "bat_sr": return row.batting?.strike_rate ?? null;
    case "bat_avg": return row.batting?.average ?? null;
    case "bowl_wkts": return row.bowling?.wickets ?? null;
    case "bowl_econ": return row.bowling?.economy ?? null;
    case "bat_rabi": return row.batting?.rabi ?? null;
    case "bowl_rabi": return row.bowling?.rabi_bowl ?? null;
    case "exposure": return row.exposure;
    case "player": return row.player;
    case "teams": return row.teams.join(", ");
    case "role": return row.role;
    case "grade": return row.grade ?? null;
    default: return null;
  }
}

export function PlayerExplorer({ rows }: { rows: Row[] }) {
  const [search, setSearch] = useState("");
  const [role, setRole] = useState("");
  const [grade, setGrade] = useState("");
  const [discipline, setDiscipline] = useState<"all" | "batting" | "bowling">("all");
  const [sort, setSort] = useState<{ key: string; dir: "asc" | "desc" }>({ key: "player", dir: "asc" });
  const [page, setPage] = useState(0);
  const pageSize = 25;

  const roles = useMemo(() => [...new Set(rows.map((r) => r.role).filter(Boolean))].sort() as string[], [rows]);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    const out = rows.filter((r) => {
      if (term && !r.player.toLowerCase().includes(term)) return false;
      if (role && r.role !== role) return false;
      if (grade && (r.grade ?? "D") > grade) return false;
      if (discipline === "batting" && !r.batting) false;
      if (discipline === "batting" && !r.batting) return false;
      if (discipline === "bowling" && !r.bowling) return false;
      return true;
    });
    return out.sort((a, b) => {
      const av = valueOf(a, sort.key);
      const bv = valueOf(b, sort.key);
      if (av === null || av === undefined) return 1;
      if (bv === null || bv === undefined) return -1;
      const cmp = typeof av === "number" && typeof bv === "number" ? av - bv : String(av).localeCompare(String(bv));
      return sort.dir === "asc" ? cmp : -cmp;
    });
  }, [rows, search, role, grade, discipline, sort]);

  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const current = Math.min(page, pages - 1);
  const shown = filtered.slice(current * pageSize, current * pageSize + pageSize);

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 border-b border-surface-line px-4 py-2.5">
        <label className="relative">
          <Search className="pointer-events-none absolute top-2 left-2 h-3.5 w-3.5 text-ink-faint" />
          <input className="input w-60 pl-7" placeholder="Search any player" value={search} onChange={(e) => { setSearch(e.target.value); setPage(0); }} />
        </label>
        <select className="input" value={role} onChange={(e) => { setRole(e.target.value); setPage(0); }} aria-label="Role filter">
          <option value="">All roles</option>
          {roles.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <select className="input" value={discipline} onChange={(e) => { setDiscipline(e.target.value as any); setPage(0); }} aria-label="Discipline filter">
          <option value="all">Both disciplines</option>
          <option value="batting">Has batting record</option>
          <option value="bowling">Has bowling record</option>
        </select>
        <select className="input" value={grade} onChange={(e) => { setGrade(e.target.value); setPage(0); }} aria-label="Grade filter">
          <option value="">Any confidence</option>
          <option value="A">A</option>
          <option value="B">B or better</option>
          <option value="C">C or better</option>
        </select>
        <span className="ml-auto text-2xs text-ink-faint">{filtered.length} player(s)</span>
      </div>

      <DataTable className="max-h-[64vh] overflow-y-auto">
        <THead>
          {COLS.map((c) => (
            <TH key={String(c.key)} align={c.align === "right" ? "right" : "left"}>
              <button className="inline-flex items-center gap-1 hover:text-ink" onClick={() => setSort((p) => ({ key: String(c.key), dir: p.key === String(c.key) && p.dir === "desc" ? "asc" : "desc" }))}>
                {c.label}
                {sort.key === String(c.key) ? (sort.dir === "desc" ? <ArrowDown className="h-3 w-3 text-royal-pink" /> : <ArrowUp className="h-3 w-3 text-royal-pink" />) : null}
              </button>
            </TH>
          ))}
        </THead>
        <TBody>
          {shown.map((r) => (
            <tr key={r.player} className="hover:bg-surface-muted/70">
              <TD><Link href={`/players/${encodeURIComponent(r.player)}`} className="data-link font-medium">{r.player}</Link></TD>
              <TD className="max-w-[150px] truncate text-ink-soft">{r.teams.join(", ") || "—"}</TD>
              <TD className="text-ink-soft">{r.role ? titleCase(r.role) : "—"}{r.roleBasis === "inferred_from_workload" ? <span className="ml-1 text-2xs text-ink-faint">(inferred)</span> : null}</TD>
              <TD align="right" mono>{num(r.batting?.runs ?? null)}</TD>
              <TD align="right" mono>{dec(r.batting?.strike_rate ?? null, 1)}</TD>
              <TD align="right" mono>{dec(r.batting?.average ?? null)}</TD>
              <TD align="right" mono>{num(r.bowling?.wickets ?? null)}</TD>
              <TD align="right" mono>{dec(r.bowling?.economy ?? null)}</TD>
              <TD align="right" mono>{num(r.exposure)}</TD>
              <TD><GradeBadge grade={r.grade} /></TD>
              <TD align="right" mono>{dec(r.batting?.rabi ?? null, 1)}</TD>
              <TD align="right" mono>{dec(r.bowling?.rabi_bowl ?? null, 1)}</TD>
            </tr>
          ))}
          {!shown.length ? (
            <tr><td colSpan={COLS.length} className="px-3 py-8 text-center text-xs text-ink-faint">No player matches these filters.</td></tr>
          ) : null}
        </TBody>
      </DataTable>

      <div className="flex items-center justify-between border-t border-surface-line px-4 py-2 text-2xs text-ink-faint">
        <span>Page {current + 1} of {pages}</span>
        <div className="flex gap-1.5">
          <button className="btn" onClick={() => setPage(Math.max(0, current - 1))} disabled={current === 0}>Previous</button>
          <button className="btn" onClick={() => setPage(Math.min(pages - 1, current + 1))} disabled={current >= pages - 1}>Next</button>
        </div>
      </div>
    </div>
  );
}
