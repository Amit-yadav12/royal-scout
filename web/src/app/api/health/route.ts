import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const workerUrl = process.env.WORKER_API_URL;
  const configured = {
    supabase_url: Boolean(process.env.NEXT_PUBLIC_SUPABASE_URL),
    supabase_publishable_key: Boolean(process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY),
    supabase_server_key: Boolean(process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY),
    worker_api_url: Boolean(workerUrl),
    worker_shared_secret: Boolean(process.env.WORKER_SHARED_SECRET),
    app_url: Boolean(process.env.NEXT_PUBLIC_APP_URL),
  };
  const uploadsConfigured = Boolean(
    process.env.NEXT_PUBLIC_SUPABASE_URL &&
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY &&
    (process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY) &&
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
    const res = await fetch(`${workerUrl.replace(/\/$/, "")}/health/ready`, { cache: "no-store", signal: AbortSignal.timeout(8000) });
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
        detail: "Render worker is unreachable or sleeping; retry after the service starts.",
      },
      { status: 200 },
    );
  }
}
