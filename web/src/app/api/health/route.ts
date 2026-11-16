import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const workerUrl = process.env.WORKER_API_URL;
  const configured = {
    supabase_url: Boolean(process.env.NEXT_PUBLIC_SUPABASE_URL),
    supabase_publishable_key: Boolean(process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY),
    supabase_service_role: Boolean(process.env.SUPABASE_SERVICE_ROLE_KEY),
    worker_api_url: Boolean(workerUrl),
    worker_shared_secret: Boolean(process.env.WORKER_SHARED_SECRET),
    app_url: Boolean(process.env.NEXT_PUBLIC_APP_URL),
  };
  const uploadsConfigured = Boolean(
    process.env.NEXT_PUBLIC_SUPABASE_URL &&
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY &&
    process.env.SUPABASE_SERVICE_ROLE_KEY &&
    (process.env.SUPABASE_UPLOAD_BUCKET ?? "uploads") &&
    workerUrl &&
    process.env.WORKER_SHARED_SECRET,
  );
  if (!workerUrl) {
    return NextResponse.json(
      {
        web: "ok",
        worker: "not_configured",
        uploads_enabled: false,
        configured,
        detail: "WORKER_API_URL is not set: uploads and job status are unavailable in this deployment.",
      },
      { status: 200 },
    );
  }
  try {
    const res = await fetch(`${workerUrl.replace(/\/$/, "")}/health`, { cache: "no-store" });
    const body = await res.json();
    const workerReady = Boolean(res.ok && body.ready);
    return NextResponse.json({
      web: "ok",
      worker: workerReady ? "ok" : "degraded",
      uploads_enabled: workerReady && uploadsConfigured,
      worker_health: body,
      configured,
    }, { status: 200 });
  } catch (error) {
    return NextResponse.json(
      {
        web: "ok",
        worker: "unreachable",
        uploads_enabled: false,
        configured,
        detail: error instanceof Error ? error.message : String(error),
      },
      { status: 200 },
    );
  }
}
