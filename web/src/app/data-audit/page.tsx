import { ShieldAlert } from "lucide-react";
import { bundle, hasBundle } from "@/lib/bundle";
import { num, pct } from "@/lib/format";
import { PageHeader } from "@/components/shell";
import { Card, CardBody, CardHeader, KeyValue, Stat } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState, Notice } from "@/components/ui/empty";
import { ColumnAuditTable } from "@/components/column-audit";
import { MiniBar } from "@/components/charts/bars";

export default function DataAuditPage() {
  if (!hasBundle()) return <EmptyState tone="warning" title="No dataset" description="No bundle has been generated yet." />;
  const q = bundle.quality;
  const s = q.summary;
  const bySeverity = (sev: string) => q.findings.filter((f) => f.severity === sev);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Data Audit"
        icon={ShieldAlert}
        description="Column-level completeness, cricket-specific rule validation, duplicate detection and player-identity review. The quality score is a weighted composite of the five components below."
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
        <Stat label="Quality score" value={q.score.toFixed(1)} tone={q.score >= 90 ? "positive" : "warning"} hint="of 100" />
        <Stat label="Missing cells" value={pct(s.missing_pct ?? 0)} hint={`${num(s.missing_cells)} of ${num(s.total_cells)}`} />
        <Stat label="Invalid cells" value={num(s.invalid_cells)} tone={s.invalid_cells ? "warning" : "positive"} />
        <Stat label="Columns failed" value={num(s.columns_failed)} tone={s.columns_failed ? "warning" : "positive"} />
        <Stat label="High findings" value={num(bySeverity("high").length)} tone={bySeverity("high").length ? "warning" : "positive"} />
        <Stat label="Player identity flags" value={num((bundle.schema.players.suggested_merges?.length ?? 0) + (bundle.schema.players.identity_conflicts?.length ?? 0))} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader title="Score components" subtitle="Each component is measured independently; the score is the weighted sum." />
          <CardBody className="space-y-2.5">
            {Object.entries(q.components).map(([k, v]) => (
              <div key={k}>
                <div className="mb-0.5 flex items-baseline justify-between">
                  <span className="text-xs text-ink-soft">{k.replace(/_/g, " ")}</span>
                  <span className="font-mono text-xs tabular-nums text-ink">{v.toFixed(1)}</span>
                </div>
                <MiniBar value={v} colour={v >= 90 ? "#0F766E" : v >= 70 ? "#1B4B8F" : "#C9A227"} />
              </div>
            ))}
            <div className="mt-2 space-y-0.5 border-t border-surface-line pt-2">
              <KeyValue label="Tables profiled" value={num(s.tables_profiled)} mono />
              <KeyValue label="Columns audited" value={num(s.columns_audited)} mono />
              <KeyValue label="Derived values" value={num(s.derivations)} mono />
              <KeyValue label="Unmapped tables" value={num(s.unmapped_tables)} mono />
            </div>
          </CardBody>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader title="Findings" subtitle="Cricket-aware validation with the impact of each issue stated in plain language." />
          <CardBody>
            {q.findings.length ? (
              <ul className="space-y-2">
                {q.findings.map((f) => (
                  <li key={f.code} className="rounded border border-surface-line bg-surface-muted/60 px-3 py-2">
                    <div className="flex items-center gap-2">
                      <Badge tone={f.severity === "high" ? "danger" : f.severity === "medium" ? "warning" : "neutral"}>
                        {f.severity}
                      </Badge>
                      <span className="font-mono text-2xs text-ink-faint">{f.code}</span>
                      <span className="ml-auto font-mono text-2xs text-ink-faint">{f.count} occurrence(s)</span>
                    </div>
                    <p className="mt-1 text-xs leading-relaxed text-ink">{f.message}</p>
                    <p className="text-2xs text-ink-soft"><strong className="font-medium">Impact:</strong> {f.impact}</p>
                    {f.sample.length ? (
                      <ul className="mt-1 space-y-0.5">
                        {f.sample.slice(0, 3).map((sm, i) => (
                          <li key={i} className="truncate font-mono text-[0.6rem] text-ink-faint">· {sm}</li>
                        ))}
                      </ul>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : <p className="text-xs text-ink-faint">No integrity findings were raised.</p>}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Column audit"
          subtitle="File | Worksheet | Column | Total records | Missing | Invalid | Duplicate | Status. Sort and filter to find the weak points."
        />
        <ColumnAuditTable columns={q.columns} />
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Player identity review" subtitle="Fuzzy name matches are suggestions only — nothing is merged without a human decision." />
          <CardBody>
            {(bundle.schema.players.suggested_merges?.length ?? 0) ? (
              <ul className="space-y-1.5 text-xs">
                {bundle.schema.players.suggested_merges.slice(0, 12).map((s2, i) => (
                  <li key={i} className="flex items-center justify-between gap-2 border-b border-surface-line/60 pb-1">
                    <span className="text-ink">{s2.a} <span className="text-ink-faint">↔</span> {s2.b}</span>
                    <span className="flex shrink-0 items-center gap-1.5">
                      <Badge tone={s2.shared_team ? "warning" : "neutral"}>sim {s2.similarity.toFixed(3)}</Badge>
                      {s2.shared_team ? <Badge tone="info">same team</Badge> : null}
                    </span>
                  </li>
                ))}
              </ul>
            ) : <p className="text-xs text-ink-faint">No ambiguous player identities detected.</p>}
            {(bundle.schema.players.identity_conflicts?.length ?? 0) ? (
              <Notice tone="warning">
                {bundle.schema.players.identity_conflicts.length} player(s) map to more than one team — team filters may split their record.
              </Notice>
            ) : null}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Current-dataset validation notes" subtitle="Every value the engine refused to guess." />
          <CardBody>
            <ul className="space-y-1.5 text-2xs leading-relaxed text-ink-soft">
              {bundle.meta.limitations.length ? bundle.meta.limitations.map((l) => <li key={l}>· {l}</li>) : <li>No limitations recorded.</li>}
            </ul>
            <Notice>
              A failing column never removes a player from the analysis: affected values are treated as missing, flagged on
              the record, and the confidence score absorbs the uncertainty.
            </Notice>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
