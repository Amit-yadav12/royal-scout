import Link from "next/link";
import { loadDashboardDataset } from "@/lib/server-dataset";
import { TrendingUp } from "lucide-react";
import { getScope, hasBundle } from "@/lib/bundle";
import { dec, num, pct } from "@/lib/format";
import { PageHeader } from "@/components/shell";
import { Card, CardBody, CardHeader, KeyValue, Stat } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState, Notice } from "@/components/ui/empty";
import { MetricScatter } from "@/components/charts/scatter";
import { Histogram } from "@/components/charts/histogram";
import { RankedBars } from "@/components/charts/bars";
import { DataTable, TBody, TD, TH, THead } from "@/components/ui/table";

export default async function BattingPage({ searchParams }: { searchParams: Promise<{ scope?: string }> }) {
  const bundle = (await loadDashboardDataset()).bundle;
  const { scope: scopeParam } = await searchParams;
  if (!hasBundle(bundle)) return <EmptyState tone="warning" title="No dataset analysed" description="Import data to populate batting analytics." />;
  const scopeLabel = scopeParam && scopeParam !== "global" ? scopeParam : "All data";
  const rows = getScope(scopeLabel === "All data" ? null : scopeLabel, bundle)?.batters ?? [];
  const all = Object.values(bundle.batting.players);
  const caps = bundle.schema.capabilities;

  const totalRuns = rows.reduce((s, r) => s + (r.runs ?? 0), 0);
  const totalBalls = rows.reduce((s, r) => s + (r.balls_faced ?? 0), 0);
  const pooledSR = totalBalls ? (totalRuns * 100) / totalBalls : null;
  const meanSR = rows.length ? rows.reduce((s, r) => s + (r.strike_rate ?? 0), 0) / rows.length : null;
  const meanAvg = rows.filter((r) => r.average !== null).reduce((s, r) => s + (r.average ?? 0), 0) / Math.max(1, rows.filter((r) => r.average !== null).length);

  const scatter = rows.map((r) => ({
    name: r.player,
    x: r.strike_rate ?? null,
    y: r.average ?? null,
    size: r.balls_faced ?? 0,
    group: r.primary_role,
  }));

  const topBy = (key: "boundary_pct" | "dot_pct" | "consistency") =>
    [...rows]
      .filter((r) => r[key] !== null && r[key] !== undefined)
      .sort((a, z) => {
        if (key === "dot_pct") return (a[key] as number) - (z[key] as number);
        return (z[key] as number) - (a[key] as number);
      })
      .slice(0, 12)
      .map((r) => ({ name: r.player, value: r[key] as number }));

  return (
    <div className="space-y-4">
      <PageHeader
        title="Batting Analytics"
        icon={TrendingUp}
        description={`Output, distribution and scoring components for the ${rows.length} eligible batters in scope “${scopeLabel}”. Averages use genuine dismissals; not-outs are never converted into dismissals.`}
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
        <Stat label="Runs in scope" value={num(totalRuns)} />
        <Stat label="Balls faced" value={num(totalBalls)} />
        <Stat label="Pooled strike rate" value={dec(pooledSR, 1)} hint="runs per 100 balls across the scope" />
        <Stat label="Mean of player SRs" value={dec(meanSR, 1)} hint="unweighted, for contrast with the pooled rate" />
        <Stat label="Mean average" value={dec(meanAvg, 2)} hint="runs per dismissal" />
        <Stat label="Phase splits" value={caps.phase_data ? "available" : "unavailable"} tone={caps.phase_data ? "positive" : "warning"} hint={caps.phase_data ? "from ball-by-ball" : "needs delivery-level data"} />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader
            title="Volume vs efficiency"
            subtitle="Strike rate against average. Bubble size is balls faced, so a large bubble is a sample you can trust. Dashed lines mark the scope means."
          />
          <CardBody>
            <MetricScatter points={scatter} xLabel="Strike rate" yLabel="Average" xMean={pooledSR ?? undefined} yMean={meanAvg} height={340} />
            <Notice>High strike rate with a low average is a finisher profile; the reverse is an anchor. Neither is intrinsically better — role weighting handles the difference.</Notice>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Distribution of strike rates" subtitle="Every eligible batter in scope, bucketed." />
          <CardBody>
            <Histogram values={rows.map((r) => r.strike_rate ?? null)} label="Batters" bins={9} />
            <div className="mt-3 grid grid-cols-3 gap-2">
              <Mini label="Median SR" value={dec(median(rows.map((r) => r.strike_rate)), 1)} />
              <Mini label="Highest SR" value={dec(Math.max(...rows.map((r) => r.strike_rate ?? 0)), 1)} />
              <Mini label="Lowest SR" value={dec(Math.min(...rows.map((r) => r.strike_rate ?? Infinity)), 1)} />
            </div>
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card>
          <CardHeader title="Boundary dependency" subtitle="Share of runs scored in fours and sixes." />
          <CardBody><RankedBars data={topBy("boundary_pct")} valueLabel="Boundary %" height={300} /></CardBody>
        </Card>
        <Card>
          <CardHeader title="Dot-ball avoidance" subtitle="Lowest dot-ball share first." />
          <CardBody><RankedBars data={topBy("dot_pct")} valueLabel="Dot ball %" height={300} colour="#0F766E" /></CardBody>
        </Card>
        <Card>
          <CardHeader title="Consistency" subtitle="Innings-to-innings stability (CV-based, population-relative)." />
          <CardBody><RankedBars data={topBy("consistency")} valueLabel="Consistency score" height={300} colour="#C9A227" /></CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Scoring components"
          subtitle="Each component is on a 0–100 population scale. An em dash means the dataset cannot support that component for that player."
          action={<Link href="/methodology" className="btn">Definitions</Link>}
        />
        <DataTable className="max-h-[520px] overflow-y-auto">
          <THead>
            <TH>Player</TH>
            <TH align="right">Balls</TH>
            <TH align="right">Avg</TH>
            <TH align="right">SR</TH>
            <TH align="right">Perf.</TH>
            <TH align="right">Consist.</TH>
            <TH align="right">Reliab.</TH>
            <TH align="right">Pressure</TH>
            <TH align="right">Role adj.</TH>
            <TH align="right">Conf.</TH>
            <TH align="right">Coverage</TH>
            <TH align="right">RABI</TH>
          </THead>
          <TBody>
            {[...rows].sort((a, z) => (z.rabi ?? 0) - (a.rabi ?? 0)).map((r) => (
              <tr key={r.player}>
                <TD><Link className="data-link" href={`/players/${encodeURIComponent(r.player)}`}>{r.player}</Link></TD>
                <TD align="right" mono>{num(r.balls_faced)}</TD>
                <TD align="right" mono>{dec(r.average)}</TD>
                <TD align="right" mono>{dec(r.strike_rate, 1)}</TD>
                <TD align="right" mono>{dec(r.performance_score, 1)}</TD>
                <TD align="right" mono>{dec(r.consistency, 1)}</TD>
                <TD align="right" mono>{dec(r.reliability, 1)}</TD>
                <TD align="right" mono>{r.pressure_score === null || r.pressure_score === undefined ? <span className="text-ink-faint">n/a</span> : dec(r.pressure_score, 1)}</TD>
                <TD align="right" mono>{dec(r.role_adjusted_score, 1)}</TD>
                <TD align="right" mono>{dec(r.confidence_score, 1)}</TD>
                <TD align="right" mono>{pct((r.score_coverage ?? 0) * 100, 0)}</TD>
                <TD align="right" mono className="font-semibold">{dec(r.rabi, 1)}</TD>
              </tr>
            ))}
          </TBody>
        </DataTable>
      </Card>

      <Card>
        <CardHeader title="Situational splits" subtitle="Computed from record-level context only. Phase splits require ball-by-ball data and live in Pressure Analytics." />
        <CardBody className="grid gap-4 md:grid-cols-2">
          {(["by_season", "by_opposition"] as const).map((group) => {
            // Show splits for the leading players in this scope rather than the first
            // keys in the dictionary, which would otherwise all belong to one player.
            const leading = new Set(rows.slice(0, 12).map((r) => r.player));
            const keys = Object.keys(bundle.batting.splits[group] ?? {})
              .filter((k) => leading.has(k.split("|")[0]))
              .slice(0, 8);
            return (
              <div key={group}>
                <p className="section-label mb-2">{group.replace("by_", "By ")}</p>
                {keys.length ? (
                  <ul className="space-y-1 text-xs">
                    {keys.map((k) => {
                      const [player, key] = k.split("|");
                      const d = bundle.batting.splits[group][k];
                      return (
                        <li key={k} className="flex items-baseline justify-between gap-2 border-b border-surface-line/60 pb-1">
                          <span className="truncate text-ink-soft">{player} · <span className="text-ink-faint">{key}</span></span>
                          <span className="shrink-0 font-mono text-2xs tabular-nums text-ink">{num(d.runs)} runs · SR {dec(d.strike_rate, 1)}</span>
                        </li>
                      );
                    })}
                  </ul>
                ) : <p className="text-xs text-ink-faint">No {group.replace("by_", "")} column was present in the source data.</p>}
              </div>
            );
          })}
        </CardBody>
      </Card>
    </div>
  );
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-surface-line bg-surface-muted px-2 py-1.5">
      <p className="text-[0.6rem] tracking-[0.1em] text-ink-faint uppercase">{label}</p>
      <p className="font-mono text-sm tabular-nums text-ink">{value}</p>
    </div>
  );
}

function median(values: (number | null | undefined)[]): number | null {
  const nums = values.filter((v): v is number => typeof v === "number").sort((a, b) => a - b);
  if (!nums.length) return null;
  const mid = Math.floor(nums.length / 2);
  return nums.length % 2 ? nums[mid] : (nums[mid - 1] + nums[mid]) / 2;
}
