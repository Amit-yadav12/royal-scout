"use client";

import { useEffect, useRef, useState } from "react";
import { CircleAlert, CircleCheck, Loader2, UploadCloud } from "lucide-react";
import { bytes } from "@/lib/format";
import { Badge } from "./ui/badge";
import { Notice } from "./ui/empty";

interface JobState {
  job_id?: string;
  id?: string;
  dataset_id?: string;
  status?: string;
  stage?: string;
  detail?: string;
  progress?: number;
  error?: string | null;
  logs?: { at: string; stage: string; message: string; progress?: number }[];
  result?: Record<string, unknown>;
  artifacts?: { name: string; url: string; expires_in: number }[];
}

interface SignedFile {
  name: string;
  size: number;
  type: string;
  path: string;
  token: string;
  signed_url: string;
  tus_endpoint: string;
  bucket: string;
}

interface UploadInit {
  project_id: string;
  dataset_id: string;
  dataset_name: string;
  bucket: string;
  files: SignedFile[];
}

const TERMINAL = new Set(["succeeded", "failed", "cancelled"]);

function base64(value: string): string {
  return window.btoa(unescape(encodeURIComponent(value)));
}

function tusRequest(
  method: string,
  url: string,
  headers: Record<string, string>,
  body: Blob | null,
  onProgress?: (loaded: number) => void,
): Promise<{ status: number; location: string | null; offset: number | null; responseText: string }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, url, true);
    for (const [key, value] of Object.entries(headers)) xhr.setRequestHeader(key, value);
    if (onProgress && body) xhr.upload.onprogress = (event) => onProgress(event.loaded);
    xhr.onload = () => {
      const rawOffset = xhr.getResponseHeader("Upload-Offset");
      resolve({
        status: xhr.status,
        location: xhr.getResponseHeader("Location"),
        offset: rawOffset === null ? null : Number(rawOffset),
        responseText: xhr.responseText,
      });
    };
    xhr.onerror = () => reject(new Error("Network error during resumable upload."));
    xhr.onabort = () => reject(new Error("Upload was cancelled."));
    xhr.send(body);
  });
}

async function uploadSignedFile(file: File, signed: SignedFile, onProgress: (loaded: number) => void) {
  const metadata = [
    `bucketName ${base64(signed.bucket)}`,
    `objectName ${base64(signed.path)}`,
    `contentType ${base64(file.type || "application/octet-stream")}`,
    `cacheControl ${base64("3600")}`,
  ].join(",");
  const commonHeaders = {
    "Tus-Resumable": "1.0.0",
    "x-signature": signed.token,
    apikey: process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "",
  };

  const created = await tusRequest("POST", signed.tus_endpoint, {
    ...commonHeaders,
    "Upload-Length": String(file.size),
    "Upload-Metadata": metadata,
  }, null);
  if (created.status !== 201 || !created.location) {
    throw new Error(`${file.name}: could not initialise resumable upload (HTTP ${created.status}) ${created.responseText}`);
  }
  const uploadUrl = new URL(created.location, signed.tus_endpoint).toString();
  const chunkSize = 6 * 1024 * 1024;
  let offset = created.offset ?? 0;
  let retries = 0;
  onProgress(offset);

  while (offset < file.size) {
    const end = Math.min(offset + chunkSize, file.size);
    const chunk = file.slice(offset, end);
    try {
      const result = await tusRequest("PATCH", uploadUrl, {
        ...commonHeaders,
        "Upload-Offset": String(offset),
        "Content-Type": "application/offset+octet-stream",
      }, chunk, (loaded) => onProgress(offset + loaded));
      if (result.status !== 204) {
        throw new Error(`chunk upload failed (HTTP ${result.status}) ${result.responseText}`);
      }
      const nextOffset = result.offset ?? end;
      if (nextOffset <= offset || nextOffset > file.size) {
        throw new Error(`storage returned an invalid upload offset (${nextOffset})`);
      }
      offset = nextOffset;
      retries = 0;
      onProgress(offset);
    } catch (error) {
      retries += 1;
      if (retries > 5) throw new Error(`${file.name}: resumable upload stopped after 5 retries. ${error instanceof Error ? error.message : String(error)}`);
      await new Promise((resolve) => setTimeout(resolve, Math.min(15000, retries * 2000)));
      const status = await tusRequest("HEAD", uploadUrl, commonHeaders, null);
      if (status.status !== 200 || status.offset === null || status.offset < 0 || status.offset > file.size) {
        throw new Error(`${file.name}: could not recover resumable upload position (HTTP ${status.status}).`);
      }
      offset = status.offset;
      onProgress(offset);
    }
  }
  onProgress(file.size);
}

