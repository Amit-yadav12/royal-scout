import "server-only";
import { cache } from "react";
import { cookies } from "next/headers";
import localSnapshot from "@/data/bundle.json";
import { supabaseServerHeaders } from "@/lib/supabase";
import { hasBundle } from "@/lib/bundle";
import type { Bundle } from "@/lib/types";
import type { DatasetOption } from "@/lib/dataset-types";
import { datasetOptionsFrom, resolveDatasetSelection, type SuccessfulDatasetRecord } from "@/lib/dataset-selection";

const ACTIVE_COOKIE = "rs_active_dataset";
const MAX_HISTORY = 50;

type JobRow = {
  id: string;
  project_id: string;
  dataset_id: string;
  dataset_name: string;
  status: string;
  is_fixture: boolean;
  created_at: string;
  finished_at: string | null;
  result: { bundle_object?: string | null } | null;
};

export type DashboardDatasetContext = {
  bundle: Bundle | null;
  datasets: DatasetOption[];
  selectedId: string | null;
  error: string | null;
  embeddedSnapshot: boolean;
};

function serverEnvironment() {
  const supabaseUrl = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL;
  const serverKey = process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY;
  const projectId = process.env.ROYAL_SCOUT_PROJECT_ID ?? "royal-scout";
  if (!supabaseUrl || !serverKey || serverKey.startsWith("sb_publishable_")) return null;
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(projectId)) throw new Error("Project configuration is invalid.");
  return { supabaseUrl: supabaseUrl.replace(/\/$/, ""), projectId, headers: supabaseServerHeaders() };
}

async function listSuccessfulDatasets(): Promise<JobRow[]> {
  const env = serverEnvironment();
  if (!env) throw new Error("Private dataset access is not configured.");
  const makeQuery = (order: string, limit: number) => {
    const query = new URL(`${env.supabaseUrl}/rest/v1/processing_jobs`);
    query.searchParams.set("select", "id,project_id,dataset_id,dataset_name,status,is_fixture,created_at,finished_at,result");
    query.searchParams.set("project_id", `eq.${env.projectId}`);
    query.searchParams.set("status", "eq.succeeded");
    query.searchParams.set("order", order);
    query.searchParams.set("limit", String(limit));
    return query;
  };
  // Keep a bounded recent list for the selector, plus the oldest successful run
  // forever so an initial primary dataset does not disappear from the selector.
  const [recentResponse, primaryResponse] = await Promise.all([
    fetch(makeQuery("finished_at.desc.nullslast,created_at.desc", MAX_HISTORY), { headers: env.headers, cache: "no-store", signal: AbortSignal.timeout(12_000) }),
    fetch(makeQuery("created_at.asc", 1), { headers: env.headers, cache: "no-store", signal: AbortSignal.timeout(12_000) }),
  ]);
  if (!recentResponse.ok || !primaryResponse.ok) throw new Error("Dataset history is temporarily unavailable.");
  const [recentRows, primaryRows]: unknown[] = await Promise.all([recentResponse.json(), primaryResponse.json()]);
  if (!Array.isArray(recentRows) || !Array.isArray(primaryRows)) throw new Error("Dataset history returned an invalid response.");
  const rows = [...recentRows, ...primaryRows];
  const expectedProjectId = process.env.ROYAL_SCOUT_PROJECT_ID ?? "royal-scout";
  return rows.filter((row): row is JobRow => row && typeof row === "object" &&
    row.status === "succeeded" && typeof row.project_id === "string" && row.project_id === expectedProjectId &&
    typeof row.dataset_id === "string" && /^[A-Za-z0-9_-]{1,64}$/.test(row.dataset_id) &&
    typeof row.dataset_name === "string" && row.result && typeof row.result === "object" &&
    typeof row.result.bundle_object === "string" && row.result.bundle_object === `${row.project_id}/${row.dataset_id}/bundle.json`);
}

