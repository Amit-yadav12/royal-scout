"use client";

import { Fragment, useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Download, RotateCcw, Search, SlidersHorizontal } from "lucide-react";
import type { PlayerRow } from "@/lib/types";
import { DEFAULT_FILTERS, filterRows, sortRows, uniqueValues, withFilteredRanks } from "@/lib/filters";
import { dec, gradeTone, num, scoreTone, titleCase } from "@/lib/format";
import { downloadCsv } from "./csv";
import { PlayerLink, teamLabel } from "./player-link";
import { GradeBadge } from "./ui/badge";

type Discipline = "batting" | "bowling";

const BAT_COLUMNS = [
  { key: "filtered_rank", label: "#", align: "right" as const, sortable: false },
  { key: "player", label: "Player", align: "left" as const, sortable: true, wide: true },
  { key: "teams", label: "State Team", align: "left" as const, sortable: false },
  { key: "primary_role", label: "Role", align: "left" as const, sortable: false },
  { key: "matches", label: "Mat", align: "right" as const, sortable: true },
  { key: "innings", label: "Inns", align: "right" as const, sortable: true },
  { key: "runs", label: "Runs", align: "right" as const, sortable: true },
  { key: "balls_faced", label: "Balls", align: "right" as const, sortable: true },
  { key: "average", label: "Avg", align: "right" as const, sortable: true },
  { key: "strike_rate", label: "SR", align: "right" as const, sortable: true },
  { key: "fours", label: "4s", align: "right" as const, sortable: true },
  { key: "sixes", label: "6s", align: "right" as const, sortable: true },
  { key: "consistency", label: "Consist.", align: "right" as const, sortable: true },
  { key: "pressure_score", label: "Pressure", align: "right" as const, sortable: true },
  { key: "grade", label: "Conf.", align: "center" as const, sortable: true },
  { key: "score_coverage", label: "Coverage", align: "right" as const, sortable: true },
  { key: "rabi", label: "Final Score", align: "right" as const, sortable: true, emphasis: true },
];

const BOWL_COLUMNS = [
  { key: "filtered_rank", label: "#", align: "right" as const, sortable: false },
  { key: "player", label: "Player", align: "left" as const, sortable: true, wide: true },
  { key: "teams", label: "State Team", align: "left" as const, sortable: false },
  { key: "primary_role", label: "Role", align: "left" as const, sortable: false },
  { key: "bowler_type", label: "Type", align: "left" as const, sortable: true },
  { key: "innings", label: "Inns", align: "right" as const, sortable: true },
  { key: "overs", label: "Overs", align: "right" as const, sortable: false },
  { key: "wickets", label: "Wkts", align: "right" as const, sortable: true },
  { key: "runs_conceded", label: "Runs", align: "right" as const, sortable: true },
  { key: "average", label: "Avg", align: "right" as const, sortable: true },
  { key: "economy", label: "Econ", align: "right" as const, sortable: true },
  { key: "bowling_strike_rate", label: "SR", align: "right" as const, sortable: true },
  { key: "dot_pct", label: "Dot %", align: "right" as const, sortable: true },
  { key: "consistency", label: "Consist.", align: "right" as const, sortable: true },
  { key: "pressure_score", label: "Pressure", align: "right" as const, sortable: true },
  { key: "grade", label: "Conf.", align: "center" as const, sortable: true },
  { key: "score_coverage", label: "Coverage", align: "right" as const, sortable: true },
  { key: "rabi_bowl", label: "Final Score", align: "right" as const, sortable: true, emphasis: true },
];

