import { NextResponse } from "next/server";
import { createServerSupabase, supabaseServerHeaders } from "@/lib/supabase";
import { mayManageIngestion } from "@/lib/staff-access";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const workerUrl = process.env.WORKER_API_URL;
  const secret = process.env.WORKER_SHARED_SECRET;
  if (!workerUrl || !secret) {
    return NextResponse.json({ error: "The processing worker is not configured." }, { status: 503 });
  }

  const sessionClient = await createServerSupabase();
  if (!sessionClient) {
    return NextResponse.json({ error: "Supabase authentication is not configured." }, { status: 503 });
  }
  const { data: authData, error: authError } = await sessionClient.auth.getUser();
  if (authError || !authData.user) {
    return NextResponse.json({ error: "Sign in before queueing a dataset." }, { status: 401 });
  }
  if (!(await mayManageIngestion(sessionClient, authData.user.id))) {
    return NextResponse.json({ error: "Only authorised analysts, scouts, or admins may queue datasets." }, { status: 403 });
  }

  let body: {
    project_id?: string;
    dataset_id?: string;
    dataset_name?: string;
    bucket?: string;
    paths?: string[];
  };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Expected JSON job metadata." }, { status: 400 });
  }

  const configuredProjectId = process.env.ROYAL_SCOUT_PROJECT_ID ?? "royal-scout";
  const configuredBucket = process.env.SUPABASE_UPLOAD_BUCKET ?? "uploads";
  const projectId = String(body.project_id ?? "");
  const datasetId = String(body.dataset_id ?? "");
  const datasetName = String(body.dataset_name ?? "Scouting dataset").trim().slice(0, 200) || "Scouting dataset";
  const bucket = String(body.bucket ?? configuredBucket);
  const paths = Array.isArray(body.paths) ? body.paths : [];

  if (!/^[a-zA-Z0-9_-]{1,64}$/.test(configuredProjectId) || projectId !== configuredProjectId ||
      !/^ds_[a-f0-9]{16}$/.test(datasetId) || bucket !== configuredBucket ||
      !paths.length || paths.length > 200 || new Set(paths).size !== paths.length) {
    return NextResponse.json({ error: "Invalid project, dataset, bucket or uploaded-file references." }, { status: 400 });
  }
  const prefix = `${projectId}/${datasetId}/`;
  if (paths.some((path) => typeof path !== "string" || !path.startsWith(prefix) || path.includes("..") || path.includes("\\"))) {
    return NextResponse.json({ error: "One or more storage paths are outside this dataset." }, { status: 400 });
  }

  const supabaseUrl = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL;
  const serverKey = process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!supabaseUrl || !serverKey) {
    return NextResponse.json({ error: "Private upload verification is not configured." }, { status: 503 });
  }

  try {
    const claimsUrl = new URL(`${supabaseUrl.replace(/\/$/, "")}/rest/v1/upload_claims`);
    claimsUrl.searchParams.set("select", "storage_object,status,job_id");
    claimsUrl.searchParams.set("created_by", `eq.${authData.user.id}`);
    claimsUrl.searchParams.set("project_id", `eq.${projectId}`);
    claimsUrl.searchParams.set("dataset_id", `eq.${datasetId}`);
    claimsUrl.searchParams.set("storage_bucket", `eq.${bucket}`);
    claimsUrl.searchParams.set("storage_object", `in.(${paths.map((path) => `"${path}"`).join(",")})`);
    const claimsResponse = await fetch(claimsUrl, { headers: supabaseServerHeaders(), cache: "no-store" });
    const claims = await claimsResponse.json().catch(() => []);
    if (!claimsResponse.ok || !Array.isArray(claims) || claims.length !== paths.length ||
        claims.some((claim) => claim.status === "queued" || !paths.includes(claim.storage_object))) {
      return NextResponse.json({ error: "These storage objects are not all authorised for your account and dataset, or this dataset has already been queued." }, { status: 403 });
    }

    for (const path of paths) {
      const objectUrl = `${supabaseUrl.replace(/\/$/, "")}/storage/v1/object/${encodeURIComponent(bucket)}/${path.split("/").map(encodeURIComponent).join("/")}`;
      const head = await fetch(objectUrl, { method: "HEAD", headers: supabaseServerHeaders(), cache: "no-store" });
      if (!head.ok) {
        return NextResponse.json({ error: "One or more uploads are not present in private Storage yet." }, { status: 409 });
      }
    }

    const markUploadedUrl = new URL(`${supabaseUrl.replace(/\/$/, "")}/rest/v1/upload_claims`);
    markUploadedUrl.searchParams.set("created_by", `eq.${authData.user.id}`);
    markUploadedUrl.searchParams.set("dataset_id", `eq.${datasetId}`);
    markUploadedUrl.searchParams.set("storage_object", `in.(${paths.map((path) => `"${path}"`).join(",")})`);
    const marked = await fetch(markUploadedUrl, { method: "PATCH", headers: supabaseServerHeaders(),
      body: JSON.stringify({ status: "uploaded" }), cache: "no-store" });
    if (!marked.ok) throw new Error("upload claims could not be marked as uploaded");

    const response = await fetch(`${workerUrl.replace(/\/$/, "")}/jobs`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Worker-Secret": secret },
      body: JSON.stringify({
        project_id: projectId,
        dataset_id: datasetId,
        dataset_name: datasetName,
        sources: paths.map((path) => ({ bucket, path })),
        is_fixture: false,
        created_by: authData.user.id,
      }),
      cache: "no-store",
    });
    const payload = await response.json().catch(() => ({ error: `Worker returned HTTP ${response.status}` }));
    if (!response.ok) {
      return NextResponse.json({ error: payload.detail ?? payload.error ?? "Worker rejected the job." }, { status: response.status });
    }
    const job = payload.job ?? payload;
    const markQueued = await fetch(markUploadedUrl, { method: "PATCH", headers: supabaseServerHeaders(),
      body: JSON.stringify({ status: "queued", job_id: job.id ?? job.job_id }), cache: "no-store" });
    if (!markQueued.ok) {
      return NextResponse.json({ error: "The job was created, but upload ownership state could not be confirmed. Contact support with the job ID.", job_id: job.id ?? job.job_id }, { status: 502 });
    }
    return NextResponse.json({ ...job, job_id: job.id ?? job.job_id, dataset_id: datasetId }, { status: 202 });
  } catch (error) {
    return NextResponse.json({ error: "Could not reach the processing worker.", detail: error instanceof Error ? error.message : String(error) }, { status: 502 });
  }
}
