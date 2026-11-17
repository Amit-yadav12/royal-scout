"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { CircleAlert, CircleCheck, Loader2, Trash2, UploadCloud, X } from "lucide-react";
import { bytes } from "@/lib/format";
import { Badge } from "./ui/badge";
import { Notice } from "./ui/empty";
import type { StaffAccess, StaffRole } from "@/lib/staff-access";
import { WORKER_AUTO_RETRIES, WORKER_HEALTH_TIMEOUT_MS, workerHealthState, workerRetryDelay } from "@/lib/worker-health";
import { ACCEPTED_UPLOAD_TYPES, validateUploadFiles } from "@/lib/upload-validation";

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
const STAFF_ROLES = new Set(["viewer", "admin"]);

function base64(value: string): string {
  return window.btoa(unescape(encodeURIComponent(value)));
}

function tusRequest(
  method: string,
  url: string,
  headers: Record<string, string>,
  body: Blob | null,
  onProgress?: (loaded: number) => void,
  signal?: AbortSignal,
): Promise<{ status: number; location: string | null; offset: number | null; responseText: string }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const cleanup = () => signal?.removeEventListener("abort", abort);
    const abort = () => xhr.abort();
    if (signal?.aborted) { reject(new Error("Upload was cancelled.")); return; }
    signal?.addEventListener("abort", abort, { once: true });
    xhr.open(method, url, true);
    for (const [key, value] of Object.entries(headers)) xhr.setRequestHeader(key, value);
    if (onProgress && body) xhr.upload.onprogress = (event) => onProgress(event.loaded);
    xhr.onload = () => {
      cleanup();
      const rawOffset = xhr.getResponseHeader("Upload-Offset");
      resolve({ status: xhr.status, location: xhr.getResponseHeader("Location"),
        offset: rawOffset === null ? null : Number(rawOffset), responseText: xhr.responseText });
    };
    xhr.onerror = () => { cleanup(); reject(new Error("Network error during resumable upload.")); };
    xhr.onabort = () => { cleanup(); reject(new Error("Upload was cancelled.")); };
    xhr.send(body);
  });
}

async function uploadSignedFile(file: File, signed: SignedFile, onProgress: (loaded: number) => void, signal: AbortSignal) {
  const metadata = [
    `bucketName ${base64(signed.bucket)}`,
    `objectName ${base64(signed.path)}`,
    `contentType ${base64(file.type || "application/octet-stream")}`,
    `cacheControl ${base64("3600")}`,
  ].join(",");
  const apiKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "";
  if (!apiKey || !signed.token || !signed.bucket || !signed.path) throw new Error(`${file.name}: signed upload response is incomplete.`);
  const commonHeaders: Record<string, string> = {
    "Tus-Resumable": "1.0.0",
    "x-signature": signed.token,
    apikey: apiKey,
  };
  // Legacy anon keys are JWTs and need the bearer header; new publishable keys
  // are API keys and must only be sent as apikey.
  if (/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(apiKey)) commonHeaders.Authorization = `Bearer ${apiKey}`;

  const created = await tusRequest("POST", signed.tus_endpoint, {
    ...commonHeaders,
    "Upload-Length": String(file.size),
    "Upload-Metadata": metadata,
  }, null, undefined, signal);
  if (created.status !== 201 || !created.location) {
    throw new Error(`${file.name}: could not initialise resumable upload (HTTP ${created.status}) ${created.responseText}`);
  }
  const uploadSession = new URL(created.location, signed.tus_endpoint);
  if (uploadSession.origin !== new URL(signed.tus_endpoint).origin) {
    throw new Error(`${file.name}: storage returned an unexpected resumable-upload host.`);
  }
  const uploadUrl = uploadSession.toString();
  const chunkSize = 6 * 1024 * 1024;
  let offset = created.offset ?? 0;
  if (!Number.isInteger(offset) || offset < 0 || offset > file.size) throw new Error(`${file.name}: storage returned an invalid initial upload offset.`);
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
      }, chunk, (loaded) => onProgress(offset + loaded), signal);
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
      if (signal.aborted) throw new Error(`${file.name}: upload cancelled.`);
      retries += 1;
      if (retries > 5) throw new Error(`${file.name}: resumable upload stopped after 5 retries. ${error instanceof Error ? error.message : String(error)}`);
      await new Promise((resolve) => setTimeout(resolve, Math.min(15000, retries * 2000)));
      const status = await tusRequest("HEAD", uploadUrl, commonHeaders, null, undefined, signal);
      if (status.status !== 200 || status.offset === null || status.offset < 0 || status.offset > file.size) {
        throw new Error(`${file.name}: could not recover resumable upload position (HTTP ${status.status}).`);
      }
      offset = status.offset;
      onProgress(offset);
    }
  }
  const finalStatus = await tusRequest("HEAD", uploadUrl, commonHeaders, null, undefined, signal);
  if (finalStatus.status !== 200 || finalStatus.offset !== file.size) {
    throw new Error(`${file.name}: final TUS verification failed (HTTP ${finalStatus.status}, offset ${finalStatus.offset ?? "unknown"}, expected ${file.size}).`);
  }
  onProgress(file.size);
}

