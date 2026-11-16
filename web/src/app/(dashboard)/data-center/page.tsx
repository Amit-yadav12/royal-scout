import Link from "next/link";
import { loadDashboardDataset } from "@/lib/server-dataset";
import { Database, Download, FileArchive, FileSpreadsheet } from "lucide-react";
import { hasBundle, scopeOptions } from "@/lib/bundle";
import { bytes, num, shortDate } from "@/lib/format";
import { PageHeader } from "@/components/shell";
import { Card, CardBody, CardHeader, KeyValue, Stat } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EmptyState, Notice } from "@/components/ui/empty";
import { DataTable, TBody, TD, TH, THead } from "@/components/ui/table";

export default async function DataCenterPage() {
  const datasetContext = await loadDashboardDataset();
  const { bundle, datasets, selectedId } = datasetContext;
  if (!hasBundle(bundle)) return <EmptyState tone="warning" title="No active dataset" description={datasetContext.error ?? "No successfully processed dataset is available."} />;
  const b = bundle;
  const ing = b.ingestion;
  const tables = b.schema.tables;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Data Center"
        icon={Database}
        description="Dataset versions, original uploads, cryptographic hashes, detected tables and the derived artefacts. Originals are preserved untouched until an operator explicitly deletes them."
      />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Stat label="Uploaded files" value={num(ing.summary.files_seen)} hint={`${bytes(ing.summary.original_bytes)} original`} />
        <Stat label="Extracted files" value={num(ing.summary.files_processed)} hint={`${bytes(ing.summary.extracted_bytes)} extracted`} />
        <Stat label="Archives" value={num(ing.summary.archives)} hint={`${num(ing.summary.archive_entries)} entries inspected`} />
        <Stat label="Tables detected" value={num(ing.summary.tables_detected)} hint={`${num(ing.summary.rows_discovered)} rows discovered`} />
        <Stat label="Duplicates skipped" value={num(ing.summary.duplicate_files)} tone="warning" hint="byte-identical content is never counted twice" />
        <Stat label="Filter scopes" value={num(scopeOptions(bundle).length)} hint="precomputed for instant filtering" />
      </div>

      <Card>
        <CardHeader title="Processed dataset history" subtitle="Only completed jobs with a published analytical bundle are selectable. Switching the active dataset is applied across analytics and exports without rebuilding the web app." />
        <DataTable>
          <THead>
            <TH>Dataset</TH>
            <TH>Dataset ID</TH>
            <TH>Processed</TH>
            <TH>Status</TH>
          </THead>
          <TBody>
            {datasets.map((dataset) => (
              <tr key={dataset.dataset_id}>
                <TD className="font-medium">{dataset.name}{dataset.is_fixture ? " · test fixture" : ""}</TD>
                <TD className="font-mono text-2xs">{dataset.dataset_id}</TD>
                <TD>{shortDate(dataset.created_at)}</TD>
                <TD>{dataset.dataset_id === selectedId ? <Badge tone="positive">active</Badge> : <Badge tone="neutral">processed</Badge>}</TD>
              </tr>
            ))}
          </TBody>
        </DataTable>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader title="Active dataset" subtitle="Immutable provenance for this bundle." />
          <CardBody className="space-y-1">
            <KeyValue label="Name" value={b.meta.name} />
            <KeyValue label="Project" value={<span className="font-mono text-2xs">{b.meta.project_id}</span>} />
            <KeyValue label="Dataset ID" value={<span className="font-mono text-2xs">{b.meta.dataset_id}</span>} />
            <KeyValue label="Version" value={`v${b.meta.dataset_version}`} />
            <KeyValue label="Analysed" value={shortDate(b.meta.created_at)} />
            <KeyValue label="Model" value={b.meta.model_version} mono />
            <KeyValue label="Config fingerprint" value={<span className="font-mono text-2xs">{b.meta.config_fingerprint}</span>} />
            <KeyValue label="Processing duration" value={`${b.meta.processing_seconds} s`} mono />
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Original files" subtitle="Sorted by size. SHA-256 lets you prove which file produced which record." />
          <CardBody>
            <ul className="space-y-1.5">
              {ing.originals.slice(0, 8).map((o) => (
                <li key={o.sha256} className="border-b border-surface-line/60 pb-1.5 text-2xs last:border-0">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate font-medium text-ink">{o.name}</span>
                    <span className="shrink-0 font-mono text-ink-faint">{bytes(o.bytes)}</span>
                  </div>
                  <span className="block truncate font-mono text-[0.6rem] text-ink-faint">sha256:{o.sha256.slice(0, 32)}…</span>
                </li>
              ))}
              {!ing.originals.length ? <p className="text-xs text-ink-faint">No originals recorded.</p> : null}
            </ul>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Artefacts" subtitle="Everything the engine wrote for this dataset." />
          <CardBody className="space-y-2 text-xs">
            <Artefact icon={FileSpreadsheet} label="bundle.json" detail="Full analytical payload consumed by this dashboard" />
            <Artefact icon={FileSpreadsheet} label="batting_records.parquet / bowling_records.parquet" detail="Canonical cleaned records with lineage" />
            <Artefact icon={FileSpreadsheet} label="ball_events.parquet" detail={b.schema.capabilities.ball_by_ball ? "Delivery-level events" : "Not produced — no ball-by-ball data"} />
            <Artefact icon={FileArchive} label="Top 30 CSV · Excel workbook · PDF report" detail="Generated at analysis time; also downloadable live from Export Center" />
            <Link href="/exports" className="btn mt-1 w-full justify-center"><Download className="h-3.5 w-3.5" /> Open Export Center</Link>
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Detected tables & schema mapping"
          subtitle="Every table the engine found, the record type it inferred, and whether a human needs to confirm the mapping."
        />
        <DataTable>
          <THead>
            <TH>File</TH>
            <TH>Container</TH>
            <TH>Table / sheet</TH>
            <TH align="right">Rows</TH>
            <TH align="right">Columns</TH>
            <TH>Detected type</TH>
            <TH>Confidence</TH>
            <TH>Status</TH>
          </THead>
          <TBody>
            {tables.map((t, i) => {
              const top = t.record_type_scores[0];
              return (
                <tr key={`${t.source_path}-${t.table_name}-${i}`}>
                  <TD className="max-w-[220px] truncate text-ink-soft">{t.source_path}</TD>
                  <TD className="text-ink-faint">{t.container}</TD>
                  <TD className="font-medium">{t.table_name}</TD>
                  <TD align="right" mono>{num(t.row_count)}</TD>
                  <TD align="right" mono>{t.column_count}</TD>
                  <TD><Badge tone={t.record_type === "unknown" ? "warning" : "info"}>{t.record_type.replace(/_/g, " ")}</Badge></TD>
                  <TD align="right" mono>{top ? top.score.toFixed(2) : "—"}</TD>
                  <TD>{t.needs_review ? <Badge tone="warning">needs review</Badge> : <Badge tone="positive">mapped</Badge>}</TD>
                </tr>
              );
            })}
          </TBody>
        </DataTable>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Unmapped tables" subtitle="Excluded from analytics and listed here — never silently skipped." />
          <CardBody>
            {b.schema.unmapped_tables.length ? (
              <ul className="space-y-2">
                {b.schema.unmapped_tables.map((u, i) => (
                  <li key={i} className="rounded border border-amber-200 bg-amber-50/60 px-2.5 py-2 text-2xs">
                    <p className="font-medium text-ink">{u.source_path} · {u.table}</p>
                    <p className="text-ink-soft">{u.rows} row(s) · {u.reason}</p>
                    <p className="mt-1 truncate font-mono text-[0.6rem] text-ink-faint">{u.columns.join(", ")}</p>
                  </li>
                ))}
              </ul>
            ) : <p className="text-xs text-ink-faint">Every discovered table was mapped to a cricket record type.</p>}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Derivations & superseded rows" subtitle="Every value the engine had to infer, and every aggregate it dropped to avoid double counting." />
          <CardBody>
            {b.schema.derivations.length ? (
              <ul className="max-h-72 space-y-1.5 overflow-y-auto text-2xs">
                {b.schema.derivations.map((d, i) => (
                  <li key={i} className="border-b border-surface-line/60 pb-1.5">
                    <span className="font-mono text-[0.6rem] tracking-wide text-royal-pinkDark uppercase">{d.kind.replace(/_/g, " ")}</span>
                    <p className="text-ink-soft">{d.player ? `${d.player} — ` : ""}{d.reason}</p>
                  </li>
                ))}
              </ul>
            ) : <p className="text-xs text-ink-faint">No derivations were required: every value came from the source.</p>}
            <Notice>{b.schema.derivations_total} derivation(s) recorded in total.</Notice>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function Artefact({ icon: Icon, label, detail }: { icon: any; label: string; detail: string }) {
  return (
    <div className="flex gap-2">
      <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-faint" />
      <div>
        <p className="font-medium break-all text-ink">{label}</p>
        <p className="text-2xs text-ink-faint">{detail}</p>
      </div>
    </div>
  );
}
