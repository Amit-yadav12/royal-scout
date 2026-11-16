import Link from "next/link";
import {
  AlertTriangle, ArrowRight, BarChart3, CircleCheck, Database, FileWarning, Gauge, ListOrdered, ShieldCheck, Users,
} from "lucide-react";
import { bundle, hasBundle, limitations, scopeOptions } from "@/lib/bundle";
import { bytes, dec, num, pct, shortDate } from "@/lib/format";
import { PageHeader } from "@/components/shell";
import { Card, CardBody, CardHeader, KeyValue, Stat } from "@/components/ui/card";
import { Badge, GradeBadge } from "@/components/ui/badge";
import { EmptyState, Notice } from "@/components/ui/empty";
import { MiniBar } from "@/components/charts/bars";
import { DataTable, TBody, TD, TH, THead } from "@/components/ui/table";

export const dynamic = "force-static";

export default function OverviewPage() {
  if (!hasBundle()) {
    return (
      <EmptyState
        tone="warning"
        title="No analytical bundle has been generated"
        description="Import a dataset through Data Ingestion (the worker will analyse it) or run the engine locally: python -m royalscout.cli ingest --paths <files> --publish src/data/bundle.json. Until then this dashboard deliberately shows no figures."
      />
    );
  }
  const b = bundle;
  const counts = b.counts;
  const global = b.leaderboards.global;
  const quality = b.quality;
  const highFindings = quality.findings.filter((f) => f.severity === "high");
  const caps = b.schema.capabilities;
  const coverageChecks = Object.entries(caps).filter(([, v]) => v).length;
  const capsTotal = Object.keys(caps).length;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Overview"
        icon={BarChart3}
        description={`${b.meta.name} · analysed ${shortDate(b.meta.created_at)} · model ${b.meta.model_version}. Every figure below is computed from the ingested records, with its coverage and confidence attached.`}
        actions={
          <>
            <Link href="/top-batters" className="btn">
              <ListOrdered className="h-3.5 w-3.5" /> Top 30 batters
            </Link>
            <Link href="/data-audit" className="btn-primary">
              <ShieldCheck className="h-3.5 w-3.5" /> Audit the data
            </Link>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
        <Stat label="Players" value={num(counts.players)} hint={`${num(counts.batters)} batting · ${num(counts.bowlers)} bowling`} />
        <Stat label="Batting records" value={num(counts.batting_records)} hint={`${num(counts.ball_events)} ball events`} />
        <Stat label="Bowling records" value={num(counts.bowling_records)} hint={`${num(counts.matches)} matches`} />
        <Stat label="Competitions" value={num(counts.competitions)} hint={`${num(counts.seasons)} seasons · ${num(counts.teams)} teams`} />
        <Stat label="Data quality" value={dec(quality.score, 1)} tone={quality.score >= 90 ? "positive" : "warning"} hint={`${quality.findings.length} finding(s) raised`} />
        <Stat label="Capabilities" value={`${coverageChecks}/${capsTotal}`} hint={caps.ball_by_ball ? "ball-by-ball available" : "aggregate data only"} tone={caps.ball_by_ball ? "positive" : "warning"} />
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader
            title="Reliability-adjusted leaders"
            subtitle="Top five in each discipline. The index is a coverage-weighted composite: components the data cannot support are excluded and the coverage is printed beside every score."
            action={
              <div className="flex gap-2">
                <Link href="/top-batters" className="btn">Batters <ArrowRight className="h-3 w-3" /></Link>
                <Link href="/top-bowlers" className="btn">Bowlers <ArrowRight className="h-3 w-3" /></Link>
              </div>
            }
          />
          <CardBody className="grid gap-5 md:grid-cols-2">
            {(["batters", "bowlers"] as const).map((key) => {
              const rows = (global[key] as any[]).slice(0, 5);
              const scoreKey = key === "batters" ? "rabi" : "rabi_bowl";
              return (
                <div key={key}>
                  <p className="section-label mb-2">{key === "batters" ? "Top 30 batters" : "Top 30 bowlers"}</p>
                  {rows.length ? (
                    <ol className="space-y-1.5">
                      {rows.map((r) => (
                        <li key={r.player} className="flex items-center gap-2">
                          <span className="w-4 shrink-0 font-mono text-2xs text-ink-faint">{r.rank}</span>
                          <div className="min-w-0 flex-1">
                            <Link href={`/players/${encodeURIComponent(r.player)}`} className="block truncate text-xs font-medium text-ink hover:text-royal-pink">
                              {r.player}
                            </Link>
                            <p className="truncate text-2xs text-ink-faint">
                              {r.teams?.[0] ?? "—"} · {r.innings} inns ·{" "}
                              {key === "batters" ? `${num(r.runs)} runs @ ${dec(r.strike_rate)} SR` : `${num(r.wickets)} wkts @ ${dec(r.economy)} econ`}
                            </p>
                          </div>
                          <GradeBadge grade={r.grade} />
                          <span className="w-10 shrink-0 text-right font-mono text-xs font-semibold tabular-nums text-ink">
                            {dec(r[scoreKey], 1)}
                          </span>
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <p className="text-xs text-ink-faint">No eligible players in this dataset yet.</p>
                  )}
                  <p className="mt-2 text-2xs text-ink-faint">
                    {key === "batters" ? global.batters_eligible : global.bowlers_eligible} of{" "}
                    {key === "batters" ? global.batters_evaluated : global.bowlers_evaluated} evaluated players clear the ranked
                    thresholds.
                  </p>
                </div>
              );
            })}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Insight panel" subtitle="Generated from the processed records, not templated copy." />
          <CardBody className="space-y-2.5">
            <Insight
              icon={ShieldCheck}
              tone={quality.score >= 90 ? "positive" : "warning"}
              title={`Data quality ${dec(quality.score, 1)}/100`}
              body={
                quality.findings.length
                  ? `${highFindings.length} high-severity finding(s): ${highFindings.map((f) => f.code.replace(/_/g, " ")).slice(0, 3).join(", ") || "none"}.`
                  : "No integrity findings were raised by the audit."
              }
            />
            <Insight
              icon={Gauge}
              tone={caps.ball_by_ball ? "positive" : "warning"}
              title={caps.ball_by_ball ? "Ball-by-ball pressure analysis available" : "Pressure analysis unavailable"}
              body={
                caps.ball_by_ball
                  ? `${num(counts.ball_events)} deliveries were tagged against documented match situations; phase splits are computed from the same events.`
                  : "No delivery-level data was supplied, so match-pressure performance cannot be claimed. Only labelled proxies exist."
              }
            />
            <Insight
              icon={Users}
              tone="info"
              title={`${num(counts.players)} players resolved`}
              body={
                b.schema.players.suggested_merges.length
                  ? `${b.schema.players.suggested_merges.length} name pair(s) need manual merge review — they were not merged automatically.`
                  : "No ambiguous player identities were detected."
              }
            />
            <Insight
              icon={FileWarning}
              tone={b.ingestion.summary.files_failed ? "warning" : "info"}
              title={`${b.ingestion.summary.files_processed} file(s) processed`}
              body={`${b.ingestion.summary.files_unsupported} unsupported · ${b.ingestion.summary.files_failed} failed · ${b.ingestion.summary.duplicate_files} duplicate(s) skipped. Every file has an explicit status.`}
            />
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader title="Dataset" subtitle="Provenance of the bundle in view." />
          <CardBody className="space-y-1">
            <KeyValue label="Dataset ID" value={<span className="font-mono text-2xs">{b.meta.dataset_id}</span>} />
            <KeyValue label="Version" value={`v${b.meta.dataset_version}`} />
            <KeyValue label="Model version" value={b.meta.model_version} mono />
            <KeyValue label="Config fingerprint" value={<span className="font-mono text-2xs">{b.meta.config_fingerprint}</span>} />
            <KeyValue label="Processing time" value={`${b.meta.processing_seconds ?? "—"} s`} mono />
            <KeyValue label="Original uploads" value={bytes(b.ingestion.summary.original_bytes)} mono />
            <KeyValue label="Extracted payload" value={bytes(b.ingestion.summary.extracted_bytes)} mono />
            <KeyValue label="Filter scopes precomputed" value={num(scopeOptions().length)} mono />
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Capability coverage" subtitle="What this dataset actually supports." />
          <CardBody className="space-y-1.5">
            {Object.entries(caps).map(([key, value]) => (
              <div key={key} className="flex items-center justify-between gap-2 text-xs">
                <span className="text-ink-soft">{key.replace(/_/g, " ")}</span>
                {value ? (
                  <Badge tone="positive"><CircleCheck className="h-3 w-3" /> available</Badge>
                ) : (
                  <Badge tone="neutral">unavailable</Badge>
                )}
              </div>
            ))}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Known limitations" subtitle="Disclosed, not hidden." />
          <CardBody className="space-y-2">
            {limitations().length ? (
              limitations().map((l) => (
                <div key={l} className="flex gap-2 text-xs leading-relaxed text-ink-soft">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600" />
                  <span>{l}</span>
                </div>
              ))
            ) : (
              <p className="text-xs text-ink-faint">No limitations recorded for this dataset.</p>
            )}
            <Notice>
              {b.meta.is_fixture
                ? "This bundle is a synthetic fixture. Production rankings remain empty until a genuine dataset is imported."
                : "Scores are population-relative within the selected scope and are not comparable across scopes."}
            </Notice>
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Data completeness by column"
          subtitle="Worst ten audited columns, ranked by missing-value share."
          action={<Link href="/data-audit" className="btn">Full audit <ArrowRight className="h-3 w-3" /></Link>}
        />
        <DataTable>
          <THead>
            <TH>File</TH>
            <TH>Worksheet</TH>
            <TH>Column</TH>
            <TH>Canonical field</TH>
            <TH align="right">Records</TH>
            <TH align="right">Missing</TH>
            <TH align="right">Invalid</TH>
            <TH align="right">Completeness</TH>
            <TH>Status</TH>
          </THead>
          <TBody>
            {[...quality.columns]
              .sort((a, z) => (z.missing_pct ?? 0) - (a.missing_pct ?? 0))
              .slice(0, 10)
              .map((c, i) => (
                <tr key={`${c.file}-${c.column}-${i}`}>
                  <TD className="max-w-[200px] truncate text-ink-soft">{c.file}</TD>
                  <TD className="text-ink-soft">{c.worksheet}</TD>
                  <TD className="font-medium">{c.column}</TD>
                  <TD className="font-mono text-2xs text-ink-soft">{c.canonical_field || "—"}</TD>
                  <TD align="right" mono>{num(c.total_records)}</TD>
                  <TD align="right" mono>{pct(c.missing_pct ?? 0)}</TD>
                  <TD align="right" mono>{num(c.invalid)}</TD>
                  <TD align="right"><div className="w-28"><MiniBar value={100 - (c.missing_pct ?? 0)} /></div></TD>
                  <TD>
                    <Badge tone={c.status === "fail" ? "danger" : c.status === "warn" ? "warning" : "positive"}>
                      {c.status}
                    </Badge>
                  </TD>
                </tr>
              ))}
          </TBody>
        </DataTable>
      </Card>
    </div>
  );
}

function Insight({ icon: Icon, title, body, tone }: { icon: any; title: string; body: string; tone: "positive" | "warning" | "info" }) {
  const ring = tone === "positive" ? "text-emerald-700 bg-emerald-50" : tone === "warning" ? "text-amber-700 bg-amber-50" : "text-sky-700 bg-sky-50";
  return (
    <div className="flex gap-2.5">
      <span className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded ${ring}`}>
        <Icon className="h-3.5 w-3.5" />
      </span>
      <div>
        <p className="text-xs font-semibold text-ink">{title}</p>
        <p className="mt-0.5 text-2xs leading-relaxed text-ink-soft">{body}</p>
      </div>
    </div>
  );
}
