"""Worker HTTP API (FastAPI).

The Vercel tier submits jobs here (never doing the heavy work itself) and reads
their status. Every mutating endpoint requires the shared secret, so the worker
can never be driven by an anonymous browser.

Endpoints
---------
GET  /health                     liveness + configuration report
POST /ingest                     multipart upload -> staging -> queued job
POST /jobs                       create a job from already-uploaded storage objects
GET  /jobs                       list jobs (optionally by project)
GET  /jobs/{job_id}              job status, progress and logs
POST /jobs/{job_id}/retry        requeue a failed job
GET  /datasets/{project}/{dataset}/bundle   serve the analytical bundle
POST /analyse                    synchronous analysis for small payloads (dev/QA only)
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile, Response
from pydantic import BaseModel, Field

from .config import DEFAULT_CONFIG, MODEL_VERSION
from .db import JOB_FAILED, make_queue, new_job
from .pipeline import run_pipeline
from .store import ArtifactStore
from .supabase_auth import (SupabaseConfigurationError, get_supabase_server_key, get_supabase_url,
                            supabase_api_headers, supabase_key_type)

STORAGE = Path(os.getenv("RS_STORAGE_ROOT", "./storage"))
SHARED_SECRET = os.getenv("WORKER_SHARED_SECRET", "")
MAX_UPLOAD_FILES = int(os.getenv("RS_MAX_UPLOAD_FILES", "200"))

app = FastAPI(title="Royal Scout Worker API", version=MODEL_VERSION,
              description="Ingestion + analytics worker for Royal Scout Intelligence Hub")


def require_secret(x_worker_secret: str | None = Header(default=None)) -> None:
    if not SHARED_SECRET:
        # Fail closed in production, allow local development with a clear warning.
        if os.getenv("RS_ENV", "production").lower() == "production":
            raise HTTPException(503, "WORKER_SHARED_SECRET is not configured on the worker; "
                                     "refusing unauthenticated job submission")
        return
    if x_worker_secret != SHARED_SECRET:
        raise HTTPException(401, "invalid or missing X-Worker-Secret header")


class SourceRef(BaseModel):
    bucket: str | None = None
    path: str | None = None
    local_path: str | None = None


class JobRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=64)
    dataset_id: str = Field(min_length=1, max_length=64)
    dataset_name: str = Field(min_length=1, max_length=200)
    sources: list[SourceRef] = Field(min_length=1)
    is_fixture: bool = False
    created_by: UUID | None = None


def _health_report() -> dict[str, Any]:
    STORAGE.mkdir(parents=True, exist_ok=True)
    try:
        configured_url = get_supabase_url()
        server_key = get_supabase_server_key()
        key_type = supabase_key_type(server_key)
        supabase_configured = True
    except SupabaseConfigurationError:
        configured_url, server_key, key_type = "", "", None
        supabase_configured = False

    supabase_reachable = False
    queue_accessible = False
    storage_accessible = False
    queue_diagnostic = "not_checked"
    storage_diagnostic = "not_checked"
    queue_name = "unavailable"
    if supabase_configured:
        import httpx
        try:
            response = httpx.get(f"{configured_url}/rest/v1/processing_jobs?select=id&limit=1",
                                 headers=supabase_api_headers(key=server_key), timeout=5)
            supabase_reachable = True  # an HTTP response confirms network/API reachability
            queue_accessible = response.is_success
            queue_diagnostic = ("ok" if queue_accessible else {401: "invalid_api_key", 403: "permission_denied",
                                404: "processing_jobs_missing"}.get(response.status_code, "queue_unavailable"))
        except Exception:
            queue_diagnostic = "supabase_unreachable"
        try:
            bucket = os.getenv("SUPABASE_ARTIFACT_BUCKET", "royal-scout-artifacts")
            response = httpx.get(f"{configured_url}/storage/v1/bucket/{bucket}",
                                 headers=supabase_api_headers(key=server_key), timeout=5)
            supabase_reachable = True
            storage_accessible = response.is_success
            storage_diagnostic = ("ok" if storage_accessible else {401: "invalid_api_key", 403: "permission_denied",
                                  404: "artifact_bucket_missing"}.get(response.status_code, "storage_unavailable"))
        except Exception:
            storage_diagnostic = "supabase_unreachable"
        try:
            from .db import SupabaseQueue
            queue_name = type(SupabaseQueue()).__name__
        except Exception:
            pass

    try:
        probe = STORAGE / ".health-write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        storage_writable = True
    except OSError:
        storage_writable = False
    checks = {
        "api_running": True, "configuration_valid": supabase_configured,
        "supabase_configured": supabase_configured, "supabase_key_type": key_type,
        "supabase_reachable": supabase_reachable, "queue_accessible": queue_accessible,
        "storage_accessible": storage_accessible,
        "queue_diagnostic": queue_diagnostic,
        "storage_diagnostic": storage_diagnostic,
        "worker_shared_secret_configured": bool(SHARED_SECRET),
        "temporary_storage_writable": storage_writable,
        "queue_configuration_valid": (queue_name == "SupabaseQueue" and os.getenv("RS_USE_SUPABASE_QUEUE", "1") == "1") if os.getenv("RS_ENV", "development").lower() == "production" else True,
    }
    ready = all(checks[key] for key in ("configuration_valid", "supabase_reachable", "queue_accessible",
                                         "storage_accessible", "worker_shared_secret_configured",
                                         "temporary_storage_writable", "queue_configuration_valid"))
    return {"status": "ready" if ready else "degraded", "ready": ready,
            "model_version": MODEL_VERSION, "checks": checks, "queue": queue_name,
            "limits": {"max_single_file_bytes": DEFAULT_CONFIG.limits.max_single_file_bytes,
                       "max_archive_entries": DEFAULT_CONFIG.limits.max_archive_entries,
                       "max_total_extracted_bytes": DEFAULT_CONFIG.limits.max_total_extracted_bytes,
                       "max_files_per_upload": DEFAULT_CONFIG.limits.max_files_per_upload}}


@app.get("/health/live")
def health_live() -> dict[str, Any]:
    return {"status": "alive", "api_running": True, "model_version": MODEL_VERSION}


@app.get("/health/ready")
def health_ready(response: Response) -> dict[str, Any]:
    report = _health_report()
    if not report["ready"]:
        response.status_code = 503
    return report


@app.get("/health")
def health() -> dict[str, Any]:
    return _health_report()


@app.post("/jobs", dependencies=[Depends(require_secret)])
def create_job(req: JobRequest) -> dict[str, Any]:
    if os.getenv("RS_ENV", "development").lower() == "production" and any(s.local_path for s in req.sources):
        raise HTTPException(400, "Production jobs must reference authorised private Storage objects.")
    if not all(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value) for value in (req.project_id, req.dataset_id)):
        raise HTTPException(400, "Invalid project or dataset identifier.")
    q = make_queue(STORAGE)
    job = new_job(req.project_id, req.dataset_id, req.dataset_name,
                  [s.model_dump(exclude_none=True) for s in req.sources],
                  is_fixture=req.is_fixture, created_by=str(req.created_by) if req.created_by else None)
    q.create(job)
    q.log(job.id, "queued", f"{len(req.sources)} source(s) queued")
    return {"job": job.to_dict()}


@app.post("/ingest", dependencies=[Depends(require_secret)])
async def ingest(project_id: str = Form(...), dataset_name: str = Form(...),
                 is_fixture: bool = Form(False), dataset_id: str | None = Form(None),
                 files: list[UploadFile] = File(...)) -> dict[str, Any]:
    if os.getenv("RS_ENV", "development").lower() == "production":
        raise HTTPException(410, "Direct uploads are disabled in production; upload directly to private Supabase Storage.")
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(413, f"at most {MAX_UPLOAD_FILES} files per request; "
                                 f"upload an archive or split the batch")
    ds_id = dataset_id or f"ds_{uuid.uuid4().hex[:12]}"
    staging = STORAGE / "uploads" / f"{project_id}" / ds_id
    staging.mkdir(parents=True, exist_ok=True)
    stored: list[dict[str, Any]] = []
    for f in files:
        name = Path(f.filename or "upload").name
        target = staging / name
        size = 0
        with open(target, "wb") as out:
            while chunk := await f.read(1 << 20):
                size += len(chunk)
                if size > DEFAULT_CONFIG.limits.max_single_file_bytes:
                    out.close()
                    target.unlink(missing_ok=True)
                    raise HTTPException(413, f"'{name}' exceeds the configured single-file limit "
                                             f"of {DEFAULT_CONFIG.limits.max_single_file_bytes} bytes")
                out.write(chunk)
        stored.append({"local_path": str(target), "name": name, "bytes": size})
    q = make_queue(STORAGE)
    job = new_job(project_id, ds_id, dataset_name, stored, is_fixture=is_fixture)
    q.create(job)
    q.log(job.id, "queued", f"{len(stored)} file(s) staged")
    return {"job_id": job.id, "dataset_id": ds_id, "files": stored,
            "message": "queued for background processing"}


@app.get("/jobs/{job_id}", dependencies=[Depends(require_secret)])
def get_job(job_id: str) -> dict[str, Any]:
    q = make_queue(STORAGE)
    job = q.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job.to_dict()


@app.get("/jobs", dependencies=[Depends(require_secret)])
def list_jobs(project_id: str | None = None, limit: int = 25) -> dict[str, Any]:
    q = make_queue(STORAGE)
    return {"jobs": [j.to_dict() for j in q.list(project_id=project_id, limit=limit)]}


@app.post("/jobs/{job_id}/retry", dependencies=[Depends(require_secret)])
def retry_job(job_id: str) -> dict[str, Any]:
    q = make_queue(STORAGE)
    job = q.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    if job.status == "running":
        raise HTTPException(409, "A running job cannot be retried.")
    if job.attempts >= job.max_attempts:
        raise HTTPException(409, "The retry limit has been reached for this job.")
    q.update(job_id, status="queued", error=None, stage="requeued", detail="manually requeued")
    q.log(job_id, "requeued", "job requeued by operator")
    return {"job": q.get(job_id).to_dict()}


@app.get("/datasets/{project_id}/{dataset_id}/bundle", dependencies=[Depends(require_secret)])
def get_bundle(project_id: str, dataset_id: str) -> Any:
    if not all(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value) for value in (project_id, dataset_id)):
        raise HTTPException(400, "Invalid project or dataset identifier.")
    path = ArtifactStore(STORAGE).dataset_dir(project_id, dataset_id) / "bundle.json"
    if path.exists():
        return ArtifactStore(STORAGE).read_json(path)
    try:
        import httpx
        url, key = get_supabase_url(), get_supabase_server_key()
        bucket = os.getenv("SUPABASE_ARTIFACT_BUCKET", "royal-scout-artifacts")
        object_path = f"{project_id}/{dataset_id}/bundle.json"
        response = httpx.get(f"{url}/storage/v1/object/{bucket}/{object_path}",
                             headers=supabase_api_headers(key=key), timeout=30)
        if response.status_code == 404:
            raise HTTPException(404, "no bundle for this dataset yet")
        if not response.is_success:
            raise HTTPException(502, "private analytical bundle is temporarily unavailable")
        return response.json()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(502, "private analytical bundle is temporarily unavailable") from None


class AnalyseRequest(BaseModel):
    project_id: str = "synchronous"
    dataset_name: str = "Synchronous analysis"
    paths: list[str] = Field(min_length=1)
    is_fixture: bool = True
    mode: Literal["full"] = "full"


@app.post("/analyse", dependencies=[Depends(require_secret)])
def analyse(req: AnalyseRequest) -> dict[str, Any]:
    """Synchronous analysis, for QA and small fixture datasets only.

    Production ingestion must go through /jobs so a slow dataset can never block a
    request. The endpoint refuses anything that looks large.
    """
    total = 0
    for p in req.paths:
        pp = Path(p)
        if not pp.exists():
            raise HTTPException(400, f"path not found: {p}")
        total += pp.stat().st_size if pp.is_file() else sum(f.stat().st_size for f in pp.rglob("*"))
    if total > 8 * 1024 * 1024:
        raise HTTPException(413, "synchronous analysis is limited to 8 MB; submit a job instead")
    dataset_id = f"ds_{uuid.uuid4().hex[:12]}"
    bundle = run_pipeline(sources=[Path(p) for p in req.paths], storage_root=STORAGE,
                          project_id=req.project_id, dataset_id=dataset_id,
                          dataset_name=req.dataset_name, is_fixture=req.is_fixture, export=False)
    return {"dataset_id": dataset_id, "bundle": bundle}
