"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Plus, X } from "lucide-react";
import type { PlayerRow } from "@/lib/types";
import { dec, num, pct, scoreTone, titleCase } from "@/lib/format";
import { Badge, GradeBadge } from "./ui/badge";
import { DataTable, TBody, TD, TH, THead } from "./ui/table";
import { PlayerRadar } from "./charts/radar";
import { RankedBars } from "./charts/bars";
import { Notice } from "./ui/empty";

const MAX = 4;

type ComparisonData = {
  names: string[];
  batting: Record<string, PlayerRow>;
  bowling: Record<string, PlayerRow>;
  roles: Record<string, { primary_role?: string | null } | null>;
};

const COMPONENTS: { key: keyof PlayerRow; label: string }[] = [
  { key: "performance_score", label: "Performance" },
  { key: "consistency", label: "Consistency" },
  { key: "reliability", label: "Reliability" },
  { key: "pressure_score", label: "Pressure" },
  { key: "role_adjusted_score", label: "Role-adjusted" },
  { key: "confidence_score", label: "Confidence" },
  { key: "wicket_taking_score", label: "Wicket-taking" },
  { key: "economy_containment_score", label: "Containment" },
];

export function ComparisonLab({ data }: { data: ComparisonData }) {
  const params = useSearchParams();
  const all = useMemo(() => data.names, [data.names]);
  const [selected, setSelected] = useState<string[]>([]);
  const [pending, setPending] = useState("");

  useEffect(() => {
    const preset = params.get("players");
    if (preset) {
      const names = preset.split(",").map(decodeURIComponent).filter((n) => all.includes(n));
      if (names.length) setSelected([...new Set(names)].slice(0, MAX));
    }
  }, [params, all]);

  const rows = selected.map((n) => ({
    name: n,
    batting: data.batting[n] ?? null,
    bowling: data.bowling[n] ?? null,
    role: data.roles[n] ?? null,
  }));

  const radarMetrics = COMPONENTS.filter((c) => rows.some((r) => (r.batting?.[c.key] ?? r.bowling?.[c.key]) != null));
  const series = rows.map((r) => ({
    name: r.name,
    values: radarMetrics.map((c) => {
      const v = data.batting[r.name]?.[c.key] ?? data.bowling[r.name]?.[c.key];
      return typeof v === "number" ? v : null;
    }),
  }));

  const comparable = rows.filter((r) => r.batting).length > 1 || rows.filter((r) => r.bowling).length > 1;

  return (
    <div className="px-5 py-4">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <select className="input w-64" value={pending} onChange={(e) => setPending(e.target.value)} aria-label="Choose a player">
          <option value="">Choose a player…</option>
          {all.map((n) => (
            <option key={n} value={n} disabled={selected.includes(n)}>{n}</option>
          ))}
        </select>
        <button
          className="btn-pink"
          disabled={!pending || selected.length >= MAX || selected.includes(pending)}
          onClick={() => {
            setSelected([...selected, pending]);
            setPending("");
          }}
        >
          <Plus className="h-3.5 w-3.5" /> Add
        </button>
        {selected.length ? (
          <button className="btn" onClick={() => setSelected([])}>Clear all</button>
        ) : null}
        <span className="ml-auto text-2xs text-ink-faint">{selected.length}/{MAX} selected</span>
      </div>

      {selected.length ? (
        <div className="mb-4 flex flex-wrap gap-1.5">
          {selected.map((n) => (
            <span key={n} className="inline-flex items-center gap-1 rounded border border-surface-line bg-surface-muted px-2 py-1 text-2xs">
              {n}
              <button aria-label={`Remove ${n}`} onClick={() => setSelected(selected.filter((s) => s !== n))}>
                <X className="h-3 w-3 text-ink-faint hover:text-rose-600" />
              </button>
            </span>
          ))}
        </div>
      ) : (
        <Notice>Select two or more players to compare. Roles and sample sizes are shown alongside every metric.</Notice>
      )}

      {selected.length ? (
        <div className="grid gap-5 xl:grid-cols-2">
          <div>
            <p className="section-label mb-2">Normalised component profile</p>
            <PlayerRadar metrics={radarMetrics.map((c) => c.label)} series={series} height={330} />
            {!comparable ? (
              <Notice tone="warning">
                These players do not share a discipline, so a direct comparison is limited. Cross-discipline comparisons are
                shown for context only and are never used to rank one against the other.
              </Notice>
            ) : null}
          </div>
          <div>
            <p className="section-label mb-2">Batting output</p>
            <RankedBars
              data={rows.filter((r) => r.batting).map((r) => ({ name: r.name, value: r.batting?.rabi ?? null }))}
              valueLabel="Batting index"
              height={150}
              colour="#102A54"
            />
            <p className="section-label mt-3 mb-2">Bowling output</p>
            <RankedBars
              data={rows.filter((r) => r.bowling).map((r) => ({ name: r.name, value: r.bowling?.rabi_bowl ?? null }))}
              valueLabel="Bowling index"
              height={150}
              colour="#E8117F"
            />
          </div>
        </div>
      ) : null}

      {selected.length ? (
        <>
          <div className="mt-5">
            <DataTable>
              <THead>
                <TH>Metric</TH>
                {rows.map((r) => <TH key={r.name} align="right">{r.name.split(" ").slice(-2).join(" ")}</TH>)}
              </THead>
              <TBody>
                <Row label="Role" values={rows.map((r) => (r.role?.primary_role ? titleCase(r.role.primary_role) : "—"))} />
                <Row label="Confidence grade" values={rows.map((r) => <GradeBadge key={r.name} grade={r.batting?.grade ?? r.bowling?.grade} />)} />
                <Row label="Balls faced" values={rows.map((r) => num(r.batting?.balls_faced ?? null))} mono />
                <Row label="Runs" values={rows.map((r) => num(r.batting?.runs ?? null))} mono />
                <Row label="Average" values={rows.map((r) => dec(r.batting?.average ?? null))} mono />
                <Row label="Strike rate" values={rows.map((r) => dec(r.batting?.strike_rate ?? null, 1))} mono />
                <Row label="Boundary %" values={rows.map((r) => pct(r.batting?.boundary_pct ?? null, 1))} mono />
                <Row label="Dot ball %" values={rows.map((r) => pct(r.batting?.dot_pct ?? null, 1))} mono />
                <Row label="Legal balls bowled" values={rows.map((r) => num(r.bowling?.legal_balls ?? null))} mono />
                <Row label="Wickets" values={rows.map((r) => num(r.bowling?.wickets ?? null))} mono />
                <Row label="Economy" values={rows.map((r) => dec(r.bowling?.economy ?? null))} mono />
                <Row label="Bowling SR" values={rows.map((r) => dec(r.bowling?.bowling_strike_rate ?? null))} mono />
                <Row label="Bowling average" values={rows.map((r) => dec(r.bowling?.average ?? null))} mono />
                <Row label="Consistency" values={rows.map((r) => dec(r.batting?.consistency ?? r.bowling?.consistency ?? null, 1))} mono />
                <Row label="Pressure" values={rows.map((r) => (r.batting?.pressure_score ?? r.bowling?.pressure_score) == null ? "unavailable" : dec(r.batting?.pressure_score ?? r.bowling?.pressure_score ?? null, 1))} mono />
                <Row label="Composite coverage" values={rows.map((r) => pct((r.batting?.score_coverage ?? r.bowling?.score_coverage ?? 0) * 100, 0))} mono />
                <Row label="Batting index" values={rows.map((r) => <span key={r.name} className={`font-mono font-semibold ${scoreTone(r.batting?.rabi ?? null)}`}>{dec(r.batting?.rabi ?? null, 1)}</span>)} />
                <Row label="Bowling index" values={rows.map((r) => <span key={r.name} className={`font-mono font-semibold ${scoreTone(r.bowling?.rabi_bowl ?? null)}`}>{dec(r.bowling?.rabi_bowl ?? null, 1)}</span>)} />
              </TBody>
            </DataTable>
          </div>

          <div className="mt-4 space-y-2">
            <p className="section-label">Statistical interpretation</p>
            {rows.map((r) => {
              const b = r.batting;
              const w = r.bowling;
              const parts: string[] = [];
              if (b) parts.push(`${b.exposure_balls} balls faced across ${b.innings} innings (grade ${b.grade})`);
              if (w) parts.push(`${w.legal_balls} legal balls bowled, ${w.wickets} wickets (grade ${w.grade})`);
              if (b && b.pressure_score !== null && b.pressure_score !== undefined) parts.push(`pressure score ${b.pressure_score.toFixed(1)}`);
              else parts.push("no pressure evidence");
              return (
                <p key={r.name} className="text-2xs leading-relaxed text-ink-soft">
                  <Link href={`/players/${encodeURIComponent(r.name)}`} className="data-link font-medium">{r.name}</Link> — {parts.join("; ")}.
                </p>
              );
            })}
            <Notice>
              A higher index is not automatically a better selection: role, phase requirement and match situation decide
              which component matters. Use the component profile, not the single index, to make the call.
            </Notice>
          </div>
        </>
      ) : null}
    </div>
  );
}

function Row({ label, values, mono = false }: { label: string; values: React.ReactNode[]; mono?: boolean }) {
  return (
    <tr>
      <TD className="font-medium">{label}</TD>
      {values.map((v, i) => (
        <TD key={i} align="right" mono={mono}>{v}</TD>
      ))}
    </tr>
  );
}
