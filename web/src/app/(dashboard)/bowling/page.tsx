import Link from "next/link";
import { loadDashboardDataset } from "@/lib/server-dataset";
import { Target } from "lucide-react";
import { getScope, hasBundle } from "@/lib/bundle";
import { dec, num, pct } from "@/lib/format";
import { PageHeader } from "@/components/shell";
import { Card, CardBody, CardHeader, Stat } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState, Notice } from "@/components/ui/empty";
import { MetricScatter } from "@/components/charts/scatter";
import { RankedBars } from "@/components/charts/bars";
import { Histogram } from "@/components/charts/histogram";
import { DataTable, TBody, TD, TH, THead } from "@/components/ui/table";

export default async function BowlingPage({ searchParams }: { searchParams: Promise<{ scope?: string }> }) {
  const bundle = (await loadDashboardDataset()).bundle;
  const { scope: scopeParam } = await searchParams;
  if (!hasBundle(bundle)) return <EmptyState tone="warning" title="No dataset analysed" description="Import data to populate bowling analytics." />;
  const scopeLabel = scopeParam && scopeParam !== "global" ? scopeParam : "All data";
  const rows = getScope(scopeLabel === "All data" ? null : scopeLabel, bundle)?.bowlers ?? [];

  const totalBalls = rows.reduce((s, r) => s + (r.legal_balls ?? 0), 0);
  const totalRuns = rows.reduce((s, r) => s + (r.runs_conceded ?? 0), 0);
  const totalWkts = rows.reduce((s, r) => s + (r.wickets ?? 0), 0);
  const pooledEcon = totalBalls ? (totalRuns * 6) / totalBalls : null;
  const pooledAvg = totalWkts ? totalRuns / totalWkts : null;
  const pooledSR = totalWkts ? totalBalls / totalWkts : null;

  const typeCounts = rows.reduce<Record<string, number>>((acc, r) => {
    const k = r.bowler_type ?? "unclassified";
    acc[k] = (acc[k] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-4">
      <PageHeader
        title="Bowling Analytics"
        icon={Target}
        description={`Workload, wicket-taking and containment for the ${rows.length} eligible bowlers in scope “${scopeLabel}”. Overs are converted to legal balls before any arithmetic — 3.4 overs is 22 balls, never 3.4 of anything.`}
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
        <Stat label="Legal balls" value={num(totalBalls)} hint={`${(totalBalls / 6).toFixed(1)} overs`} />
        <Stat label="Wickets" value={num(totalWkts)} />
        <Stat label="Pooled economy" value={dec(pooledEcon, 2)} hint="runs per over across the scope" />
        <Stat label="Pooled average" value={dec(pooledAvg, 2)} hint="runs per wicket" />
        <Stat label="Pooled strike rate" value={dec(pooledSR, 2)} hint="balls per wicket" />
        <Stat label="Specialist types" value={num(Object.keys(typeCounts).length)} hint="classified from data, not names" />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader
            title="Economy vs wicket-taking"
            subtitle="Lower economy is better (left is better here — axis kept honest by labelling). Bubble size is workload."
          />
          <CardBody>
            <MetricScatter
              points={rows.map((r) => ({ name: r.player, x: r.economy ?? null, y: r.bowling_strike_rate ?? null, size: r.legal_balls ?? 0 }))}
              xLabel="Economy (lower is better)"
              yLabel="Balls per wicket (lower is better)"
              xMean={pooledEcon ?? undefined}
              yMean={pooledSR ?? undefined}
              height={340}
            />
            <Notice>A bowler with an excellent economy and few wickets sits low-and-left; a strike bowler low-and-right is not automatically worse — both components are scored separately and shown in the table.</Notice>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Specialist classification" subtitle="Wicket-taker / economy / phase specialist, derived from workload and phase shares." />
          <CardBody>
            <ul className="space-y-1.5">
              {Object.entries(typeCounts).sort((a, z) => z[1] - a[1]).map(([type, count]) => (
                <li key={type} className="flex items-center justify-between gap-2 border-b border-surface-line/60 pb-1 text-xs">
                  <span className="text-ink-soft">{type.replace(/_/g, " ")}</span>
                  <Badge tone="info">{count}</Badge>
                </li>
              ))}
            </ul>
            <div className="mt-3">
              <Histogram values={rows.map((r) => r.economy ?? null)} label="Bowlers" bins={8} colour="#1B4B8F" height={170} />
            </div>
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader title="Wicket-taking score" subtitle="Strike rate and wickets per innings, population-relative." />
          <CardBody>
            <RankedBars
              data={[...rows].sort((a, z) => (z.wicket_taking_score ?? 0) - (a.wicket_taking_score ?? 0)).slice(0, 12)
                .map((r) => ({ name: r.player, value: r.wicket_taking_score ?? null }))}
              valueLabel="Wicket-taking score" height={300} colour="#102A54"
            />
          </CardBody>
        </Card>
        <Card>
          <CardHeader title="Containment score" subtitle="Economy, dot-ball creation and average, combined." />
          <CardBody>
            <RankedBars
              data={[...rows].sort((a, z) => (z.economy_containment_score ?? 0) - (a.economy_containment_score ?? 0)).slice(0, 12)
                .map((r) => ({ name: r.player, value: r.economy_containment_score ?? null }))}
              valueLabel="Containment score" height={300} colour="#E8117F"
            />
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader title="Bowling component table" subtitle="Every component on a 0–100 scale with its coverage." />
        <DataTable className="max-h-[520px] overflow-y-auto">
          <THead>
            <TH>Player</TH>
            <TH>Type</TH>
            <TH align="right">Overs</TH>
            <TH align="right">Wkts</TH>
            <TH align="right">Econ</TH>
            <TH align="right">Avg</TH>
            <TH align="right">SR</TH>
            <TH align="right">Dot %</TH>
            <TH align="right">Wkt score</TH>
            <TH align="right">Contain</TH>
            <TH align="right">Consist.</TH>
            <TH align="right">Pressure</TH>
            <TH align="right">Coverage</TH>
            <TH align="right">Index</TH>
          </THead>
          <TBody>
            {[...rows].sort((a, z) => (z.rabi_bowl ?? 0) - (a.rabi_bowl ?? 0)).map((r) => (
              <tr key={r.player}>
                <TD><Link className="data-link" href={`/players/${encodeURIComponent(r.player)}`}>{r.player}</Link></TD>
                <TD className="text-2xs text-ink-soft">{(r.bowler_type ?? "—").replace(/_/g, " ")}</TD>
                <TD align="right" mono>{r.overs ?? "—"}</TD>
                <TD align="right" mono>{num(r.wickets)}</TD>
                <TD align="right" mono>{dec(r.economy)}</TD>
                <TD align="right" mono>{dec(r.average)}</TD>
                <TD align="right" mono>{dec(r.bowling_strike_rate)}</TD>
                <TD align="right" mono>{dec(r.dot_pct, 1)}</TD>
                <TD align="right" mono>{dec(r.wicket_taking_score, 1)}</TD>
                <TD align="right" mono>{dec(r.economy_containment_score, 1)}</TD>
                <TD align="right" mono>{dec(r.consistency, 1)}</TD>
                <TD align="right" mono>{r.pressure_score === null || r.pressure_score === undefined ? <span className="text-ink-faint">n/a</span> : dec(r.pressure_score, 1)}</TD>
                <TD align="right" mono>{pct((r.score_coverage ?? 0) * 100, 0)}</TD>
                <TD align="right" mono className="font-semibold">{dec(r.rabi_bowl, 1)}</TD>
              </tr>
            ))}
          </TBody>
        </DataTable>
      </Card>
    </div>
  );
}
