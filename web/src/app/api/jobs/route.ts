import { NextResponse } from "next/server";
import { createServerSupabase, supabaseServerHeaders } from "@/lib/supabase";
import { mayManageIngestion } from "@/lib/staff-access";
import { isSameOriginRequest } from "@/lib/request-security";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 30;

function errorJson(error: string, status: number, stage: string, suggestion: string) {
  return NextResponse.json({ error, stage, suggestion }, { status, headers: { "Cache-Control": "no-store" } });
}

export async function POST(request: Request) {
  if (!isSameOriginRequest(request)) return errorJson("Cross-origin job submissions are not allowed.", 403, "authorisation", "Use the Royal Scout dashboard on its configured domain.");
  const workerUrl = process.env.WORKER_API_URL;
  const workerSecret = process.env.WORKER_SHARED_SECRET;
  if (!workerUrl || !workerSecret) return errorJson("The Render worker is not configured.", 503, "worker readiness", "Set WORKER_API_URL and WORKER_SHARED_SECRET on the web deployment and Render worker.");

  const session = await createServerSupabase();
  if (!session) return errorJson("Supabase authentication is not configured.", 503, "authentication", "Configure the Supabase URL and publishable key.");
  const { data: { user }, error: authError } = await session.auth.getUser();
  if (authError || !user) return errorJson("Sign in before queueing a dataset.", 401, "authentication", "Use an invited staff account.");
  if (!(await mayManageIngestion(session, user.id))) return errorJson("Your current staff role cannot queue datasets.", 403, "staff permission", "Ask a platform administrator to grant analyst or scout access.");

  let body: { project_id?: unknown; dataset_id?: unknown; dataset_name?: unknown; bucket?: unknown; paths?: unknown };
  try { body = await request.json(); }
  catch { return errorJson("Expected JSON job metadata.", 400, "job request", "Retry the upload from the ingestion page."); }
  const projectId = typeof body.project_id === "string" ? body.project_id : "";
  const datasetId = typeof body.dataset_id === "string" ? body.dataset_id : "";
  const datasetName = typeof body.dataset_name === "string" ? body.dataset_name.trim().slice(0, 200) : "";
  const bucket = typeof body.bucket === "string" ? body.bucket : "";
  const paths = Array.isArray(body.paths) && body.paths.every((path): path is string => typeof path === "string") ? body.paths : [];
  const configuredProjectId = process.env.ROYAL_SCOUT_PROJECT_ID ?? "royal-scout";
  const configuredBucket = process.env.SUPABASE_UPLOAD_BUCKET ?? "uploads";
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(configuredProjectId) || projectId !== configuredProjectId ||
      !/^ds_[a-f0-9]{16}$/.test(datasetId) || !datasetName || bucket !== configuredBucket ||
      paths.length < 1 || paths.length > 200 || new Set(paths).size !== paths.length) {
    return errorJson("Invalid project, dataset, name, bucket or uploaded-file references.", 400, "ownership validation", "Re-select the files and request fresh signed upload claims.");
  }
  const prefix = `${projectId}/${datasetId}/`;
  if (paths.some((path) => !path.startsWith(prefix) || path.includes("..") || path.includes("\\") || path.startsWith("/"))) {
    return errorJson("One or more object paths are outside this user's dataset.", 400, "ownership validation", "Select files through Royal Scout so each object receives a dataset-scoped path.");
  }

  const supabaseUrl = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL;
  if (!supabaseUrl) return errorJson("Supabase Storage is not configured.", 503, "storage verification", "Configure the server-side Supabase URL and service key.");
  const baseUrl = supabaseUrl.replace(/\/$/, "");
  try {
    const claimsUrl = new URL(`${baseUrl}/rest/v1/upload_claims`);
    claimsUrl.searchParams.set("select", "storage_object,status,job_id,size_bytes,filename,dataset_name");
    claimsUrl.searchParams.set("created_by", `eq.${user.id}`);
    claimsUrl.searchParams.set("project_id", `eq.${projectId}`);
    claimsUrl.searchParams.set("dataset_id", `eq.${datasetId}`);
    claimsUrl.searchParams.set("dataset_name", `eq.${datasetName}`);
    claimsUrl.searchParams.set("storage_bucket", `eq.${bucket}`);
    claimsUrl.searchParams.set("storage_object", `in.(${paths.map((path) => `"${path}"`).join(",")})`);
    const claimsResponse = await fetch(claimsUrl, { headers: supabaseServerHeaders(), cache: "no-store", signal: AbortSignal.timeout(15_000) });
    const claims: unknown = await claimsResponse.json().catch(() => null);
    if (!claimsResponse.ok || !Array.isArray(claims) || claims.length !== paths.length) {
      return errorJson("Not every source file has a unique claim owned by this account, dataset and bucket.", 403, "upload claim verification", "Re-upload any file without a matching signed claim; do not reuse another user's object.");
    }
    const claimMap = new Map<string, { status: string; job_id: string | null; size_bytes: number; filename: string }>();
    for (const claim of claims as Record<string, unknown>[]) {
      if (typeof claim.storage_object !== "string" || claimMap.has(claim.storage_object) ||
          typeof claim.status !== "string" || !Number.isSafeInteger(Number(claim.size_bytes)) ||
          typeof claim.filename !== "string" || claim.dataset_name !== datasetName) {
        return errorJson("Upload claim metadata is incomplete or duplicated.", 409, "upload claim verification", "Check the upload_claims migration and request fresh signed upload claims.");
      }
      claimMap.set(claim.storage_object, { status: claim.status, job_id: typeof claim.job_id === "string" ? claim.job_id : null,
        size_bytes: Number(claim.size_bytes), filename: claim.filename });
    }
    if (paths.some((path) => !claimMap.has(path))) return errorJson("A source file claim is missing.", 403, "upload claim verification", "Re-upload the missing file so it receives an ownership claim.");

    for (const path of paths) {
      const claim = claimMap.get(path)!;
      if (!["signed", "uploaded", "queued"].includes(claim.status)) {
        return errorJson(`${claim.filename}: upload claim is in the unexpected '${claim.status}' state.`, 409, "upload claim state", "Use a fresh upload; queued objects cannot be reused.");
      }
      const encodedPath = path.split("/").map(encodeURIComponent).join("/");
      const stored = await fetch(`${baseUrl}/storage/v1/object/${encodeURIComponent(bucket)}/${encodedPath}`, {
        method: "HEAD", headers: supabaseServerHeaders(), cache: "no-store", signal: AbortSignal.timeout(20_000),
      });
      if (!stored.ok) return errorJson(`${claim.filename}: Storage did not confirm the uploaded object (HTTP ${stored.status}).`, 409, "Storage object verification", "Wait for the TUS upload to finish, then retry. The object must exist in the configured private bucket.");
      const actualBytes = Number(stored.headers.get("content-length"));
      if (!Number.isSafeInteger(actualBytes) || actualBytes !== claim.size_bytes) {
        return errorJson(`${claim.filename}: uploaded size (${Number.isFinite(actualBytes) ? actualBytes : "unreported"} bytes) does not match the signed size (${claim.size_bytes} bytes).`, 409, "Storage size verification", "Check the TUS final Upload-Offset and retry the file; do not queue a partial upload.");
      }
    }

    // One privileged DB function transitions claims signed -> uploaded -> queued
    // and inserts the Supabase processing_jobs row in a single transaction.
    const sources = paths.map((path) => ({ bucket, path }));
    const queuedResponse = await fetch(`${baseUrl}/rest/v1/rpc/queue_verified_uploads`, {
      method: "POST", headers: supabaseServerHeaders({ Prefer: "return=representation" }),
      body: JSON.stringify({ p_project_id: projectId, p_dataset_id: datasetId, p_dataset_name: datasetName,
        p_bucket: bucket, p_created_by: user.id, p_sources: sources }),
      cache: "no-store", signal: AbortSignal.timeout(20_000),
    });
    const queued: unknown = await queuedResponse.json().catch(() => null);
    if (!queuedResponse.ok || !Array.isArray(queued) || !queued[0] || typeof queued[0] !== "object") {
      return errorJson("Upload ownership was verified, but the atomic Supabase job queue rejected the request.", 503, "queue creation", "Confirm migration 0010_atomic_upload_jobs.sql is applied and the service key can execute queue_verified_uploads.");
    }
    const job = queued[0] as Record<string, unknown>;
    if (typeof job.id !== "string" || typeof job.status !== "string") return errorJson("Supabase returned an invalid queue record.", 502, "queue verification", "Inspect the processing_jobs schema and queue RPC return columns.");
    return NextResponse.json({ ...job, job_id: job.id, dataset_id: datasetId, message: "Verified source files and atomically queued the processing job." }, {
      status: 202, headers: { "Cache-Control": "no-store" },
    });
  } catch (cause) {
    const message = cause instanceof Error ? cause.message : "unknown network or database error";
    return errorJson(`Could not verify the source files or create the Supabase processing job (${message}).`, 502, "queue connection", "Retry after checking Supabase REST/Storage availability and the Render worker readiness.");
  }
}
