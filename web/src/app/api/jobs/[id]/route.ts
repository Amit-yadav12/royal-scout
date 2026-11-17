import { NextResponse } from "next/server";
import { createServerSupabase, supabaseServerHeaders } from "@/lib/supabase";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" };

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^job_[a-f0-9]{16}$/.test(id)) {
    return NextResponse.json({ error: "Invalid job identifier." }, { status: 400, headers: NO_STORE });
  }

  const sessionClient = await createServerSupabase();
  if (!sessionClient) {
    return NextResponse.json({ error: "Supabase authentication is not configured." }, { status: 503, headers: NO_STORE });
  }
  const { data: authData, error: authError } = await sessionClient.auth.getUser();
  if (authError || !authData.user) {
    return NextResponse.json({ error: "Sign in to view processing status." }, { status: 401, headers: NO_STORE });
  }

  const supabaseUrl = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL;
  const serverKey = process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!supabaseUrl || !serverKey) {
    return NextResponse.json({ error: "Secure processing status is not configured." }, { status: 503, headers: NO_STORE });
  }

  try {
    const baseUrl = supabaseUrl.replace(/\/$/, "");
    const headers = supabaseServerHeaders({ Accept: "application/json" });
    const jobUrl = new URL(`${baseUrl}/rest/v1/processing_jobs`);
    jobUrl.searchParams.set("select", "id,dataset_id,status,progress,stage,detail,error,created_by,updated_at");
    jobUrl.searchParams.set("id", `eq.${id}`);
    const jobResponse = await fetch(jobUrl, {
      headers, cache: "no-store", signal: AbortSignal.timeout(10_000),
    });
    if (!jobResponse.ok) {
      return NextResponse.json({ error: "Could not read the processing queue." }, { status: 502, headers: NO_STORE });
    }
    const rows: unknown = await jobResponse.json();
    const row = Array.isArray(rows) ? rows[0] as Record<string, unknown> | undefined : undefined;
    if (!row) return NextResponse.json({ error: "Processing job not found." }, { status: 404, headers: NO_STORE });
    if (row.created_by !== authData.user.id) {
      return NextResponse.json({ error: "You do not have access to this job." }, { status: 403, headers: NO_STORE });
    }

    const logsUrl = new URL(`${baseUrl}/rest/v1/processing_logs`);
    logsUrl.searchParams.set("select", "stage,message,progress,created_at");
    logsUrl.searchParams.set("job_id", `eq.${id}`);
    logsUrl.searchParams.set("order", "created_at.asc");
    logsUrl.searchParams.set("limit", "200");
    const logsResponse = await fetch(logsUrl, {
      headers, cache: "no-store", signal: AbortSignal.timeout(10_000),
    });
    const rawLogs: unknown = logsResponse.ok ? await logsResponse.json().catch(() => []) : [];
    const logs = Array.isArray(rawLogs) ? rawLogs.flatMap((item) => {
      if (!item || typeof item !== "object") return [];
      const log = item as Record<string, unknown>;
      return [{
        at: typeof log.created_at === "string" ? log.created_at : "",
        stage: typeof log.stage === "string" ? log.stage : "",
        message: typeof log.message === "string" ? log.message : "",
        progress: Number.isFinite(Number(log.progress)) ? Number(log.progress) : undefined,
      }];
    }) : [];

    const updatedAt = typeof row.updated_at === "string" ? row.updated_at : null;
    const updatedAtMs = updatedAt ? Date.parse(updatedAt) : Number.NaN;
    const heartbeatStale = row.status === "running" && Number.isFinite(updatedAtMs) &&
      Date.now() - updatedAtMs > 5 * 60_000;

    return NextResponse.json({
      id, job_id: id,
      dataset_id: typeof row.dataset_id === "string" ? row.dataset_id : undefined,
      status: typeof row.status === "string" ? row.status : "unknown",
      progress: Number.isFinite(Number(row.progress)) ? Number(row.progress) : 0,
      stage: typeof row.stage === "string" ? row.stage : "unknown",
      detail: typeof row.detail === "string" ? row.detail : "",
      error: typeof row.error === "string" ? row.error : null,
      updated_at: updatedAt,
      heartbeat_stale: heartbeatStale,
      logs,
    }, { headers: NO_STORE });
  } catch (error) {
    return NextResponse.json({
      error: "Could not read processing status from Supabase.",
      detail: error instanceof Error ? error.message : String(error),
    }, { status: 502, headers: NO_STORE });
  }
}
