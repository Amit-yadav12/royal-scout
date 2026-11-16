import { NextResponse } from "next/server";
import { createServerSupabase } from "@/lib/supabase";

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

  try {
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
    return NextResponse.json({ ...job, job_id: job.id ?? job.job_id, dataset_id: datasetId }, { status: 202 });
  } catch (error) {
    return NextResponse.json({ error: "Could not reach the processing worker.", detail: error instanceof Error ? error.message : String(error) }, { status: 502 });
  }
}
