import { NextResponse } from "next/server";
import { createServerSupabase } from "@/lib/supabase";
import { getStaffAccess } from "@/lib/staff-access";
import { isSameOriginRequest } from "@/lib/request-security";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  if (!isSameOriginRequest(request)) return NextResponse.json({ error: "Cross-origin job retries are not allowed." }, { status: 403 });
  const { id } = await params;
  if (!/^job_[a-f0-9]{16}$/.test(id)) {
    return NextResponse.json({ error: "Invalid job identifier." }, { status: 400 });
  }
  const session = await createServerSupabase();
  if (!session) return NextResponse.json({ error: "Supabase authentication is not configured." }, { status: 503 });
  const { data, error } = await session.auth.getUser();
  if (error || !data.user) return NextResponse.json({ error: "Sign in to retry processing." }, { status: 401 });
  const access = await getStaffAccess(session, data.user.id);
  if (access.status !== "verified" || !access.canUpload) {
    return NextResponse.json({ error: access.message ?? "Only the platform administrator may retry processing.", access_status: access.status }, { status: 403 });
  }
  const workerUrl = process.env.WORKER_API_URL;
  const secret = process.env.WORKER_SHARED_SECRET;
  if (!workerUrl || !secret) return NextResponse.json({ error: "Processing worker is not configured." }, { status: 503 });

  try {
    const base = workerUrl.replace(/\/$/, "");
    const headers = { "X-Worker-Secret": secret };
    const currentResponse = await fetch(`${base}/jobs/${encodeURIComponent(id)}`, { headers, cache: "no-store" });
    const current = await currentResponse.json().catch(() => null);
    if (!currentResponse.ok) return NextResponse.json({ error: "Job status is unavailable." }, { status: currentResponse.status });
    if (current?.created_by !== data.user.id) return NextResponse.json({ error: "You do not have access to this job." }, { status: 403 });
    if (current.status === "running") return NextResponse.json({ error: "This job is already running." }, { status: 409 });
    if (Number(current.attempts) >= Number(current.max_attempts)) return NextResponse.json({ error: "This job has reached its retry limit." }, { status: 409 });

    const response = await fetch(`${base}/jobs/${encodeURIComponent(id)}/retry`, {
      method: "POST", headers, cache: "no-store",
    });
    const result = await response.json().catch(() => null);
    if (!response.ok) return NextResponse.json({ error: result?.detail ?? "The worker could not retry this job." }, { status: response.status });
    return NextResponse.json(result?.job ?? result, { status: 202, headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ error: "The processing worker is unreachable or sleeping." }, { status: 502 });
  }
}
