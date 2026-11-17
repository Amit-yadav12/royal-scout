import { UploadCloud } from "lucide-react";
import { loadDashboardDataset } from "@/lib/server-dataset";
import { hasBundle } from "@/lib/bundle";
import { bytes, num, shortDate } from "@/lib/format";
import { PageHeader } from "@/components/shell";
import { Card, CardBody, CardHeader, Stat } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Notice } from "@/components/ui/empty";
import { DataTable, TBody, TD, TH, THead } from "@/components/ui/table";
import { UploadPanel } from "@/components/upload-panel";
import { createServerSupabase } from "@/lib/supabase";
import { getStaffAccess, type StaffAccess } from "@/lib/staff-access";

export default async function IngestionPage() {
  const [datasetContext, session] = await Promise.all([loadDashboardDataset(), createServerSupabase()]);
  const { data: { user } } = session ? await session.auth.getUser() : { data: { user: null } };
  const access: StaffAccess = user && session
    ? await getStaffAccess(session, user.id)
    : { status: "lookup_failed", role: null, canUpload: false, message: "Your sign-in session could not be verified. Sign in again." };
  const bundle = datasetContext.bundle;
  const ready = hasBundle(bundle);
  const ing = ready ? bundle.ingestion : null;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Data Ingestion"
        icon={UploadCloud}
        description="Upload cricket datasets directly to private Supabase Storage, then follow validation, queueing, processing and publication with source-level provenance."
      />

      <UploadPanel initialAccess={access} />

      {ing && bundle ? (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
            <Stat label="Files seen" value={num(ing.summary.files_seen)} />
            <Stat label="Processed" value={num(ing.summary.files_processed)} tone="positive" />
            <Stat label="Failed" value={num(ing.summary.files_failed)} tone={ing.summary.files_failed ? "warning" : "positive"} />
            <Stat label="Unsupported" value={num(ing.summary.files_unsupported)} />
            <Stat label="Archive entries" value={num(ing.summary.archive_entries)} />
            <Stat label="Rows discovered" value={num(ing.summary.rows_discovered)} />
            <Stat label="Duration" value={`${ing.duration_seconds}s`} />
          </div>

          <Card>
            <CardHeader title="File-by-file processing log" subtitle="Every file that entered the system, with its explicit outcome. Nothing is skipped silently." />
            <DataTable className="max-h-[420px] overflow-y-auto">
              <THead>
                <TH>File</TH>
                <TH>Origin</TH>
                <TH>Kind</TH>
                <TH align="right">Size</TH>
                <TH align="right">Tables</TH>
                <TH align="right">Rows</TH>
                <TH>Record type</TH>
                <TH>Status</TH>
                <TH>Reason</TH>
              </THead>
              <TBody>
                {ing.files.map((f, i) => (
                  <tr key={`${f.path}-${i}`}>
                    <TD className="max-w-[220px] truncate font-medium">{f.display_name}</TD>
                    <TD className="text-2xs text-ink-faint">{f.origin}</TD>
                    <TD className="text-2xs text-ink-soft">{f.kind}</TD>
                    <TD align="right" mono>{bytes(f.size_bytes)}</TD>
                    <TD align="right" mono>{num(f.tables_found)}</TD>
                    <TD align="right" mono>{num(f.rows)}</TD>
                    <TD className="text-2xs text-ink-soft">{(f.record_type ?? "—").replace(/_/g, " ")}</TD>
                    <TD>
                      <Badge tone={f.status === "processed" ? "positive" : f.status === "failed" ? "danger" : f.status === "unsupported" ? "warning" : "neutral"}>
                        {f.status}
                      </Badge>
                    </TD>
                    <TD className="max-w-[320px] truncate text-2xs text-ink-soft" >{f.reason ?? "—"}</TD>
                  </tr>
                ))}
              </TBody>
            </DataTable>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader title="Archive inspection" subtitle="Entries were inspected before extraction. Hostile or unreadable entries are refused by name." />
              <DataTable className="max-h-[360px] overflow-y-auto">
                <THead>
                  <TH>Entry</TH>
                  <TH align="right">Size</TH>
                  <TH align="right">Ratio</TH>
                  <TH>Outcome</TH>
                </THead>
                <TBody>
                  {ing.archive_entries.map((e, i) => (
                    <tr key={`${e.name}-${i}`}>
                      <TD className="max-w-[260px] truncate font-mono text-2xs">{e.name}</TD>
                      <TD align="right" mono>{bytes(e.size_bytes)}</TD>
                      <TD align="right" mono>{e.compressed_size ? `${(e.size_bytes / e.compressed_size).toFixed(1)}×` : "—"}</TD>
                      <TD>
                        {e.reason ? <Badge tone="danger">refused</Badge> : <Badge tone="positive">extracted</Badge>}
                        {e.reason ? <span className="ml-1.5 text-2xs text-ink-soft">{e.reason}</span> : null}
                      </TD>
                    </tr>
                  ))}
                </TBody>
              </DataTable>
            </Card>

            <Card>
              <CardHeader title="Duplicate handling" subtitle="Byte-identical uploads are used once so records are never double counted." />
              <CardBody>
                {ing.duplicates.length ? (
                  <ul className="space-y-1.5 text-2xs">
                    {ing.duplicates.map((d, i) => (
                      <li key={i} className="border-b border-surface-line/60 pb-1.5">
                        <p className="font-medium text-ink">{d.file}</p>
                        <p className="text-ink-soft">duplicate of {d.duplicate_of}</p>
                        <p className="truncate font-mono text-[0.6rem] text-ink-faint">sha256:{d.sha256.slice(0, 40)}…</p>
                      </li>
                    ))}
                  </ul>
                ) : <p className="text-xs text-ink-faint">No duplicate uploads detected.</p>}
                <Notice>
                  Limits in force: {bytes(bundle.meta.config.limits.max_single_file_bytes)} per file,{" "}
                  {num(bundle.meta.config.limits.max_archive_entries)} archive entries,{" "}
                  {num(bundle.meta.config.limits.max_files_per_upload)} files per upload, compression ratio capped at{" "}
                  {bundle.meta.config.limits.max_compression_ratio}:1. All configurable on the worker.
                </Notice>
              </CardBody>
            </Card>
          </div>
        </>
      ) : (
        <Notice tone="warning">No bundle is loaded, so there is no ingestion history to show. Upload a dataset to begin.</Notice>
      )}
    </div>
  );
}
