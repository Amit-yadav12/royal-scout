import { Activity } from "lucide-react";
import { loadDashboardDataset } from "@/lib/server-dataset";
import { hasBundle } from "@/lib/bundle";
import { dec, num } from "@/lib/format";
import { PageHeader } from "@/components/shell";
import { Card, CardBody, CardHeader, Stat } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState, Notice } from "@/components/ui/empty";
import { DataTable, TBody, TD, TH, THead } from "@/components/ui/table";
import { RankedBars } from "@/components/charts/bars";
import { MiniBar } from "@/components/charts/bars";

export default async function StabilityPage() {
  const bundle = (await loadDashboardDataset()).bundle;
  if (!hasBundle(bundle)) return <EmptyState tone="warning" title="No dataset" description="No bundle has been generated yet." />;
  const b = bundle;
  const bat = b.stability.batting;
  const bowl = b.stability.bowling;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Ranking Stability"
        icon={Activity}
        description="A ranking is only useful if it survives reasonable changes of opinion about the method. The engine re-runs the whole pipeline under alternative shrinkage priors, component weights and eligibility floors, then measures how far each player moves."
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
        <Stat label="Batting mean rho" value={dec(bat.mean_spearman, 3)} tone={(bat.mean_spearman ?? 0) >= 0.9 ? "positive" : "warning"} hint="Spearman vs baseline" />
        <Stat label="Batting worst rho" value={dec(bat.min_spearman, 3)} tone={(bat.min_spearman ?? 0) >= 0.8 ? "positive" : "warning"} />
        <Stat label="Bowling mean rho" value={dec(bowl.mean_spearman, 3)} tone={(bowl.mean_spearman ?? 0) >= 0.9 ? "positive" : "warning"} />
        <Stat label="Bowling worst rho" value={dec(bowl.min_spearman, 3)} tone={(bowl.min_spearman ?? 0) >= 0.8 ? "positive" : "warning"} />
        <Stat label="Batting variants" value={num(bat.variants.length)} hint="alternative configurations tested" />
        <Stat label="Bowling variants" value={num(bowl.variants.length)} />
      </div>

      <div className="space-y-4">
        {[bat, bowl].map((report) => (
          <Card key={report.discipline}>
            <CardHeader title={`${report.discipline} — assumption tests`} subtitle={report.interpretation} />
            <DataTable className="max-h-[380px] overflow-y-auto">
              <THead>
                <TH>Variant</TH>
                <TH align="right">Spearman ρ</TH>
                <TH align="right">Top-30 overlap</TH>
                <TH align="right">Top-30 changes</TH>
                <TH>What changed</TH>
              </THead>
              <TBody>
                {report.variants.map((v) => (
                  <tr key={v.variant}>
                    <TD className="font-mono text-2xs">{v.variant}</TD>
                    <TD align="right" mono className={v.spearman_vs_baseline === null ? "" : v.spearman_vs_baseline >= 0.9 ? "text-emerald-700" : v.spearman_vs_baseline >= 0.75 ? "text-amber-700" : "text-rose-700"}>
                      {dec(v.spearman_vs_baseline, 3)}
                    </TD>
                    <TD align="right" mono>{v.top30_overlap}/30</TD>
                    <TD align="right" mono>{v.top30_changes}</TD>
                    <TD className="max-w-[260px] whitespace-normal text-2xs text-ink-soft">{v.config_delta}</TD>
                  </tr>
                ))}
              </TBody>
            </DataTable>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        {[bat, bowl].map((report) => (
          <Card key={`${report.discipline}-spread`}>
            <CardHeader title="Most volatile players" subtitle="Largest rank movement across every tested configuration. A big spread means the ranking is not settled for that player." />
            <DataTable className="max-h-[420px] overflow-y-auto">
              <THead>
                <TH>Player</TH>
                <TH align="right">Baseline</TH>
                <TH align="right">Best</TH>
                <TH align="right">Worst</TH>
                <TH align="right">Spread</TH>
                <TH>Stability</TH>
              </THead>
              <TBody>
                {[...report.per_player].sort((a, z) => z.rank_spread - a.rank_spread).slice(0, 15).map((p) => (
                  <tr key={p.player}>
                    <TD className="max-w-[210px] truncate font-medium">{p.player}</TD>
                    <TD align="right" mono>{p.baseline_rank ?? "—"}</TD>
                    <TD align="right" mono>{p.min_rank}</TD>
                    <TD align="right" mono>{p.max_rank}</TD>
                    <TD align="right" mono>±{Math.round(p.rank_spread / 2)}</TD>
                    <TD><div className="w-28"><MiniBar value={p.stability_score} colour={p.stability_score >= 80 ? "#0F766E" : "#C9A227"} /></div></TD>
                  </tr>
                ))}
              </TBody>
            </DataTable>
            <CardBody>
              <Notice>
                Rank spread is measured across {report.per_player[0]?.assessments ?? 0} assessments per player. Players with a
                spread of zero are ranked identically under every assumption tested.
              </Notice>
            </CardBody>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader title="Most stable top performers" subtitle="High ranking AND low movement: the players you can act on with least methodological risk." />
        <CardBody>
          <RankedBars
            data={[...bat.per_player]
              .filter((p) => (p.baseline_rank ?? 999) <= 30)
              .sort((a, z) => z.stability_score - a.stability_score)
              .slice(0, 12)
              .map((p) => ({ name: p.player, value: p.stability_score }))}
            valueLabel="Stability score"
            height={320}
            colour="#0F766E"
          />
        </CardBody>
      </Card>
    </div>
  );
}
