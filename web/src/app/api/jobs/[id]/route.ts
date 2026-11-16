import { NextResponse } from "next/server";
import { createServerSupabase } from "@/lib/supabase";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^job_[a-f0-9]{16}$/.test(id)) {
    return NextResponse.json({ error: "Invalid job identifier." }, { status: 400 });
  }
  const workerUrl = process.env.WORKER_API_URL;
  const secret = process.env.WORKER_SHARED_SECRET;
  if (!workerUrl || !secret) {
    return NextResponse.json({ error: "Processing worker is not configured." }, { status: 503 });
  }
  const sessionClient = await createServerSupabase();
  if (!sessionClient) {
    return NextResponse.json({ error: "Supabase authentication is not configured." }, { status: 503 });
  }
  const { data: authData, error: authError } = await sessionClient.auth.getUser();
  if (authError || !authData.user) {
    return NextResponse.json({ error: "Sign in to view processing status." }, { status: 401 });
  }
  try {
    const res = await fetch(`${workerUrl.replace(/\/$/, "")}/jobs/${encodeURIComponent(id)}`, {
      headers: { "X-Worker-Secret": secret },
      cache: "no-store",
    });
    const body = await res.json();
    // Fail closed: missing ownership metadata is not permission to view a job.
    if (!body || body.created_by !== authData.user.id) {
      return NextResponse.json({ error: "You do not have access to this job." }, { status: 403 });
    }
    return NextResponse.json(body, { status: res.status, headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return NextResponse.json(
      { error: "Worker unreachable", detail: error instanceof Error ? error.message : String(error) },
      { status: 502 },
    );
  }
}