export function UploadPanel() {
  const [files, setFiles] = useState<File[]>([]);
  const [name, setName] = useState("Scouting dataset");
  const [job, setJob] = useState<JobState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [worker, setWorker] = useState<"unknown" | "ok" | "unavailable" | "not_configured">("unknown");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let alive = true;
    fetch("/api/health", { cache: "no-store" })
      .then((r) => r.json())
      .then((d) => {
        if (!alive) return;
        setWorker(d.uploads_enabled && d.worker === "ok" ? "ok" : d.worker === "unreachable" ? "unavailable" : "not_configured");
      })
      .catch(() => alive && setWorker("unavailable"));
    return () => {
      alive = false;
    };
  }, []);

  async function poll(jobId: string) {
    for (let i = 0; i < 600; i += 1) {
      await new Promise((r) => setTimeout(r, 2000));
      try {
        const res = await fetch(`/api/jobs/${encodeURIComponent(jobId)}`, { cache: "no-store" });
        if (!res.ok) {
          setError(`Could not read processing status (HTTP ${res.status}). The job may still be running.`);
          return;
        }
        const data = (await res.json()) as JobState;
        if (data.status === "succeeded") {
          try {
            const artifactResponse = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/artifacts`, { cache: "no-store" });
            if (artifactResponse.ok) {
              const artifactPayload = await artifactResponse.json();
              data.artifacts = Array.isArray(artifactPayload.artifacts) ? artifactPayload.artifacts : [];
            }
          } catch {
            // The job remains successful even if temporary download links cannot be minted.
          }
        }
        setJob(data);
        if (data.status && TERMINAL.has(data.status)) return;
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        return;
      }
    }
    setHint("Status polling reached its time limit. Check the worker job logs; processing may still be running.");
  }

  async function submit() {
    if (!files.length || busy) return;
    setBusy(true);
    setError(null);
    setHint(null);
    setJob(null);
    setUploadProgress(0);

    try {
      // Only small metadata passes through Vercel. The file bytes go directly
      // from the browser to Supabase Storage using short-lived signed URLs.
      const signResponse = await fetch("/api/uploads/sign", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          dataset_name: name || "Scouting dataset",
          files: files.map((file) => ({ name: file.name, size: file.size, type: file.type })),
        }),
      });
      const signPayload = await signResponse.json();
      if (!signResponse.ok) {
        throw new Error(signPayload.error ?? `Could not prepare uploads (HTTP ${signResponse.status})`);
      }
      const init = signPayload as UploadInit;
      if (init.files.length !== files.length) throw new Error("The server returned an incomplete signed-upload list.");

      const total = files.reduce((sum, file) => sum + file.size, 0);
      let completed = 0;
      for (let i = 0; i < files.length; i += 1) {
        const file = files[i];
        const signed = init.files[i];
        await uploadSignedFile(file, signed, (loaded) => {
          const pct = total ? ((completed + loaded) / total) * 100 : 100;
          setUploadProgress(Math.min(100, pct));
        });
        completed += file.size;
        setUploadProgress(total ? (completed / total) * 100 : 100);
      }

      // The worker receives storage references only; it downloads the objects
      // from the private bucket, so neither Vercel nor the browser proxies them.
      const jobResponse = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: init.project_id,
          dataset_id: init.dataset_id,
          dataset_name: init.dataset_name,
          bucket: init.bucket,
          paths: init.files.map((file) => file.path),
        }),
      });
      const jobPayload = await jobResponse.json();
      if (!jobResponse.ok) {
        throw new Error(jobPayload.error ?? `Files uploaded but the worker job could not be queued (HTTP ${jobResponse.status}).`);
      }
      const jobId = String(jobPayload.job_id ?? jobPayload.id ?? "");
      if (!jobId) throw new Error("The worker accepted the upload but returned no job ID.");
      setJob({ ...jobPayload, job_id: jobId, status: "queued", stage: "queued", progress: 0 });
      void poll(jobId);
      setFiles([]);
      if (inputRef.current) inputRef.current.value = "";
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setHint("If the storage upload completed but job creation failed, the uploaded objects remain in the private uploads bucket. Check the worker configuration before retrying.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="rounded-lg border border-surface-line bg-surface shadow-card">
        <header className="border-b border-surface-line px-5 py-3.5">
          <h2 className="text-[0.8125rem] font-semibold tracking-[0.06em] text-ink uppercase">Upload a dataset</h2>
          <p className="mt-1 text-xs text-ink-soft">
            CSV, TSV, Excel, ODS, JSON/JSONL, XML, Parquet, Feather, PDF, DOCX or ZIP/TAR archives with nested folders.
            Large files use resumable 6 MB TUS chunks directly to private storage; Vercel only handles small metadata requests.
          </p>
        </header>
        <div className="space-y-3 px-5 py-4">
          <div
            className="flex flex-col items-center justify-center gap-1.5 rounded border border-dashed border-surface-line bg-surface-muted px-4 py-7 text-center"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              setFiles(Array.from(e.dataTransfer.files));
            }}
          >
            <UploadCloud className="h-6 w-6 text-ink-faint" />
            <p className="text-xs text-ink-soft">Drag files here or choose them below</p>
            <input
              ref={inputRef}
              type="file"
              multiple
              className="mt-1 block w-full max-w-xs text-2xs text-ink-soft file:mr-2 file:rounded file:border-0 file:bg-navy-900 file:px-2.5 file:py-1.5 file:text-2xs file:font-medium file:text-white"
              onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
            />
          </div>

          <label className="block text-2xs font-medium tracking-wide text-ink-faint uppercase">
            Dataset name
            <input className="input mt-1 w-full" value={name} onChange={(e) => setName(e.target.value)} maxLength={200} />
          </label>

          {files.length ? (
            <ul className="max-h-32 space-y-1 overflow-y-auto text-2xs">
              {files.map((f, i) => (
                <li key={`${f.name}-${i}`} className="flex items-center justify-between gap-2 border-b border-surface-line/60 pb-1">
                  <span className="truncate text-ink">{f.name}</span>
                  <span className="shrink-0 font-mono text-ink-faint">{bytes(f.size)}</span>
                </li>
              ))}
            </ul>
          ) : null}

          <div className="flex items-center gap-2">
            <button className="btn-pink" onClick={submit} disabled={busy || !files.length || worker !== "ok"}>
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <UploadCloud className="h-3.5 w-3.5" />}
              {busy ? "Uploading…" : "Upload and process"}
            </button>
            {files.length ? (
              <button className="btn" onClick={() => { setFiles([]); if (inputRef.current) inputRef.current.value = ""; }} disabled={busy}>
                Clear
              </button>
            ) : null}
          </div>

          {busy ? (
            <div className="rounded border border-surface-line bg-surface-muted px-3 py-2.5 text-2xs">
              <div className="flex items-center justify-between gap-2">
                <span className="text-ink-soft">Direct storage upload</span>
                <span className="font-mono tabular-nums">{Math.round(uploadProgress)}%</span>
              </div>
              <div className="mt-1.5 h-1 w-full overflow-hidden rounded bg-surface-deep">
                <div className="h-full bg-royal-pink transition-[width]" style={{ width: `${uploadProgress}%` }} />
              </div>
            </div>
          ) : null}

          {error ? (
            <div className="rounded border border-rose-200 bg-rose-50 px-2.5 py-2 text-2xs text-rose-900">
              <p className="flex items-center gap-1.5 font-medium"><CircleAlert className="h-3.5 w-3.5" /> {error}</p>
              {hint ? <p className="mt-1 text-rose-800">{hint}</p> : null}
            </div>
          ) : null}

          {job ? (
            <div className="rounded border border-surface-line bg-surface-muted px-3 py-2.5 text-2xs">
              <div className="flex items-center gap-2">
                <Badge tone={job.status === "succeeded" ? "positive" : job.status === "failed" ? "danger" : "info"}>
                  {job.status ?? "queued"}
                </Badge>
                <span className="font-mono text-ink-faint">{job.job_id}</span>
                <span className="ml-auto font-mono">{Math.round(job.progress ?? 0)}%</span>
              </div>
              <div className="mt-1.5 h-1 w-full overflow-hidden rounded bg-surface-deep">
                <div className="h-full bg-royal-pink transition-[width]" style={{ width: `${job.progress ?? 0}%` }} />
              </div>
              <p className="mt-1.5 text-ink-soft">{job.stage}{job.detail ? ` · ${job.detail}` : ""}</p>
              {job.error ? <p className="mt-1 text-rose-700">{job.error}</p> : null}
              {job.logs?.length ? (
                <ul className="mt-1.5 max-h-24 space-y-0.5 overflow-y-auto font-mono text-[0.6rem] text-ink-faint">
                  {job.logs.slice(-6).map((l, i) => <li key={i}>[{l.stage}] {l.message}</li>)}
                </ul>
              ) : null}
              {job.status === "succeeded" ? (
                <div className="mt-2 border-t border-surface-line pt-2">
                  <p className="text-ink-soft">
                    Dataset processing is complete. The new bundle is stored under its dataset ID. To publish it as the dashboard snapshot, follow the dataset-publishing steps in docs/DEPLOYMENT.md and redeploy the Vercel project.
                  </p>
                  {job.artifacts?.length ? (
                    <div className="mt-2 space-y-1.5">
                      <p className="font-semibold text-ink">Private processing exports (links expire in 10 minutes)</p>
                      {job.artifacts.map((artifact) => (
                        <a key={`${artifact.name}-${artifact.url}`} href={artifact.url} target="_blank" rel="noreferrer" className="block text-royal-pink underline underline-offset-2">
                          Download {artifact.name}
                        </a>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-1 text-ink-faint">No downloadable CSV, Excel or PDF artefacts were published for this job.</p>
                  )}
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>

      <div className="space-y-3">
        {worker === "ok" ? (
          <Notice tone="success">
            Upload storage and processing worker are configured. Files go directly to the private Supabase Storage bucket; only signed-upload metadata and storage object references pass through Vercel.
          </Notice>
        ) : worker === "not_configured" ? (
          <Notice tone="warning">
            Secure uploads are not configured. Set Supabase URL, publishable key and server-only service-role key, then configure WORKER_API_URL and WORKER_SHARED_SECRET. Sign in is required for uploads.
          </Notice>
        ) : worker === "unavailable" ? (
          <Notice tone="danger">The processing worker is configured but not responding. Uploads are disabled until it is healthy.</Notice>
        ) : (
          <Notice>Checking Supabase storage and processing worker availability…</Notice>
        )}
        <div className="flex items-center gap-1.5 text-2xs text-ink-faint">
          <CircleCheck className="h-3 w-3 text-emerald-600" /> Large file bytes never pass through a Vercel Function.
        </div>
      </div>
    </div>
  );
}
