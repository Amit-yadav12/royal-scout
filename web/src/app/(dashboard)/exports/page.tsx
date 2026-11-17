import { Download } from "lucide-react";
import { loadDashboardDataset } from "@/lib/server-dataset";
import { hasBundle } from "@/lib/bundle";
import { num, shortDate } from "@/lib/format";
import { PageHeader } from "@/components/shell";
import { Card, CardBody, CardHeader, KeyValue } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState, Notice } from "@/components/ui/empty";

const LIVE_EXPORTS = [
  { href: "/api/export?discipline=batting&limit=30", label: "Top 30 batters (current scope)", format: "CSV" },
  { href: "/api/export?discipline=bowling&limit=30", label: "Top 30 bowlers (current scope)", format: "CSV" },
  { href: "/api/export?discipline=batting&limit=500", label: "Complete batting analytics", format: "CSV" },
  { href: "/api/export?discipline=bowling&limit=500", label: "Complete bowling analytics", format: "CSV" },
];

export default async function ExportsPage() {
  const bundle = (await loadDashboardDataset()).bundle;
  if (!hasBundle(bundle)) return <EmptyState tone="warning" title="No dataset" description="No bundle has been generated yet." />;
  const b = bundle;
  return (
    <div className="space-y-4">
      <PageHeader
        title="Export Center"
        icon={Download}
        description="Every export carries a provenance block: calculation date, dataset and model version, config fingerprint, ranking method, sample-size rules, active scope and the dataset's known limitations."
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Live exports" subtitle="Generated on request from the current bundle, so the file always matches what you see." />
          <CardBody className="space-y-2">
            {LIVE_EXPORTS.map((e) => (
              <a key={e.href} href={e.href} className="flex items-center justify-between gap-3 rounded border border-surface-line px-3 py-2 text-xs hover:border-navy-700/30 hover:bg-surface-muted">
                <span className="font-medium text-ink">{e.label}</span>
                <span className="flex items-center gap-2">
                  <Badge tone="info">{e.format}</Badge>
                  <Download className="h-3.5 w-3.5 text-ink-faint" />
                </span>
              </a>
            ))}
            <Notice>
              The scope selector in the header applies to these links: download a competition- or team-specific leaderboard
              and the file records that scope in its provenance block.
            </Notice>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Provenance of this bundle" subtitle="Reproduce the numbers before trusting them." />
          <CardBody className="space-y-1">
            <KeyValue label="Dataset" value={b.meta.name} />
            <KeyValue label="Dataset version" value={`v${b.meta.dataset_version}`} mono />
            <KeyValue label="Model version" value={b.meta.model_version} mono />
            <KeyValue label="Fingerprint" value={<span className="font-mono text-2xs">{b.meta.config_fingerprint}</span>} />
            <KeyValue label="Analysed" value={shortDate(b.meta.created_at)} />
            <KeyValue label="Ranking method" value="Reliability-Adjusted Index" />
            <KeyValue label="Min balls (bat / bowl)" value={`${b.meta.config.eligibility.bat_min_balls_ranked} / ${b.meta.config.eligibility.bowl_min_balls_ranked}`} mono />
            <KeyValue label="Quality score" value={`${b.quality.score.toFixed(1)}/100`} mono />
            <KeyValue label="Fixture data" value={b.meta.is_fixture ? "yes — synthetic" : "no"} />
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader title="Public read-only access" subtitle="The dashboard and analytical exports are available without an account." />
        <CardBody>
          <Notice>Uploads, processing retries, and private worker artefact downloads require the administrator sign-in. Public CSV exports below are generated from the selected dataset and retain provenance details.</Notice>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="Filtered leaderboard downloads" subtitle="Per-competition, per-season and per-team exports precomputed by the engine." />
        <CardBody>
          <div className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
            {b.leaderboards.scopes.map((s) => (
              <a
                key={s.scope.label}
                href={`/api/export?discipline=batting&limit=30&scope=${encodeURIComponent(s.scope.label)}`}
                className="flex items-center justify-between gap-2 rounded border border-surface-line px-2.5 py-1.5 text-2xs hover:bg-surface-muted"
              >
                <span className="truncate text-ink">{s.scope.type === "global" ? "All data" : s.scope.label}</span>
                <span className="shrink-0 font-mono text-ink-faint">{num(Math.max(s.batters_eligible, s.bowlers_eligible))}</span>
              </a>
            ))}
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
