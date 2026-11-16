import type { PlayerRow, ScopePayload } from "./types";

export type SortDirection = "asc" | "desc";

export interface FilterState {
  search: string;
  team: string;
  role: string;
  grade: string;
  minScore: number;
  minExposure: number;
  /** metrics where a *lower* value is better */
  lowerIsBetter: string[];
}

export const DEFAULT_FILTERS: FilterState = {
  search: "",
  team: "",
  role: "",
  grade: "",
  minScore: 0,
  minExposure: 0,
  lowerIsBetter: ["economy", "bowling_strike_rate", "average"],
};

const GRADE_ORDER: Record<string, number> = { A: 0, B: 1, C: 2, D: 3 };

export function filterRows(rows: PlayerRow[], filters: FilterState, scoreKey: "rabi" | "rabi_bowl"): PlayerRow[] {
  const search = filters.search.trim().toLowerCase();
  return rows.filter((r) => {
    if (search && !r.player.toLowerCase().includes(search)) return false;
    if (filters.team && !(r.teams ?? []).some((t) => t.toLowerCase() === filters.team.toLowerCase())) return false;
    if (filters.role && (r.primary_role ?? "") !== filters.role) return false;
    if (filters.grade && GRADE_ORDER[r.grade ?? "D"] > GRADE_ORDER[filters.grade]) return false;
    if (filters.minScore > 0 && ((r[scoreKey] as number | null) ?? -1) < filters.minScore) return false;
    if (filters.minExposure > 0 && (r.exposure_balls ?? 0) < filters.minExposure) return false;
    return true;
  });
}

export function sortRows(rows: PlayerRow[], key: string, direction: SortDirection): PlayerRow[] {
  const dir = direction === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const av = a[key as keyof PlayerRow];
    const bv = b[key as keyof PlayerRow];
    if (av === null || av === undefined) return 1;
    if (bv === null || bv === undefined) return -1;
    if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
    return String(av).localeCompare(String(bv)) * dir;
  });
}

/** Re-rank within the *filtered* view while keeping the original scope rank visible. */
export function withFilteredRanks(rows: PlayerRow[]): (PlayerRow & { filtered_rank: number })[] {
  return rows.map((r, i) => ({ ...r, filtered_rank: i + 1 }));
}

export function rankDelta(row: PlayerRow & { filtered_rank?: number }): number | null {
  if (row.filtered_rank === undefined || row.rank === undefined) return null;
  return row.rank - row.filtered_rank;
}

export function uniqueValues(rows: PlayerRow[], key: "teams" | "primary_role" | "grade"): string[] {
  const set = new Set<string>();
  for (const r of rows) {
    const v = r[key];
    if (Array.isArray(v)) v.forEach((x) => set.add(x));
    else if (v) set.add(String(v));
  }
  return [...set].sort();
}

export function scopeTeamOptions(scopes: ScopePayload[]): string[] {
  return scopes
    .filter((s) => s.scope.type === "team")
    .map((s) => String(s.scope.filter.team?.[0] ?? s.scope.label))
    .sort();
}
