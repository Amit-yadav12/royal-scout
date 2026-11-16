import { NextResponse } from "next/server";
import { createServerSupabase, supabaseServerHeaders } from "@/lib/supabase";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const DOWNLOADABLE = new Set([".csv", ".xlsx", ".xls", ".pdf"]);
const trimSlash = (value: string) => value.endsWith("/") ? value.slice(0, -1) : value;

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^job_[a-f0-9]{16}$/.test(id)) {
    return NextResponse.json({ error: "Invalid job identifier." }, { status: 400 });
  }

  const workerUrl = process.env.WORKER_API_URL;
  const secret = process.env.WORKER_SHARED_SECRET;
  const supabaseUrl = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL;
  const serverKey = process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!workerUrl || !secret || !supabaseUrl || !serverKey || serverKey.startsWith("sb_publishable_")) {
    return NextResponse.json({ error: "Private artifact downloads are not configured." }, { status: 503 });
  }

  const sessionClient = await createServerSupabase();
  if (!sessionClient) {
    return NextResponse.json({ error: "Supabase authentication is not configured." }, { status: 503 });
  }
  const { data: authData, error: authError } = await sessionClient.auth.getUser();
  if (authError || !authData.user) {
    return NextResponse.json({ error: "Sign in to download processing artefacts." }, { status: 401 });
  }

  try {
    const response = await fetch(`${workerUrl.replace(/\/$/, "")}/jobs/${encodeURIComponent(id)}`, {
      headers: { "X-Worker-Secret": secret },
      cache: "no-store",
    });
    const job = await response.json();
    if (!response.ok) return NextResponse.json({ error: job.detail ?? job.error ?? "Job not found." }, { status: response.status });
    if (!job || job.created_by !== authData.user.id) {
      return NextResponse.json({ error: "You do not have access to this job." }, { status: 403 });
    }
    if (job.status !== "succeeded") {
      return NextResponse.json({ error: "Processing has not completed yet." }, { status: 409 });
    }

    const bucket = process.env.SUPABASE_ARTIFACT_BUCKET ?? "royal-scout-artifacts";
    const prefix = `${job.project_id}/${job.dataset_id}/`;
    const uploads = Array.isArray(job.result?.uploads) ? job.result.uploads : [];
    const artifacts: { name: string; url: string; expires_in: number }[] = [];

    for (const item of uploads) {
      if (item?.status !== "uploaded" || typeof item.object !== "string") continue;
      const objectPath = item.object;
      const name = objectPath.split("/").pop() ?? "";
      const ext = name.slice(name.lastIndexOf(".")).toLowerCase();
      if (!objectPath.startsWith(prefix) || objectPath.includes("..") || objectPath.includes("\\") || !DOWNLOADABLE.has(ext)) continue;
      const encodedPath = objectPath.split("/").map(encodeURIComponent).join("/");
      const signed = await fetch(`${trimSlash(supabaseUrl)}/storage/v1/object/sign/${encodeURIComponent(bucket)}/${encodedPath}`, {
        method: "POST", headers: supabaseServerHeaders(),
        body: JSON.stringify({ expiresIn: 600, download: name }), cache: "no-store",
      });
      const data = await signed.json().catch(() => null);
      if (!signed.ok || typeof data?.signedURL !== "string") continue;
      const signedUrl = data.signedURL.startsWith("http") ? data.signedURL :
        `${trimSlash(supabaseUrl)}/storage/v1/${data.signedURL.replace(/^\/?(?:storage\/v1\/)?/, "")}`;
      artifacts.push({ name, url: signedUrl, expires_in: 600 });
    }

    return NextResponse.json({ artifacts }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return NextResponse.json(
      { error: "Could not prepare private artifact downloads.", detail: error instanceof Error ? error.message : String(error) },
      { status: 502 },
    );
  }
}
