import { Brain } from "lucide-react";
import { loadDashboardDataset } from "@/lib/server-dataset";
import { hasBundle } from "@/lib/bundle";
import { dec, num } from "@/lib/format";
import { PageHeader } from "@/components/shell";
import { Card, CardBody, CardHeader, KeyValue, Stat } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState, Notice } from "@/components/ui/empty";
import { DataTable, TBody, TD, TH, THead } from "@/components/ui/table";
import { MiniBar } from "@/components/charts/bars";
import { MetricScatter } from "@/components/charts/scatter";

const STATUS_TONE: Record<string, "positive" | "info" | "warning" | "neutral"> = {
  available: "positive",
  derivable: "info",
  requires_verification: "warning",
  unavailable: "neutral",
};

export default async function StatisticalPage() {
  const bundle = (await loadDashboardDataset()).bundle;
  if (!hasBundle(bundle)) return <EmptyState tone="warning" title="No dataset" description="No bundle has been generated yet." />;
  const b = bundle;
  const cfg = b.meta.config;
  const bat = Object.values(b.batting.players);
  const bowl = Object.values(b.bowling.players);

  const gradeCounts = (rows: { grade?: string }[]) =>
    ["A", "B", "C", "D"].map((g) => ({ grade: g, count: rows.filter((r) => r.grade === g).length }));

  const coverageScatter = bat.map((r) => ({
    name: r.player,
    x: r.exposure_balls ?? null,
    y: r.score_coverage !== null && r.score_coverage !== undefined ? r.score_coverage * 100 : null,
    size: 120,
  }));

  return (
    <div className="space-y-4">
      <PageHeader
        title="Statistical Intelligence"
        icon={Brain}
        description="How the numbers are produced: shrinkage, confidence grading, coverage accounting and — critically — which metrics this dataset can and cannot support."
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Shrinkage prior (batting)" value={`k = ${cfg.stats.prior_strength_balls_bat}`} hint="balls at which the player's own rate carries equal weight with the baseline" />
        <Stat label="Shrinkage prior (bowling)" value={`k = ${cfg.stats.prior_strength_balls_econ}`} hint="applied to economy; averages use wicket exposure" />
        <Stat label="Grade A requires" value={`${cfg.stats.grade_a_min_exposure} balls`} hint={`and ≥ ${Math.round(cfg.stats.grade_a_min_coverage * 100)}% composite coverage`} />
        <Stat label="Bootstrap iterations" value={num(cfg.stats.bootstrap_iterations)} hint={`${Math.round(cfg.stats.ci_level * 100)}% interval, seeded for reproducibility`} />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader title="Confidence grades" subtitle="Exposure and coverage both have to be earned; volatility can demote a grade." />
          <CardBody className="space-y-3">
            {[
              { label: "Batting", rows: bat },
              { label: "Bowling", rows: bowl },
            ].map(({ label, rows }) => (
              <div key={label}>
                <p className="section-label mb-1.5">{label}</p>
                <div className="grid grid-cols-4 gap-1.5">
                  {gradeCounts(rows).map((g) => (
                    <div key={g.grade} className="rounded border border-surface-line bg-surface-muted px-2 py-1.5 text-center">
                      <p className="font-mono text-lg leading-none font-semibold text-ink">{g.count}</p>
                      <p className="mt-0.5 text-2xs text-ink-faint">grade {g.grade}</p>
                    </div>
                  ))}
                </div>
              </div>
            ))}
            <Notice>
              A grade D player is not a bad player — it means the evidence is thin. Treat the score as provisional, not as a
              selection verdict.
            </Notice>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Sample size vs composite coverage" subtitle="Batters, by balls faced and the share of the model the data supports." />
          <CardBody>
            <MetricScatter points={coverageScatter} xLabel="Balls faced" yLabel="Coverage %" height={300} />
            <Notice>
              Coverage is capped by the dataset, not the player: no ball-by-ball data means no pressure component, so every
              player tops out below 100%.
            </Notice>
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Metric availability classification"
          subtitle="A: directly available · B: mathematically derivable · C: requires external verification · D: unavailable in this dataset."
        />
        <DataTable>
          <THead>
            <TH>Metric</TH>
            <TH>Category</TH>
            <TH>Status</TH>
            <TH>Why</TH>
          </THead>
          <TBody>
            {b.metric_availability.map((m) => (
              <tr key={m.metric}>
                <TD className="font-medium">{m.metric}</TD>
                <TD className="text-2xs text-ink-soft">{m.category}</TD>
                <TD>
                  <Badge tone={STATUS_TONE[m.status] ?? "neutral"}>{m.status.replace(/_/g, " ")}</Badge>
                </TD>
                <TD className="max-w-[520px] whitespace-normal text-2xs text-ink-soft">{m.note}</TD>
              </tr>
            ))}
          </TBody>
        </DataTable>
      </Card>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card>
          <CardHeader title="Shrinkage in one picture" />
          <CardBody className="space-y-2 text-xs leading-relaxed text-ink-soft">
            <p className="font-mono text-2xs text-ink">adjusted = own × n/(n+k) + baseline × k/(n+k)</p>
            <p>
              With k = {cfg.stats.prior_strength_balls_bat} balls, a batter who has faced 100 balls keeps{" "}
              <strong className="text-ink">{Math.round((100 / (100 + cfg.stats.prior_strength_balls_bat)) * 100)}%</strong> of
              their own strike rate and inherits the rest from the population; a batter with 1,200 balls keeps{" "}
              <strong className="text-ink">{Math.round((1200 / (1200 + cfg.stats.prior_strength_balls_bat)) * 100)}%</strong>.
            </p>
            <p>
              Different metrics use different denominators on purpose: strike rate and economy use balls, batting average uses
              dismissals, bowling average and strike rate use wickets. Matches, innings and balls are never treated as
              interchangeable exposure.
            </p>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Component weights" subtitle="Normalised over whatever is available." />
          <CardBody className="space-y-1">
            {Object.entries(cfg.batting_weights).map(([k, v]) => (
              <div key={`bat-${k}`}>
                <div className="flex justify-between text-2xs"><span className="text-ink-soft">bat · {k.replace(/_/g, " ")}</span><span className="font-mono">{Math.round(Number(v) * 100)}%</span></div>
                <MiniBar value={Number(v) * 100} showValue={false} colour="#102A54" />
              </div>
            ))}
            {Object.entries(cfg.bowling_weights).map(([k, v]) => (
              <div key={`bowl-${k}`}>
                <div className="flex justify-between text-2xs"><span className="text-ink-soft">bowl · {k.replace(/_/g, " ")}</span><span className="font-mono">{Math.round(Number(v) * 100)}%</span></div>
                <MiniBar value={Number(v) * 100} showValue={false} colour="#E8117F" />
              </div>
            ))}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Model configuration in force" subtitle="Exact values, reproducible via the fingerprint." />
          <CardBody className="space-y-1">
            <KeyValue label="Model version" value={b.meta.model_version} mono />
            <KeyValue label="Fingerprint" value={<span className="font-mono text-2xs">{b.meta.config_fingerprint}</span>} />
            <KeyValue label="Ranked min balls (bat)" value={cfg.eligibility.bat_min_balls_ranked} mono />
            <KeyValue label="Ranked min balls (bowl)" value={cfg.eligibility.bowl_min_balls_ranked} mono />
            <KeyValue label="Min innings" value={cfg.eligibility.bat_min_innings_ranked} mono />
            <KeyValue label="Grade B floor" value={cfg.stats.grade_b_min_exposure} mono />
            <KeyValue label="Grade C floor" value={cfg.stats.grade_c_min_exposure} mono />
            <KeyValue label="Pressure weight (bat)" value={dec(cfg.batting_weights.pressure * 100, 0) + "%"} mono />
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