export function Leaderboard({
  rows,
  discipline,
  scopeLabel,
  provenance,
  defaultSort,
  pageSize = 30,
  weights,
}: {
  rows: PlayerRow[];
  discipline: Discipline;
  scopeLabel: string;
  provenance: Record<string, unknown>;
  defaultSort: string;
  pageSize?: number;
  /** nominal composite weights in force for this discipline (from the model config) */
  weights?: Record<string, number>;
}) {
  const scoreKey = discipline === "batting" ? "rabi" : "rabi_bowl";
  const columns = discipline === "batting" ? BAT_COLUMNS : BOWL_COLUMNS;
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [sort, setSort] = useState<{ key: string; dir: "asc" | "desc" }>({
    key: defaultSort,
    dir: "desc",
  });
  const [expanded, setExpanded] = useState<string | null>(null);

  const teams = useMemo(() => uniqueValues(rows, "teams"), [rows]);
  const roles = useMemo(() => uniqueValues(rows, "primary_role"), [rows]);

  const filtered = useMemo(() => {
    const f = filterRows(rows, filters, scoreKey);
    const sorted = sortRows(f, sort.key, sort.dir);
    return withFilteredRanks(sorted);
  }, [rows, filters, sort, scoreKey]);

  const shown = filtered.slice(0, pageSize);
  const activeFilterCount =
    (filters.search ? 1 : 0) +
    (filters.team ? 1 : 0) +
    (filters.role ? 1 : 0) +
    (filters.grade ? 1 : 0) +
    (filters.minScore ? 1 : 0) +
    (filters.minExposure ? 1 : 0);

  function toggleSort(key: string) {
    setSort((prev) =>
      prev.key === key ? { key, dir: prev.dir === "desc" ? "asc" : "desc" } : { key, dir: "desc" },
    );
  }

  return (
    <div>
      <div className="flex flex-wrap items-end gap-2 border-b border-surface-line px-4 py-3">
        <label className="relative">
          <Search className="pointer-events-none absolute top-2 left-2 h-3.5 w-3.5 text-ink-faint" />
          <input
            className="input w-52 pl-7"
            placeholder="Search player"
            value={filters.search}
            onChange={(e) => setFilters({ ...filters, search: e.target.value })}
            aria-label="Search player"
          />
        </label>
        <select
          className="input"
          value={filters.team}
          onChange={(e) => setFilters({ ...filters, team: e.target.value })}
          aria-label="Filter by state team"
        >
          <option value="">All state teams</option>
          {teams.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <select
          className="input"
          value={filters.role}
          onChange={(e) => setFilters({ ...filters, role: e.target.value })}
          aria-label="Filter by role"
        >
          <option value="">All roles</option>
          {roles.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
        <select
          className="input"
          value={filters.grade}
          onChange={(e) => setFilters({ ...filters, grade: e.target.value })}
          aria-label="Minimum confidence grade"
        >
          <option value="">Any confidence</option>
          <option value="A">Grade A or better</option>
          <option value="B">Grade B or better</option>
          <option value="C">Grade C or better</option>
        </select>
        <label className="flex items-center gap-1 text-2xs text-ink-soft">
          Min score
          <input
            type="number"
            min={0}
            max={100}
            className="input w-16"
            value={filters.minScore}
            onChange={(e) => setFilters({ ...filters, minScore: Number(e.target.value) })}
            aria-label="Minimum final score"
          />
        </label>
        <label className="flex items-center gap-1 text-2xs text-ink-soft">
          Min balls
          <input
            type="number"
            min={0}
            step={50}
            className="input w-20"
            value={filters.minExposure}
            onChange={(e) => setFilters({ ...filters, minExposure: Number(e.target.value) })}
            aria-label="Minimum balls of exposure"
          />
        </label>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-2xs text-ink-faint">
            <SlidersHorizontal className="mr-1 inline h-3 w-3" />
            {filtered.length} of {rows.length} players match
            {activeFilterCount ? ` · ${activeFilterCount} filter(s) active` : ""} · scope: {scopeLabel}
          </span>
          <button
            className="btn"
            onClick={() => setFilters(DEFAULT_FILTERS)}
            disabled={!activeFilterCount}
            title="Clear all filters"
          >
            <RotateCcw className="h-3.5 w-3.5" /> Clear
          </button>
          <button
            className="btn"
            onClick={() =>
              downloadCsv(
                `royal-scout-top-${discipline}-${scopeLabel.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}.csv`,
                filtered as unknown as Record<string, unknown>[],
                columns
                  .filter((c) => c.key !== "filtered_rank")
                  .map((c) => ({ key: c.key, label: c.label })),
                { ...provenance, scope: scopeLabel, rows_exported: filtered.length, filters: JSON.stringify(filters) },
              )
            }
          >
            <Download className="h-3.5 w-3.5" /> Export view
          </button>
        </div>
      </div>

      <div className="max-h-[70vh] overflow-auto">
        <table className="w-full border-collapse text-left text-xs">
          <thead className="sticky top-0 z-10 bg-surface-muted/95 backdrop-blur">
            <tr className="border-b border-surface-line">
              {columns.map((c) => (
                <th
                  key={c.key}
                  scope="col"
                  className={`px-2.5 py-2 text-2xs font-semibold tracking-[0.05em] whitespace-nowrap text-ink-faint uppercase ${
                    c.align === "right" ? "text-right" : c.align === "center" ? "text-center" : "text-left"
                  }`}
                >
                  {c.sortable ? (
                    <button className="inline-flex items-center gap-1 hover:text-ink" onClick={() => toggleSort(c.key)}>
                      {c.label}
                      {sort.key === c.key ? (
                        sort.dir === "desc" ? (
                          <ArrowDown className="h-3 w-3 text-royal-pink" />
                        ) : (
                          <ArrowUp className="h-3 w-3 text-royal-pink" />
                        )
                      ) : null}
                    </button>
                  ) : (
                    c.label
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-line/80">
            {shown.map((row) => {
              const delta = row.rank !== undefined ? row.rank - row.filtered_rank : null;
              const score = row[scoreKey] as number | null;
              const isOpen = expanded === row.player;
              return (
                <Fragment key={row.player}>
                  <tr className="group hover:bg-surface-muted/70">
                    <td className="px-2.5 py-1.5 text-right font-mono tabular-nums text-ink-faint">
                      {row.filtered_rank}
                      {delta !== null && delta !== 0 ? (
                        <span
                          className={`ml-1 text-2xs ${delta > 0 ? "text-emerald-600" : "text-rose-600"}`}
                          title={`Global rank ${row.rank}; moves ${delta > 0 ? "up" : "down"} ${Math.abs(delta)} under the current filters`}
                        >
                          {delta > 0 ? "▲" : "▼"}
                          {Math.abs(delta)}
                        </span>
                      ) : null}
                    </td>
                    <td className="max-w-[220px] px-2.5 py-1.5">
                      <PlayerLink name={row.player} meta={row.granularity === "aggregate" ? "aggregate rows" : undefined} />
                    </td>
                    <td className="max-w-[150px] truncate px-2.5 py-1.5 text-ink-soft">{teamLabel(row)}</td>
                    <td className="px-2.5 py-1.5 text-ink-soft">{titleCase(row.primary_role ?? "—")}</td>
                    {discipline === "bowling" ? (
                      <td className="px-2.5 py-1.5 text-ink-soft">
                        {row.bowler_type ? row.bowler_type.replace(/_/g, " ") : "—"}
                      </td>
                    ) : null}
                    {discipline === "batting" ? (
                      <>
                        <Cell v={row.matches} />
                        <Cell v={row.innings} />
                        <Cell v={row.runs} strong />
                        <Cell v={row.balls_faced} />
                        <Cell v={row.average} dp={2} />
                        <Cell v={row.strike_rate} dp={2} />
                        <Cell v={row.fours} />
                        <Cell v={row.sixes} />
                      </>
                    ) : (
                      <>
                        <Cell v={row.innings} />
                        <td className="px-2.5 py-1.5 text-right font-mono tabular-nums text-ink-soft">{row.overs ?? "—"}</td>
                        <Cell v={row.wickets} strong />
                        <Cell v={row.runs_conceded} />
                        <Cell v={row.average} dp={2} />
                        <Cell v={row.economy} dp={2} />
                        <Cell v={row.bowling_strike_rate} dp={2} />
                        <Cell v={row.dot_pct} dp={1} />
                      </>
                    )}
                    <Cell v={row.consistency} dp={1} />
                    <td className="px-2.5 py-1.5 text-right font-mono tabular-nums">
                      {row.pressure_score === null || row.pressure_score === undefined ? (
                        <span className="text-ink-faint" title="No ball-by-ball data: pressure is not measurable">
                          n/a
                        </span>
                      ) : (
                        <span className={scoreTone(row.pressure_score)}>{row.pressure_score.toFixed(1)}</span>
                      )}
                    </td>
                    <td className="px-2.5 py-1.5 text-center">
                      <GradeBadge grade={row.grade} />
                    </td>
                    <td className="px-2.5 py-1.5 text-right font-mono tabular-nums text-ink-faint">
                      {row.score_coverage !== undefined && row.score_coverage !== null
                        ? `${Math.round(row.score_coverage * 100)}%`
                        : "—"}
                    </td>
                    <td className="px-2.5 py-1.5 text-right">
                      <button
                        className={`font-mono text-sm font-semibold tabular-nums ${scoreTone(score)} hover:underline`}
                        onClick={() => setExpanded(isOpen ? null : row.player)}
                        title="Show the score decomposition"
                      >
                        {score === null || score === undefined ? "—" : score.toFixed(1)}
                      </button>
                    </td>
                  </tr>
                  {isOpen ? (
                    <tr className="bg-navy-950/95 text-white">
                      <td colSpan={columns.length} className="px-4 py-2.5">
                        <div className="grid gap-x-6 gap-y-1 text-2xs sm:grid-cols-2 lg:grid-cols-4">
                          <Detail label="Eligibility" value={row.eligibility_reason ?? "meets the ranked thresholds"} />
                          <Detail
                            label="Composite coverage"
                            value={`${Math.round((row.score_coverage ?? 0) * 100)}% of the nominal weight is supported by this dataset`}
                          />
                          <Detail label="Exposure" value={`${num(row.exposure_balls)} balls`} />
                          <Detail label="Confidence" value={`grade ${row.grade} · score ${dec(row.confidence_score, 1)}`} />
                        </div>
                        {(() => {
                          const components: { key: keyof PlayerRow; label: string }[] =
                            discipline === "batting"
                              ? [
                                  { key: "performance_score", label: "performance" },
                                  { key: "consistency", label: "consistency" },
                                  { key: "reliability", label: "reliability" },
                                  { key: "pressure_score", label: "pressure" },
                                  { key: "role_adjusted_score", label: "role_adjusted" },
                                  { key: "confidence_score", label: "confidence" },
                                ]
                              : [
                                  { key: "performance_score", label: "performance" },
                                  { key: "wicket_taking_score", label: "wicket_taking" },
                                  { key: "economy_containment_score", label: "economy" },
                                  { key: "consistency", label: "consistency" },
                                  { key: "pressure_score", label: "pressure" },
                                  { key: "confidence_score", label: "confidence" },
                                ];
                          const available = components.filter((c) => typeof row[c.key] === "number");
                          const nominal = available.reduce((sum, c) => sum + (weights?.[c.label] ?? 0), 0);
                          return (
                            <div className="mt-2 border-t border-white/15 pt-1.5">
                              <p className="mb-1 text-[0.6rem] tracking-[0.12em] text-white/40 uppercase">
                                Score decomposition — weights renormalise over the components this dataset supports
                              </p>
                              <div className="flex flex-wrap gap-x-4 gap-y-0.5 font-mono text-2xs text-white/80">
                                {available.map((c) => {
                                  const nominalWeight = weights?.[c.label] ?? null;
                                  const applied = nominalWeight !== null && nominal > 0 ? nominalWeight / nominal : null;
                                  return (
                                    <span key={c.label}>
                                      {c.label.replace(/_/g, " ")}{" "}
                                      <span className="text-white/55">
                                        {nominalWeight === null ? "w n/a" : `w ${(nominalWeight * 100).toFixed(0)}%`}
                                        {applied === null ? "" : ` → ${(applied * 100).toFixed(0)}% applied`}
                                      </span>{" "}
                                      <span className="text-white">{dec(row[c.key] as number, 1)}</span>
                                    </span>
                                  );
                                })}
                                {components.length > available.length ? (
                                  <span className="text-amber-300">
                                    missing: {components.filter((c) => typeof row[c.key] !== "number").map((c) => c.label.replace(/_/g, " ")).join(", ")}
                                  </span>
                                ) : null}
                              </div>
                            </div>
                          );
                        })()}
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              );
            })}
            {!shown.length ? (
              <tr>
                <td colSpan={columns.length} className="px-3 py-8 text-center text-xs text-ink-faint">
                  No player in this scope clears the eligibility thresholds with the current filters. The engine never
                  pads a leaderboard — relax the filters or widen the scope to see more players.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      {filtered.length > shown.length ? (
        <p className="border-t border-surface-line px-4 py-2 text-2xs text-ink-faint">
          Showing the first {shown.length} of {filtered.length} matching players, ranked within this view.
        </p>
      ) : null}
    </div>
  );
}

function Cell({ v, dp = 0, strong = false }: { v: number | null | undefined; dp?: number; strong?: boolean }) {
  return (
    <td className={`px-2.5 py-1.5 text-right font-mono tabular-nums ${strong ? "font-semibold text-ink" : "text-ink-soft"}`}>
      {v === null || v === undefined ? "—" : dp ? v.toFixed(dp) : num(v)}
    </td>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[0.6rem] tracking-[0.12em] text-white/40 uppercase">{label}</p>
      <p className="mt-0.5 leading-snug text-white/85">{value}</p>
    </div>
  );
}
