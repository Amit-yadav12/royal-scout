import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";
import { createServerSupabase } from "@/lib/supabase";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_FILES = Number(process.env.RS_MAX_FILES_PER_UPLOAD ?? 200);
const MAX_FILE_BYTES = Number(process.env.RS_MAX_UPLOAD_FILE_BYTES ?? 2 * 1024 ** 3);
const MAX_TOTAL_BYTES = Number(process.env.RS_MAX_UPLOAD_TOTAL_BYTES ?? 10 * 1024 ** 3);
const BUCKET = process.env.SUPABASE_UPLOAD_BUCKET ?? "uploads";

function safeFileName(name: string): string {
  const normalised = name.replace(/\\/g, "/").split("/").pop() ?? "upload";
  const cleaned = normalised.replace(/[^a-zA-Z0-9._ -]/g, "_").trim().replace(/\s+/g, "-").replace(/\.\.+/g, "_");
  return cleaned.replace(/^\.+/, "")?.slice(0, 160) || "upload";
}

export async function POST(request: Request) {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const serviceRole = process.env.SUPABASE_SERVICE_ROLE_KEY;
  const projectId = process.env.ROYAL_SCOUT_PROJECT_ID ?? "royal-scout";

  if (!/^[a-zA-Z0-9_-]{1,64}$/.test(projectId)) {
    return NextResponse.json({ error: "ROYAL_SCOUT_PROJECT_ID must contain only letters, numbers, underscores or hyphens (maximum 64 characters)." }, { status: 500 });
  }
  if (!url || !serviceRole) {
    return NextResponse.json(
      { error: "Secure uploads are not configured.", hint: "Configure Supabase URL and the server-only service-role key." },
      { status: 503 },
    );
  }

  const sessionClient = await createServerSupabase();
  if (!sessionClient) {
    return NextResponse.json({ error: "Supabase authentication is not configured." }, { status: 503 });
  }
  const { data: authData, error: authError } = await sessionClient.auth.getUser();
  if (authError || !authData.user) {
    return NextResponse.json({ error: "Sign in before uploading scouting data." }, { status: 401 });
  }

  let body: { dataset_name?: unknown; files?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Expected JSON upload metadata." }, { status: 400 });
  }

  const datasetName = String(body.dataset_name ?? "Scouting dataset").trim().slice(0, 200) || "Scouting dataset";
  const files = Array.isArray(body.files) ? body.files : [];
  if (!files.length || files.length > MAX_FILES) {
    return NextResponse.json({ error: `Select between 1 and ${MAX_FILES} files.` }, { status: 400 });
  }

  const parsed = files.map((item) => {
    const value = item as { name?: unknown; size?: unknown; type?: unknown };
    return {
      name: safeFileName(String(value.name ?? "upload")),
      size: Number(value.size),
      type: String(value.type ?? "application/octet-stream").slice(0, 120),
    };
  });

  if (parsed.some((f) => !Number.isSafeInteger(f.size) || f.size < 0 || f.size > MAX_FILE_BYTES)) {
    return NextResponse.json({ error: `Each file must be smaller than ${MAX_FILE_BYTES} bytes.` }, { status: 413 });
  }
  const totalBytes = parsed.reduce((sum, file) => sum + file.size, 0);
  if (totalBytes > MAX_TOTAL_BYTES) {
    return NextResponse.json({ error: `The selected files exceed the ${MAX_TOTAL_BYTES}-byte upload batch limit.` }, { status: 413 });
  }

  const datasetId = `ds_${crypto.randomUUID().replace(/-/g, "").slice(0, 16)}`;
  const admin = createClient(url, serviceRole, {
    auth: { autoRefreshToken: false, persistSession: false },
  });

  const signedFiles: { name: string; size: number; type: string; path: string; token: string; signed_url: string; tus_endpoint: string; bucket: string }[] = [];
  try {
    for (const [index, file] of parsed.entries()) {
      const objectName = `${projectId}/${datasetId}/${String(index + 1).padStart(3, "0")}-${crypto.randomUUID().slice(0, 8)}-${file.name}`;
      const { data, error } = await admin.storage.from(BUCKET).createSignedUploadUrl(objectName, { upsert: false });
      if (error || !data) {
        throw new Error(error?.message ?? `Could not sign upload for ${file.name}`);
      }
      const supabaseOrigin = new URL(url);
      const directHost = supabaseOrigin.hostname.endsWith(".supabase.co")
        ? `${supabaseOrigin.hostname.split(".")[0]}.storage.supabase.co`
        : supabaseOrigin.host;
      const tusEndpoint = `${supabaseOrigin.protocol}//${directHost}/storage/v1/upload/resumable`;
      signedFiles.push({ ...file, path: objectName, token: data.token, signed_url: data.signedUrl, tus_endpoint: tusEndpoint, bucket: BUCKET });
    }
  } catch (error) {
    return NextResponse.json(
      { error: "Could not create secure upload URLs.", detail: error instanceof Error ? error.message : String(error), hint: `Confirm that the private '${BUCKET}' bucket exists and that its configured file-size limit permits these uploads.` },
      { status: 502 },
    );
  }

  return NextResponse.json({
    project_id: projectId,
    dataset_id: datasetId,
    dataset_name: datasetName,
    bucket: BUCKET,
    created_by: authData.user.id,
    files: signedFiles,
    total_bytes: totalBytes,
  });
}