async function downloadBundle(datasetId: string, rows: JobRow[]): Promise<Bundle | null> {
  const env = serverEnvironment();
  if (!env) return null;
  const row = rows.find((item) => item.dataset_id === datasetId);
  if (!row) return null;
  const bucket = process.env.SUPABASE_ARTIFACT_BUCKET ?? "royal-scout-artifacts";
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(bucket)) throw new Error("Artifact storage is not configured correctly.");
  const objectPath = `${row.project_id}/${row.dataset_id}/bundle.json`;
  const encodedPath = objectPath.split("/").map(encodeURIComponent).join("/");
  const response = await fetch(`${env.supabaseUrl}/storage/v1/object/${encodeURIComponent(bucket)}/${encodedPath}`, {
    headers: env.headers,
    cache: "no-store",
    signal: AbortSignal.timeout(30_000),
  });
  if (!response.ok) throw new Error(response.status === 404 ? "The selected dataset bundle is missing from private storage." : "The selected dataset bundle is temporarily unavailable.");
  const contentLength = Number(response.headers.get("content-length") ?? 0);
  if (contentLength > 100 * 1024 * 1024) throw new Error("The selected dataset bundle exceeds the application size limit.");
  let data: unknown;
  try {
    const reader = response.body?.getReader();
    if (!reader) throw new Error("empty body");
    const chunks: Uint8Array[] = [];
    let total = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > 100 * 1024 * 1024) {
        await reader.cancel();
        throw new Error("The selected dataset bundle exceeds the application size limit.");
      }
      chunks.push(value);
    }
    const bytes = new Uint8Array(total);
    let offset = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, offset);
      offset += chunk.byteLength;
    }
    data = JSON.parse(new TextDecoder().decode(bytes));
  } catch (cause) {
    if (cause instanceof Error && cause.message.includes("size limit")) throw cause;
    throw new Error("The selected dataset bundle is not valid JSON.");
  }
  if (!hasBundle(data as Bundle) || (data as Bundle).meta.dataset_id !== datasetId || (data as Bundle).meta.project_id !== env.projectId) {
    throw new Error("The selected dataset bundle failed validation.");
  }
  return data as Bundle;
}

function localContext(error: string | null = null): DashboardDatasetContext {
  const snapshot = localSnapshot as unknown as Bundle;
  const ready = hasBundle(snapshot);
  const option: DatasetOption = {
    dataset_id: snapshot.meta.dataset_id,
    name: `${snapshot.meta.name} (embedded snapshot)`,
    created_at: snapshot.meta.created_at,
    is_fixture: Boolean(snapshot.meta.is_fixture),
  };
  return { bundle: ready ? snapshot : null, datasets: ready ? [option] : [], selectedId: ready ? option.dataset_id : null, error, embeddedSnapshot: ready };
}

/** Load the explicitly selected successful dataset. Without server storage configuration, serve the versioned public deployment snapshot. */
export const loadDashboardDataset = cache(async (): Promise<DashboardDatasetContext> => {
  const cookieStore = await cookies();
  const selectedCookie = cookieStore.get(ACTIVE_COOKIE)?.value ?? null;
  let env: ReturnType<typeof serverEnvironment>;
  try {
    env = serverEnvironment();
  } catch {
    return process.env.NODE_ENV === "production"
      ? { bundle: null, datasets: [], selectedId: null, error: "Project configuration is invalid.", embeddedSnapshot: false }
      : localContext("Project configuration is invalid.");
  }
  if (!env) {
    return localContext("Live dataset storage is not configured; showing the embedded public snapshot.");
  }

  try {
    const rows = await listSuccessfulDatasets();
    const datasets = datasetOptionsFrom(rows as SuccessfulDatasetRecord[]);
    if (selectedCookie && !/^[A-Za-z0-9_-]{1,64}$/.test(selectedCookie)) {
      return { bundle: null, datasets, selectedId: selectedCookie, error: "The selected dataset identifier is invalid. Choose a dataset from history.", embeddedSnapshot: false };
    }
    const selection = resolveDatasetSelection(selectedCookie, datasets);
    if (selection.error || !selection.selectedId) {
      return { bundle: null, datasets, selectedId: selection.selectedId, error: selection.error ?? "No active dataset is available.", embeddedSnapshot: false };
    }
    const selectedId = selection.selectedId;
    const bundle = await downloadBundle(selectedId, rows);
    return bundle
      ? { bundle, datasets, selectedId, error: null, embeddedSnapshot: false }
      : { bundle: null, datasets, selectedId, error: "The selected dataset bundle is unavailable. No stale snapshot has been substituted.", embeddedSnapshot: false };
  } catch (cause) {
    const error = cause instanceof Error ? cause.message : "Dataset loading failed.";
    return process.env.NODE_ENV === "production"
      ? { bundle: null, datasets: [], selectedId: selectedCookie, error, embeddedSnapshot: false }
      : localContext(error);
  }
});

export async function getSuccessfulDatasetOptions(): Promise<DatasetOption[]> {
  if (!serverEnvironment()) return localContext().datasets;
  const rows = await listSuccessfulDatasets();
  return datasetOptionsFrom(rows as SuccessfulDatasetRecord[]);
}
