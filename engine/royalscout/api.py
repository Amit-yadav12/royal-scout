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
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .config import DEFAULT_CONFIG, MODEL_VERSION
from .db import JOB_FAILED, make_queue, new_job
from .pipeline import run_pipeline
from .store import ArtifactStore

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
    created_by: str | None = None


@app.get("/health")
def health() -> dict[str, Any]:
    STORAGE.mkdir(parents=True, exist_ok=True)
    supabase_configured = bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
    storage_writable = os.access(STORAGE, os.W_OK)
    queue_name = "unavailable"
    queue_error = None
    try:
        q = make_queue(STORAGE)
        queue_name = type(q).__name__
    except Exception as exc:
        queue_error = f"{type(exc).__name__}: {exc}"
    production_ready = os.getenv("RS_ENV", "development").lower() != "production" or (supabase_configured and queue_name == "SupabaseQueue")
    ready = bool(storage_writable and SHARED_SECRET and production_ready and queue_error is None)
    return {
        "status": "ok" if ready else "degraded", "ready": ready, "model_version": MODEL_VERSION,
        "storage_root": str(STORAGE), "storage_writable": storage_writable,
        "queue": queue_name, "queue_error": queue_error,
        "supabase_configured": supabase_configured,
        "shared_secret_configured": bool(SHARED_SECRET),
        "limits": {
            "max_single_file_bytes": DEFAULT_CONFIG.limits.max_single_file_bytes,
            "max_archive_entries": DEFAULT_CONFIG.limits.max_archive_entries,
            "max_total_extracted_bytes": DEFAULT_CONFIG.limits.max_total_extracted_bytes,
            "max_files_per_upload": DEFAULT_CONFIG.limits.max_files_per_upload,
        },
    }


@app.post("/jobs", dependencies=[Depends(require_secret)])
def create_job(req: JobRequest) -> dict[str, Any]:
    q = make_queue(STORAGE)
    job = new_job(req.project_id, req.dataset_id, req.dataset_name,
                  [s.model_dump(exclude_none=True) for s in req.sources],
                  is_fixture=req.is_fixture, created_by=req.created_by)
    q.create(job)
    q.log(job.id, "queued", f"{len(req.sources)} source(s) queued")
    return {"job": job.to_dict()}


@app.post("/ingest", dependencies=[Depends(require_secret)])
async def ingest(project_id: str = Form(...), dataset_name: str = Form(...),
                 is_fixture: bool = Form(False), dataset_id: str | None = Form(None),
                 files: list[UploadFile] = File(...)) -> dict[str, Any]:
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
    q.update(job_id, status="queued", error=None, stage="requeued", detail="manually requeued")
    q.log(job_id, "requeued", "job requeued by operator")
    return {"job": q.get(job_id).to_dict()}


@app.get("/datasets/{project_id}/{dataset_id}/bundle", dependencies=[Depends(require_secret)])
def get_bundle(project_id: str, dataset_id: str) -> Any:
    path = ArtifactStore(STORAGE).dataset_dir(project_id, dataset_id) / "bundle.json"
    if not path.exists():
        raise HTTPException(404, "no bundle for this dataset yet")
    return ArtifactStore(STORAGE).read_json(path)


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
