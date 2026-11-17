import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
// Allow the Render free service time to wake for readiness, without holding the
// browser to the platform's maximum duration.
export const maxDuration = 30;

export async function GET() {
  const workerUrl = process.env.WORKER_API_URL?.replace(/\/$/, "");
  const configured = {
    supabase_url: Boolean(process.env.NEXT_PUBLIC_SUPABASE_URL),
    supabase_publishable_key: Boolean(process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY),
    supabase_server_key: Boolean(process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY),
    upload_bucket: Boolean(process.env.SUPABASE_UPLOAD_BUCKET ?? "uploads"),
    artifact_bucket: Boolean(process.env.SUPABASE_ARTIFACT_BUCKET ?? "royal-scout-artifacts"),
    worker_api_url: Boolean(workerUrl),
    worker_shared_secret: Boolean(process.env.WORKER_SHARED_SECRET),
  };
  const uploadsConfigured = configured.supabase_url && configured.supabase_publishable_key &&
    configured.supabase_server_key && configured.upload_bucket && configured.artifact_bucket &&
    configured.worker_api_url && configured.worker_shared_secret;
  const wakeUrl = workerUrl ? `${workerUrl}/health/live` : null;
  if (!workerUrl) {
    return NextResponse.json({ web: "ok", worker: "not_configured", ready: false, uploads_enabled: false,
      configured, wake_url: null, detail: "Set WORKER_API_URL to the deployed Render API.",
      suggestion: "Configure WORKER_API_URL, WORKER_SHARED_SECRET, and Supabase URL/publishable/server keys." });
  }
  try {
    const response = await fetch(`${workerUrl}/health/ready`, {
      cache: "no-store",
      signal: AbortSignal.timeout(24_000),
    });
    const report = await response.json().catch(() => null) as Record<string, any> | null;
    const ready = response.ok && report?.ready === true;
    const worker = ready ? "ok" : response.status === 503 ? "degraded" : "unreachable";
    return NextResponse.json({ web: "ok", worker, ready, uploads_enabled: ready && uploadsConfigured,
      worker_health: report, configured, wake_url: wakeUrl,
      detail: ready ? "Render worker and required Supabase services are ready." :
        typeof report?.checks === "object" ? "Worker is awake but one or more readiness checks failed." : `Worker readiness returned HTTP ${response.status}.`,
      suggestion: ready ? null : "Keep the page open while Render wakes. Retry the connection, or use Wake Backend and then retry." });
  } catch (cause) {
    const timedOut = cause instanceof Error && (cause.name === "TimeoutError" || cause.name === "AbortError");
    return NextResponse.json({ web: "ok", worker: "unreachable", ready: false, uploads_enabled: false,
      configured, wake_url: wakeUrl,
      detail: timedOut ? "The worker did not become ready before the 24-second readiness timeout." :
        `Render worker connection failed (${cause instanceof Error ? cause.name : "network error"}).`,
      suggestion: "Render may be cold-starting or restarting. Use Wake Backend; the panel will keep retrying health checks." });
  }
}
