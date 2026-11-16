import Link from "next/link";
import { Gauge } from "lucide-react";
import { bundle, getScope, hasBundle } from "@/lib/bundle";
import { dec, num, pct } from "@/lib/format";
import { PageHeader } from "@/components/shell";
import { Card, CardBody, CardHeader, KeyValue, Stat } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState, Notice } from "@/components/ui/empty";
import { DataTable, TBody, TD, TH, THead } from "@/components/ui/table";
import { Heatmap } from "@/components/charts/heatmap";

export default async function PressurePage({ searchParams }: { searchParams: Promise<{ scope?: string }> }) {
  const { scope: scopeParam } = await searchParams;
  if (!hasBundle()) return <EmptyState tone="warning" title="No dataset" description="No bundle has been generated yet." />;
  const b = bundle;
  const scopeLabel = scopeParam && scopeParam !== "global" ? scopeParam : "All data";
  const scope = getScope(scopeLabel === "All data" ? null : scopeLabel);
  const p = b.pressure;
  const ballByBall = b.schema.capabilities.ball_by_ball;

  const batters = (scope?.batters ?? []).filter((r) => r.pressure_score !== null && r.pressure_score !== undefined);
  const bowlers = (scope?.bowlers ?? []).filter((r) => r.pressure_score !== null && r.pressure_score !== undefined);
  const provisional = [...batters, ...bowlers].filter((r) => {
    const detail = (p.batting[r.player] ?? p.bowling[r.player])?.detail;
    return detail && detail.status === "provisional";
  }).length;

  const scenarioCounts = (() => {
    const totals: Record<string, number> = {};
    for (const entry of [...Object.values(p.batting), ...Object.values(p.bowling)]) {
      const counts = (entry.detail?.scenario_counts ?? {}) as Record<string, number>;
      for (const [k, v] of Object.entries(counts)) totals[k] = Math.max(totals[k] ?? 0, v);
    }
    return totals;
  })();

  return (
    <div className="space-y-4">
      <PageHeader
        title="Pressure Analytics"
        icon={Gauge}
        description="Pressure is defined by the match situation — required rate, wicket resources, recent wicket clusters — not by the over number. Every score states its basis; where the data cannot support a pressure metric, it is reported as unavailable."
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
        <Stat label="Pressure basis" value={<span className="text-base">{(p.basis === "ball_by_ball" ? "Ball-by-ball" : p.basis === "innings_index_proxy" ? "Proxy only" : "Unavailable")}</span>} tone={p.basis === "ball_by_ball" ? "positive" : "warning"} hint={ballByBall ? "delivery-level situations" : "no delivery data supplied"} />
        <Stat label="Batters scored" value={num(batters.length)} hint="with a measurable pressure differential" />
        <Stat label="Bowlers scored" value={num(bowlers.length)} />
        <Stat label="Provisional" value={num(provisional)} tone={provisional ? "warning" : "positive"} hint="limited tagged exposure" />
        <Stat label="Scenarios" value={num(p.scenarios.length)} hint="documented definitions" />
        <Stat label="Phase splits" value={p.phases_available ? "available" : "unavailable"} tone={p.phases_available ? "positive" : "warning"} />
      </div>

      {!ballByBall ? (
        <EmptyState
          tone="warning"
          title="No ball-by-ball data: match-pressure performance cannot be measured"
          description="Without delivery-level records the engine cannot see the scoreboard, so it refuses to label any innings as pressure. Record-level chasing proxies are shown below and are clearly marked as proxies, and the pressure component is excluded from every composite score (coverage drops accordingly)."
        />
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Card>
          <CardHeader title="Pressure scenario definitions" subtitle="These are the exact, configurable rules used to tag each delivery. Death overs alone never qualify." />
          <DataTable>
            <THead>
              <TH>Scenario</TH>
              <TH>Definition</TH>
              <TH align="right">Deliveries tagged</TH>
            </THead>
            <TBody>
              {p.scenarios.map((s) => (
                <tr key={s.id}>
                  <TD className="font-medium">{s.label}</TD>
                  <TD className="whitespace-normal text-ink-soft">{s.definition}</TD>
                  <TD align="right" mono>{num(scenarioCounts[s.id] ?? 0)}</TD>
                </tr>
              ))}
            </TBody>
          </DataTable>
        </Card>

        <Card>
          <CardHeader title="Method note" subtitle="What the number means, and what it does not." />
          <CardBody className="space-y-1.5">
            <KeyValue label="Pressure score" value="percentile of the player's own pressure-vs-non-pressure differential" />
            <KeyValue label="Shrinkage prior" value="40 tagged deliveries" mono />
            <KeyValue label="Provisional below" value={`${bundle.meta.config.scenarios.min_tagged_balls_for_score} tagged balls`} mono />
            <KeyValue label="Win expectancy" value="unvalidated heuristic — reported for context, never used to raise a score" />
            <Notice tone="warning">
              The pressure component carries {Math.round((bundle.meta.config.batting_weights.pressure ?? 0) * 100)}% of the batting
              composite and {Math.round((bundle.meta.config.bowling_weights.pressure ?? 0) * 100)}% of the bowling composite. Where it is
              unavailable the weights renormalise and the coverage figure falls — the score is never silently inflated.
            </Notice>
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Batters under pressure" subtitle="Pressure strike rate versus their own non-pressure strike rate." />
          <DataTable className="max-h-[420px] overflow-y-auto">
            <THead>
              <TH>Player</TH>
              <TH align="right">Pressure balls</TH>
              <TH align="right">Pressure SR</TH>
              <TH align="right">Normal SR</TH>
              <TH align="right">Δ SR</TH>
              <TH align="right">Score</TH>
              <TH>Status</TH>
            </THead>
            <TBody>
              {batters.sort((a, z) => (z.pressure_score ?? 0) - (a.pressure_score ?? 0)).slice(0, 20).map((r) => {
                const d = p.batting[r.player]?.detail ?? {};
                return (
                  <tr key={r.player}>
                    <TD><Link className="data-link" href={`/players/${encodeURIComponent(r.player)}`}>{r.player}</Link></TD>
                    <TD align="right" mono>{num(d.pressure_balls)}</TD>
                    <TD align="right" mono>{dec(d.pressure_strike_rate, 1)}</TD>
                    <TD align="right" mono>{dec(d.non_pressure_strike_rate, 1)}</TD>
                    <TD align="right" mono className={(d.strike_rate_delta ?? 0) >= 0 ? "text-emerald-700" : "text-rose-700"}>
                      {(d.strike_rate_delta ?? 0) >= 0 ? "+" : ""}{dec(d.strike_rate_delta, 1)}
                    </TD>
                    <TD align="right" mono className="font-semibold">{dec(r.pressure_score, 1)}</TD>
                    <TD><Badge tone={d.status === "provisional" ? "warning" : "positive"}>{d.status ?? "—"}</Badge></TD>
                  </tr>
                );
              })}
            </TBody>
          </DataTable>
        </Card>

        <Card>
          <CardHeader title="Bowlers under pressure" subtitle="Economy in tagged situations versus their own non-pressure economy." />
          <DataTable className="max-h-[420px] overflow-y-auto">
            <THead>
              <TH>Player</TH>
              <TH align="right">Pressure balls</TH>
              <TH align="right">Pressure econ</TH>
              <TH align="right">Normal econ</TH>
              <TH align="right">Δ econ</TH>
              <TH align="right">Score</TH>
              <TH>Status</TH>
            </THead>
            <TBody>
              {bowlers.sort((a, z) => (z.pressure_score ?? 0) - (a.pressure_score ?? 0)).slice(0, 20).map((r) => {
                const d = p.bowling[r.player]?.detail ?? {};
                return (
                  <tr key={r.player}>
                    <TD><Link className="data-link" href={`/players/${encodeURIComponent(r.player)}`}>{r.player}</Link></TD>
                    <TD align="right" mono>{num(d.pressure_balls)}</TD>
                    <TD align="right" mono>{dec(d.pressure_economy, 2)}</TD>
                    <TD align="right" mono>{dec(d.non_pressure_economy, 2)}</TD>
                    <TD align="right" mono className={(d.economy_delta ?? 0) >= 0 ? "text-emerald-700" : "text-rose-700"}>
                      {(d.economy_delta ?? 0) >= 0 ? "+" : ""}{dec(d.economy_delta, 2)}
                    </TD>
                    <TD align="right" mono className="font-semibold">{dec(r.pressure_score, 1)}</TD>
                    <TD><Badge tone={d.status === "provisional" ? "warning" : "positive"}>{d.status ?? "—"}</Badge></TD>
                  </tr>
                );
              })}
            </TBody>
          </DataTable>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Pressure Performance Index (PPI)"
          subtitle="Six components, each weighted. Missing components are dropped and the coverage is published — they are never filled with guesses."
        />
        <DataTable className="max-h-[440px] overflow-y-auto">
          <THead>
            <TH>Player</TH>
            <TH>Discipline</TH>
            <TH align="right">Pressure</TH>
            <TH align="right">Consist.</TH>
            <TH align="right">Role exec.</TH>
            <TH align="right">Opp. adj.</TH>
            <TH align="right">Impact</TH>
            <TH align="right">Conf.</TH>
            <TH align="right">Coverage</TH>
            <TH align="right">PPI</TH>
            <TH>Missing</TH>
          </THead>
          <TBody>
            {Object.entries(p.ppi_batting)
              .map(([player, v]: [string, any]) => ({ player, ...v }))
              .concat(Object.entries(p.ppi_bowling).map(([player, v]: [string, any]) => ({ player, ...v })))
              .sort((a: any, z: any) => (z.ppi ?? -1) - (a.ppi ?? -1))
              .slice(0, 40)
              .map((row: any, i: number) => (
                <tr key={`${row.player}-${row.discipline}-${i}`}>
                  <TD><Link className="data-link" href={`/players/${encodeURIComponent(row.player)}`}>{row.player}</Link></TD>
                  <TD className="text-2xs text-ink-soft">{row.discipline}</TD>
                  <TD align="right" mono>{dec(row.components.pressure_contribution, 1)}</TD>
                  <TD align="right" mono>{dec(row.components.consistency, 1)}</TD>
                  <TD align="right" mono>{dec(row.components.role_execution, 1)}</TD>
                  <TD align="right" mono>{dec(row.components.opposition_adjusted, 1)}</TD>
                  <TD align="right" mono>{dec(row.components.match_impact, 1)}</TD>
                  <TD align="right" mono>{dec(row.components.confidence, 1)}</TD>
                  <TD align="right" mono>{pct(row.coverage * 100, 0)}</TD>
                  <TD align="right" mono className="font-semibold">{dec(row.ppi, 1)}</TD>
                  <TD className="max-w-[220px] truncate text-2xs text-ink-faint">{row.missing_components.join(", ") || "none"}</TD>
                </tr>
              ))}
          </TBody>
        </DataTable>
      </Card>

      {p.phases_available && p.phases ? (
        <Card>
          <CardHeader
            title="Phase-wise strike rates"
            subtitle="Powerplay (overs 1–6), middle (7–15) and death (16–20), computed from the delivery stream. This is an innings-phase split — not a pressure measure."
          />
          <CardBody>
            <Heatmap
              rows={Object.keys(p.phases.batting).slice(0, 16)}
              columns={["powerplay", "middle", "death"]}
              values={Object.fromEntries(
                Object.entries(p.phases.batting).map(([player, phases]) => [
                  player,
                  {
                    powerplay: phases.powerplay?.strike_rate ?? null,
                    middle: phases.middle?.strike_rate ?? null,
                    death: phases.death?.strike_rate ?? null,
                  },
                ]),
              )}
              format={(v) => (v === null ? "—" : v.toFixed(0))}
              legend="Strike rate by phase. An em dash means the player was not exposed in that phase in this dataset."
            />
            <Notice>
              Phase splits use a different boundary from the pressure tags: an over in the death phase is not automatically a
              pressure situation, and vice versa. Both views are shown separately on purpose.
            </Notice>
          </CardBody>
        </Card>
      ) : null}

      <Card>
        <CardHeader title="Bowling by phase" subtitle="Economy and wicket rate per phase, where delivery data exists." />
        <CardBody>
          {p.phases && Object.keys(p.phases.bowling).length ? (
            <Heatmap
              rows={Object.keys(p.phases.bowling).slice(0, 16)}
              columns={["powerplay", "middle", "death"]}
              values={Object.fromEntries(
                Object.entries(p.phases.bowling).map(([player, phases]) => [
                  player,
                  {
                    powerplay: phases.powerplay?.economy ?? null,
                    middle: phases.middle?.economy ?? null,
                    death: phases.death?.economy ?? null,
                  },
                ]),
              )}
              format={(v) => (v === null ? "—" : v.toFixed(1))}
              legend="Economy by phase (lower is better). Players with no phase exposure show an em dash."
            />
          ) : (
            <Notice tone="warning">No ball-by-ball data, so phase economy cannot be computed.</Notice>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
