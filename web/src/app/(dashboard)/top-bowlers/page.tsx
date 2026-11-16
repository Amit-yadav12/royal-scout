import { AlertTriangle } from "lucide-react";
import { loadDashboardDataset } from "@/lib/server-dataset";
import { getScope, hasBundle } from "@/lib/bundle";
import { PageHeader } from "@/components/shell";
import { Leaderboard } from "@/components/leaderboard";
import { Card, CardBody, CardHeader, KeyValue } from "@/components/ui/card";
import { EmptyState, Notice } from "@/components/ui/empty";

export default async function TopBattersPage({ searchParams }: { searchParams: Promise<{ scope?: string }> }) {
  const bundle = (await loadDashboardDataset()).bundle;
  const { scope: scopeParam } = await searchParams;
  if (!hasBundle(bundle)) {
    return <EmptyState tone="warning" title="No dataset analysed" description="Import a dataset to generate leaderboards. The engine never displays placeholder players." />;
  }
  const scopeLabel = scopeParam && scopeParam !== "global" ? scopeParam : "All data";
  const scope = getScope(scopeLabel === "All data" ? null : scopeLabel, bundle);
  const rows = scope?.bowlers ?? [];
  const cfg = bundle.meta.config;
  const excluded = bundle.leaderboards.global.bowlers_excluded;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Top 30 Bowlers"
        description={`Ranked by the Reliability-Adjusted Bowling Index — a coverage-weighted composite of performance, consistency, reliability, pressure, role-adjusted output and statistical confidence, with each rate metric shrunk toward the population baseline on limited exposure. Scope: ${scopeLabel}.`}
      />

      {bundle.meta.is_fixture ? (
        <Notice tone="warning">
          Synthetic fixture data. Names and figures are generated for demonstration; production rankings stay empty until real scouting data is imported.
        </Notice>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_280px]">
        <Card>
          <CardHeader
            title="Leaderboard"
            subtitle={`${rows.length} eligible bowler(s) in this scope. Click any final score to see its eligibility and coverage; click a name for the full dossier.`}
          />
          <Leaderboard
            rows={rows}
            discipline="bowling"
            scopeLabel={scopeLabel}
            weights={cfg.bowling_weights as unknown as Record<string, number>}
            defaultSort="rabi_bowl"
            provenance={{
              dataset: bundle.meta.name,
              dataset_id: bundle.meta.dataset_id,
              model_version: bundle.meta.model_version,
              config_fingerprint: bundle.meta.config_fingerprint,
              ranking_method: "Reliability-Adjusted Bowling Index",
              minimum_balls: cfg.eligibility.bowl_min_balls_ranked,
              minimum_innings: cfg.eligibility.bowl_min_innings_ranked,
              generated_at: bundle.meta.created_at,
            }}
          />
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Eligibility rules" subtitle="Applied before any ranking." />
            <CardBody className="space-y-1">
              <KeyValue label="Minimum legal balls" value={`${cfg.eligibility.bowl_min_balls_ranked}`} mono />
              <KeyValue label="Minimum innings" value={`${cfg.eligibility.bowl_min_innings_ranked}`} mono />
              <KeyValue label="Shrinkage prior (k)" value={`${cfg.stats.prior_strength_balls_bat} balls`} mono />
              <KeyValue label="Prior (dismissals)" value={`${cfg.stats.prior_strength_dismissals_bat}`} mono />
              <KeyValue label="Grade A floor" value={`${cfg.stats.grade_a_min_exposure} balls`} mono />
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Excluded players" subtitle="Listed with reasons — never silently dropped." />
            <CardBody>
              {excluded.length ? (
                <ul className="space-y-2">
                  {excluded.slice(0, 12).map((e) => (
                    <li key={e.player} className="text-2xs leading-relaxed">
                      <span className="font-medium text-ink">{e.player}</span>
                      <span className="block text-ink-faint">{e.reason}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-ink-faint">Every evaluated bowler cleared the thresholds.</p>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Reading the table" />
            <CardBody className="space-y-2 text-2xs leading-relaxed text-ink-soft">
              <p><strong className="text-ink">Coverage</strong> is the share of the model&apos;s nominal weight that this dataset supports. Below 100% a component is genuinely unavailable — never estimated.</p>
              <p><strong className="text-ink">Confidence</strong> combines exposure, coverage and bootstrap volatility. A short, brilliant sample cannot earn grade A. A low-economy bowler with few wickets is not automatically ranked above a strike bowler: wicket-taking and containment are separate, visible components.</p>
              <p className="flex gap-1.5"><AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-amber-600" /> Ranks are only comparable inside the selected scope.</p>
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