export function UploadPanel({ initialAccess }: { initialAccess: StaffAccess }) {
  const router = useRouter();
  const [files, setFiles] = useState<File[]>([]);
  const [name, setName] = useState("Scouting dataset");
  const [job, setJob] = useState<JobState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [access, setAccess] = useState<StaffAccess>(initialAccess);
  const [refreshingAccess, setRefreshingAccess] = useState(false);
  const [accessRefreshError, setAccessRefreshError] = useState<string | null>(null);
  const [worker, setWorker] = useState<"unknown" | "ok" | "unavailable" | "not_configured">("unknown");
  const [workerDetail, setWorkerDetail] = useState("Checking the Render worker…");
  const [workerSuggestion, setWorkerSuggestion] = useState<string | null>(null);
  const [wakeUrl, setWakeUrl] = useState<string | null>(null);
  const [checkingWorker, setCheckingWorker] = useState(false);
  const [wakingWorker, setWakingWorker] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const uploadAbortRef = useRef<AbortController | null>(null);
  const healthAbortRef = useRef<AbortController | null>(null);
  const healthLockRef = useRef(false);
  const aliveRef = useRef(true);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refreshAccess = useCallback(async () => {
    setRefreshingAccess(true);
    setAccessRefreshError(null);
    try {
      const response = await fetch("/api/staff/access", { cache: "no-store", credentials: "same-origin" });
      const payload: unknown = await response.json().catch(() => null);
      if (payload && typeof payload === "object") {
        const value = payload as Record<string, unknown>;
        if (value.status === "verified" && typeof value.role === "string" && STAFF_ROLES.has(value.role)) {
          const role = value.role as StaffRole;
          setAccess({ status: "verified", role, canUpload: role === "admin", message: null });
          return;
        }
        if (["profile_missing", "invalid_role", "lookup_failed"].includes(String(value.status))) {
          setAccess({ status: value.status as StaffAccess["status"], role: null, canUpload: false,
            message: typeof value.message === "string" ? value.message : "Staff permission could not be verified." } as StaffAccess);
          if (!response.ok) setAccessRefreshError(typeof value.message === "string" ? value.message : `Permission check failed (HTTP ${response.status}).`);
          return;
        }
        if (typeof value.message === "string") setAccessRefreshError(value.message);
      }
      throw new Error(`Permission check returned an invalid response (HTTP ${response.status}).`);
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Could not refresh staff permissions.";
      setAccessRefreshError(message);
      setAccess({ status: "lookup_failed", role: null, canUpload: false,
        message: "Access is not currently verified. Upload stays disabled until Supabase confirms your role." });
    } finally {
      setRefreshingAccess(false);
    }
  }, []);

  useEffect(() => {
    void refreshAccess();
    const onFocus = () => void refreshAccess();
    const interval = setInterval(() => void refreshAccess(), 15_000);
    window.addEventListener("focus", onFocus);
    return () => { clearInterval(interval); window.removeEventListener("focus", onFocus); };
  }, [refreshAccess]);

  const checkWorker = useCallback(async (attempts = 1) => {
    if (healthLockRef.current) return;
    healthLockRef.current = true;
    setCheckingWorker(true);
    if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    let lastState: "ok" | "unavailable" | "not_configured" = "unavailable";
    try {
      for (let attempt = 1; attempt <= attempts; attempt += 1) {
        const controller = new AbortController();
        healthAbortRef.current = controller;
        const timeout = setTimeout(() => controller.abort(), WORKER_HEALTH_TIMEOUT_MS);
        try {
          const response = await fetch("/api/health", { cache: "no-store", signal: controller.signal });
          const payload = await response.json().catch(() => null);
          lastState = workerHealthState(payload);
          if (!aliveRef.current) return;
          setWorker(lastState);
          setWorkerDetail(typeof payload?.detail === "string" ? payload.detail : `Worker health returned HTTP ${response.status}.`);
          setWorkerSuggestion(typeof payload?.suggestion === "string" ? payload.suggestion : null);
          setWakeUrl(typeof payload?.wake_url === "string" ? payload.wake_url : null);
          if (lastState === "ok" || lastState === "not_configured") break;
        } catch (cause) {
          lastState = "unavailable";
          if (!aliveRef.current) return;
          setWorker(lastState);
          setWorkerDetail(controller.signal.aborted ? "Worker health check timed out." : "Could not reach the worker health endpoint.");
          setWorkerSuggestion("Render may be sleeping or restarting. Use Wake Backend, then retry the connection.");
          if (attempt === attempts) break;
        } finally {
          clearTimeout(timeout);
          if (healthAbortRef.current === controller) healthAbortRef.current = null;
        }
        if (attempt < attempts) await new Promise((resolve) => setTimeout(resolve, workerRetryDelay(attempt)));
      }
    } finally {
      healthLockRef.current = false;
      if (aliveRef.current) setCheckingWorker(false);
      // Bound each retry burst, then continue checking at a low rate while the
      // panel stays open so a transient cold start never permanently locks UI.
      if (aliveRef.current && lastState === "unavailable") {
        retryTimerRef.current = setTimeout(() => void checkWorker(2), 30_000);
      }
    }
  }, []);

  useEffect(() => {
    aliveRef.current = true;
    void checkWorker(WORKER_AUTO_RETRIES);
    return () => {
      aliveRef.current = false;
      healthAbortRef.current?.abort();
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    };
  }, [checkWorker]);

  async function retryConnection() {
    healthAbortRef.current?.abort();
    while (healthLockRef.current) await new Promise((resolve) => setTimeout(resolve, 50));
    await checkWorker(3);
  }

  async function wakeBackend() {
    if (!wakeUrl || wakingWorker) return;
    setWakingWorker(true);
    setWorkerDetail("Sending a wake request to Render, then checking readiness…");
    // A direct, read-only liveness GET lets the browser hold the cold-start
    // request without consuming a Vercel function timeout. The opaque response
    // is expected; readiness is verified separately through our same-origin API.
    void fetch(wakeUrl, { method: "GET", mode: "no-cors", cache: "no-store" }).catch(() => undefined);
    await new Promise((resolve) => setTimeout(resolve, 1200));
    await retryConnection();
    setWakingWorker(false);
  }

  const role = access.status === "verified" ? access.role : null;
  const canUpload = access.status === "verified" && access.canUpload;

  function addFiles(incoming: File[]) {
    const existing = new Set(files.map((file) => `${file.name}:${file.size}:${file.lastModified}`));
    const combined = [...files, ...incoming.filter((file) => !existing.has(`${file.name}:${file.size}:${file.lastModified}`))];
    const validationError = validateUploadFiles(combined);
    if (validationError) { setError(validationError); return; }
    setError(null);
    setHint(null);
    setFiles(combined);
  }

  function removeFile(index: number) {
    setFiles((current) => current.filter((_, position) => position !== index));
    setError(null);
  }

  function cancelUpload() {
    uploadAbortRef.current?.abort();
  }

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
        if (data.status === "succeeded") {
          if (data.dataset_id) {
            setHint("Processing succeeded. This upload is a separate dataset; the primary source was not replaced or merged. Choose this dataset from the active-dataset selector when you explicitly want to inspect it.");
          }
          router.refresh();
        }
        if (data.status && TERMINAL.has(data.status)) return;
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        return;
      }
    }
    setHint("Status polling reached its time limit. Check the worker job logs; processing may still be running.");
  }

  async function retryJob() {
    const jobId = job?.job_id ?? job?.id;
    if (!jobId || busy) return;
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/retry`, { method: "POST" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error ?? `Retry failed (HTTP ${response.status}).`);
      setJob({ ...payload, job_id: jobId });
      void poll(jobId);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    if (!files.length || busy || worker !== "ok" || !canUpload) return;
    const validationError = validateUploadFiles(files);
    if (validationError) { setError(validationError); return; }
    const controller = new AbortController();
    uploadAbortRef.current = controller;
    setBusy(true);
    setError(null);
    setHint(null);
    setJob(null);
    setUploadProgress(0);
    let currentStage = "Preparing signed-upload authorisation";

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
        signal: controller.signal,
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
        currentStage = `Uploading ${file.name} directly to private Storage`;
        await uploadSignedFile(file, signed, (loaded) => {
          const pct = total ? ((completed + loaded) / total) * 100 : 100;
          setUploadProgress(Math.min(100, pct));
        }, controller.signal);
        completed += file.size;
        setUploadProgress(total ? (completed / total) * 100 : 100);
      }

      // The worker receives storage references only; it downloads the objects
      // from the private bucket, so neither Vercel nor the browser proxies them.
      currentStage = "Verifying uploaded file sizes and registering the processing job";
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
        signal: controller.signal,
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
      const message = e instanceof Error ? e.message : String(e);
      setError(controller.signal.aborted ? `Upload cancelled during ${currentStage}.` : `${currentStage}: ${message}`);
      setHint(controller.signal.aborted
        ? "A cancelled resumable session may retain uploaded chunks temporarily; select the files again and retry to create a fresh signed upload."
        : currentStage.includes("Storage")
          ? "Check the Supabase TUS endpoint, signed token, CORS allow-headers, bucket and object metadata. The panel resumes from the server Upload-Offset when the connection is interrupted."
          : "If storage completed but job creation failed, the private objects and their signed ownership claims remain. Retry after checking the queue/worker readiness; no job is reported as successful until it is accepted.");
    } finally {
      uploadAbortRef.current = null;
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
              addFiles(Array.from(e.dataTransfer.files));
            }}
          >
            <UploadCloud className="h-6 w-6 text-ink-faint" />
            <p className="text-xs text-ink-soft">Drag files here or choose them below</p>
            <input
              ref={inputRef}
              type="file"
              multiple
              accept={ACCEPTED_UPLOAD_TYPES}
              className="mt-1 block w-full max-w-xs text-2xs text-ink-soft file:mr-2 file:rounded file:border-0 file:bg-navy-900 file:px-2.5 file:py-1.5 file:text-2xs file:font-medium file:text-white"
              onChange={(e) => { addFiles(Array.from(e.target.files ?? [])); e.currentTarget.value = ""; }}
            />
          </div>

          <label className="block text-2xs font-medium tracking-wide text-ink-faint uppercase">
            Dataset name
            <input className="input mt-1 w-full" value={name} onChange={(e) => setName(e.target.value)} maxLength={200} />
          </label>

          {files.length ? (
            <ul className="max-h-32 space-y-1 overflow-y-auto text-2xs">
              {files.map((f, i) => (
                <li key={`${f.name}-${f.lastModified}-${i}`} className="flex items-center gap-2 border-b border-surface-line/60 pb-1">
                  <span className="min-w-0 flex-1 truncate text-ink">{f.name}<span className="ml-2 text-ink-faint">{f.type || "file"}</span></span>
                  <span className="shrink-0 font-mono text-ink-faint">{bytes(f.size)}</span>
                  <button className="grid h-6 w-6 shrink-0 place-items-center rounded text-ink-faint hover:bg-rose-50 hover:text-rose-700" type="button" onClick={() => removeFile(i)} disabled={busy} aria-label={`Remove ${f.name}`}><X className="h-3.5 w-3.5" /></button>
                </li>
              ))}
            </ul>
          ) : null}

          <div className="flex items-center gap-2">
            <button className="btn-pink" onClick={submit} disabled={busy || !files.length || worker !== "ok" || !canUpload}>
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <UploadCloud className="h-3.5 w-3.5" />}
              {busy ? "Uploading…" : "Upload and process"}
            </button>
            {files.length ? (
              <button className="btn" type="button" onClick={() => { setFiles([]); setError(null); if (inputRef.current) inputRef.current.value = ""; }} disabled={busy}>
                <Trash2 className="h-3.5 w-3.5" />Clear
              </button>
            ) : null}
            {busy ? <button className="btn" type="button" onClick={cancelUpload}>Cancel upload</button> : null}
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
              {job.status === "failed" ? (
                <button className="btn mt-2" onClick={retryJob} disabled={busy}>
                  {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
                  Retry processing
                </button>
              ) : null}
              {job.logs?.length ? (
                <ul className="mt-1.5 max-h-24 space-y-0.5 overflow-y-auto font-mono text-[0.6rem] text-ink-faint">
                  {job.logs.slice(-6).map((l, i) => <li key={i}>[{l.stage}] {l.message}</li>)}
                </ul>
              ) : null}
              {job.status === "succeeded" ? (
                <div className="mt-2 border-t border-surface-line pt-2">
                  <p className="text-ink-soft">
                    Dataset processing is complete. The new private bundle is now selected across the dashboard at request time; no Vercel rebuild is needed.
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
        <div className="rounded-lg border border-surface-line bg-surface px-4 py-3 shadow-card" role="status" aria-live="polite">
          <p className="flex items-center gap-2 text-xs font-semibold text-ink">
            {checkingWorker || wakingWorker ? <Loader2 className="h-4 w-4 animate-spin text-royal-pink" /> : worker === "ok" ? <CircleCheck className="h-4 w-4 text-emerald-600" /> : <CircleAlert className="h-4 w-4 text-amber-600" />}
            {worker === "ok" ? "Worker ready" : worker === "not_configured" ? "Worker not configured" : wakingWorker ? "Waking Render backend…" : checkingWorker ? "Checking Render connection…" : "Worker connection unavailable"}
          </p>
          <p className="mt-1 text-2xs leading-relaxed text-ink-soft">{workerDetail}</p>
          {workerSuggestion && worker !== "ok" ? <p className="mt-1 text-2xs text-ink-faint">{workerSuggestion}</p> : null}
          {worker !== "ok" ? <div className="mt-3 flex flex-wrap gap-2">
            <button className="btn" type="button" onClick={() => void retryConnection()} disabled={wakingWorker}>
              {checkingWorker && !wakingWorker ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}Retry Connection
            </button>
            <button className="btn" type="button" onClick={() => void wakeBackend()} disabled={!wakeUrl || wakingWorker}>
              {wakingWorker ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}Wake Backend
            </button>
          </div> : null}
        </div>
        <div className="rounded-lg border border-surface-line bg-surface px-4 py-3 text-xs shadow-card" aria-live="polite">
          <p className="font-semibold text-ink">Your permission level: <span className="capitalize">{access.status === "verified" ? access.role : access.status === "profile_missing" ? "Profile missing" : access.status === "invalid_role" ? "Invalid role" : "Could not verify"}</span></p>
          {canUpload ? <p className="mt-1 text-2xs text-ink-soft">Supabase confirmed your administrator role. Dataset upload and processing are enabled when the worker is ready.</p> :
            <p className="mt-1 text-2xs leading-relaxed text-rose-700">{access.message}</p>}
          {access.status === "verified" && access.role === "viewer" ? <p className="mt-1 text-2xs text-ink-soft">Your account is read-only. Only the platform administrator can upload or process datasets.</p> : null}
          {accessRefreshError ? <p role="alert" className="mt-1 text-2xs text-rose-700">Permission refresh failed: {accessRefreshError}</p> : null}
          <button className="btn mt-3" type="button" onClick={() => void refreshAccess()} disabled={refreshingAccess}>
            {refreshingAccess ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}{refreshingAccess ? "Checking permissions…" : "Refresh permissions"}
          </button>
        </div>
        <div className="flex items-center gap-1.5 text-2xs text-ink-faint">
          <CircleCheck className="h-3 w-3 text-emerald-600" /> Large file bytes never pass through a Vercel Function.
        </div>
      </div>
    </div>
  );
}
