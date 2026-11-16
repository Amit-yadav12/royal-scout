"""Database-backed job queue.

Two interchangeable implementations:

* ``LocalQueue``  – JSON files under ``<storage>/queue``. Used for local
  development and tests; it survives process restarts and supports retries.
* ``SupabaseQueue`` – the production queue, backed by the ``processing_jobs``
  table through Supabase's REST API using the service-role key.

Both expose the same interface so the worker code never changes between
environments. The queue is deliberately *pull-based*: the web tier only creates
jobs, so no request ever waits for heavy processing.
"""
from __future__ import annotations

import json
import os
import re
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

from .supabase_auth import get_supabase_server_key, get_supabase_url, supabase_api_headers, validate_supabase_url

JOB_QUEUED = "queued"
JOB_RUNNING = "running"
JOB_SUCCEEDED = "succeeded"
JOB_FAILED = "failed"
JOB_CANCELLED = "cancelled"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Job:
    id: str
    project_id: str
    dataset_id: str
    dataset_name: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    status: str = JOB_QUEUED
    progress: float = 0.0
    stage: str = "queued"
    detail: str = ""
    attempts: int = 0
    max_attempts: int = 3
    is_fixture: bool = False
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    logs: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)
    created_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class JobQueue(Protocol):
    def create(self, job: Job) -> Job: ...
    def get(self, job_id: str) -> Job | None: ...
    def list(self, project_id: str | None = None, limit: int = 50) -> list[Job]: ...
    def claim_next(self) -> Job | None: ...
    def update(self, job_id: str, **fields: Any) -> Job | None: ...
    def log(self, job_id: str, stage: str, message: str, progress: float | None = None) -> None: ...


class LocalQueue:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, job_id: str) -> Path:
        return self.root / f"{job_id}.json"

    def _write(self, job: Job) -> Job:
        job.updated_at = _now()
        tmp = self._path(job.id).with_suffix(".tmp")
        tmp.write_text(json.dumps(job.to_dict(), indent=2, default=str), encoding="utf-8")
        tmp.replace(self._path(job.id))
        return job

    def create(self, job: Job) -> Job:
        with self._lock:
            return self._write(job)

    def get(self, job_id: str) -> Job | None:
        p = self._path(job_id)
        if not p.exists():
            return None
        return Job(**json.loads(p.read_text(encoding="utf-8")))

    def list(self, project_id: str | None = None, limit: int = 50) -> list[Job]:
        jobs = []
        for p in sorted(self.root.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                j = Job(**json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                continue
            if project_id and j.project_id != project_id:
                continue
            jobs.append(j)
            if len(jobs) >= limit:
                break
        return jobs

    def claim_next(self) -> Job | None:
        with self._lock:
            for p in sorted(self.root.glob("*.json"), key=lambda x: x.stat().st_mtime):
                try:
                    j = Job(**json.loads(p.read_text(encoding="utf-8")))
                except Exception:
                    continue
                if j.status in {JOB_QUEUED} or (j.status == JOB_FAILED and j.attempts < j.max_attempts):
                    j.status = JOB_RUNNING
                    j.attempts += 1
                    j.started_at = j.started_at or _now()
                    j.stage = "starting"
                    j.detail = f"attempt {j.attempts} of {j.max_attempts}"
                    return self._write(j)
            return None

    def update(self, job_id: str, **fields: Any) -> Job | None:
        with self._lock:
            j = self.get(job_id)
            if j is None:
                return None
            for k, v in fields.items():
                if hasattr(j, k):
                    setattr(j, k, v)
            return self._write(j)

    def log(self, job_id: str, stage: str, message: str, progress: float | None = None) -> None:
        with self._lock:
            j = self.get(job_id)
            if j is None:
                return
            j.logs.append({"at": _now(), "stage": stage, "message": message,
                           "progress": progress if progress is not None else j.progress})
            if progress is not None:
                j.progress = progress
            j.stage = stage
            j.detail = message
            self._write(j)


class SupabaseQueue:
    """Production queue using the Supabase REST API and atomic PostgreSQL RPCs."""

    DB_COLUMNS = {
        "id", "project_id", "dataset_id", "dataset_name", "sources", "status", "progress",
        "stage", "detail", "attempts", "max_attempts", "is_fixture", "result", "error",
        "created_by", "created_at", "updated_at", "started_at", "finished_at",
    }

    def __init__(self, url: str | None = None, key: str | None = None, table: str = "processing_jobs"):
        self.url = validate_supabase_url(url) if url else get_supabase_url()
        self.key = key.strip() if key is not None else get_supabase_server_key()
        self.table = table
        # Validate injected values too. Use central header helper for all auth behavior.
        supabase_api_headers(key=self.key)

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        return supabase_api_headers(extra, key=self.key)

    def _req(self, method: str, path: str, **kw: Any) -> Any:
        import httpx
        r = httpx.request(method, f"{self.url}/rest/v1/{path}", headers=self._headers(kw.pop("headers", None)),
                          timeout=60, **kw)
        if r.status_code >= 300:
            # Avoid reflecting upstream response bodies, which may include request details.
            raise RuntimeError(f"Supabase {method} {path.split('?')[0]} failed (HTTP {r.status_code})")
        return r.json() if r.text else None

    def rpc(self, function: str, payload: dict[str, Any] | None = None) -> Any:
        return self._req("POST", f"rpc/{function}", json=payload or {})

    def _row_to_job(self, row: dict[str, Any]) -> Job:
        return Job(
            id=row["id"], project_id=row["project_id"], dataset_id=row["dataset_id"],
            dataset_name=row.get("dataset_name") or "dataset", sources=row.get("sources") or [],
            status=row.get("status") or JOB_QUEUED, progress=float(row.get("progress") or 0),
            stage=row.get("stage") or "queued", detail=row.get("detail") or "",
            attempts=int(row.get("attempts") or 0), max_attempts=int(row.get("max_attempts") or 3),
            is_fixture=bool(row.get("is_fixture")), created_at=row.get("created_at") or _now(),
            updated_at=row.get("updated_at") or _now(), started_at=row.get("started_at"),
            finished_at=row.get("finished_at"), error=row.get("error"), logs=[],
            result=row.get("result") or {}, created_by=row.get("created_by"))

    def create(self, job: Job) -> Job:
        if not re.fullmatch(r"job_[a-f0-9]{16}", job.id):
            raise ValueError("job ID must use the job_<16 lowercase hex> format")
        if (not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", job.project_id) or
                not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", job.dataset_id) or not job.dataset_name.strip()):
            raise ValueError("project, dataset, and dataset name are required and must be valid")
        if not 1 <= int(job.max_attempts) <= 20 or not 0 <= int(job.attempts) <= int(job.max_attempts):
            raise ValueError("job attempt counters are invalid")
        if job.status not in {JOB_QUEUED, JOB_RUNNING, JOB_SUCCEEDED, JOB_FAILED, JOB_CANCELLED}:
            raise ValueError("invalid processing job status")
        if not 0 <= float(job.progress) <= 100:
            raise ValueError("job progress must be between 0 and 100")
        if job.created_by:
            try:
                uuid.UUID(job.created_by)
            except (ValueError, AttributeError) as exc:
                raise ValueError("created_by must be a valid UUID") from exc
        if not isinstance(job.sources, list):
            raise ValueError("job sources must be a JSON array")
        for source in job.sources:
            if not isinstance(source, dict) or not ((source.get("bucket") and source.get("path")) or source.get("local_path")):
                raise ValueError("each source must contain a bucket/path or local_path reference")
        payload = {key: value for key, value in job.to_dict().items()
                   if key in self.DB_COLUMNS and key != "logs"}
        # Job ID is application-generated and matches the database text key.
        rows = self._req("POST", self.table, json=[payload], headers={"Prefer": "return=representation"})
        return self._row_to_job(rows[0])

    def get(self, job_id: str) -> Job | None:
        encoded_id = quote(job_id, safe="")
        rows = self._req("GET", f"{self.table}?id=eq.{encoded_id}&select=*")
        if not rows:
            return None
        job = self._row_to_job(rows[0])
        logs = self._req("GET", f"processing_logs?job_id=eq.{encoded_id}&select=stage,message,progress,created_at&order=created_at.asc&limit=200") or []
        job.logs = [{"at": row.get("created_at"), "stage": row.get("stage"),
                     "message": row.get("message"), "progress": row.get("progress")} for row in logs]
        return job

    def list(self, project_id: str | None = None, limit: int = 50) -> list[Job]:
        q = f"{self.table}?select=*&order=created_at.desc&limit={max(1, min(limit, 100))}"
        if project_id:
            q += f"&project_id=eq.{quote(project_id, safe='')}"
        return [self._row_to_job(r) for r in (self._req("GET", q) or [])]

    def claim_next(self) -> Job | None:
        rows = self.rpc("claim_processing_job")
        return self._row_to_job(rows[0]) if rows else None

    def requeue_stale(self) -> int:
        result = self.rpc("requeue_stale_jobs", {"stale_after": "30 minutes"})
        return int(result or 0)

    def update(self, job_id: str, **fields: Any) -> Job | None:
        allowed = self.DB_COLUMNS - {"id", "created_at", "created_by", "logs"}
        fields = {key: value for key, value in fields.items() if key in allowed}
        fields["updated_at"] = _now()
        rows = self._req("PATCH", f"{self.table}?id=eq.{quote(job_id, safe='')}", json=fields,
                         headers={"Prefer": "return=representation"})
        return self._row_to_job(rows[0]) if rows else None

    def log(self, job_id: str, stage: str, message: str, progress: float | None = None) -> None:
        self.rpc("log_job_progress", {"p_job_id": job_id, "p_stage": stage,
                                       "p_message": message, "p_progress": progress})


def make_queue(storage_root: Path) -> JobQueue:
    """Use Supabase for multi-service production; use a local queue only in development.

    A local JSON queue is not shared between separate Railway/Render services and
    must therefore never be selected silently in production.
    """
    use_supabase = os.getenv("RS_USE_SUPABASE_QUEUE", "1") == "1"
    has_supabase = bool((os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")) and
                        (os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")))
    if use_supabase and has_supabase:
        return SupabaseQueue()
    if os.getenv("RS_ENV", "development").lower() == "production":
        raise RuntimeError(
            "Production requires SUPABASE_URL and SUPABASE_SECRET_KEY (or legacy SUPABASE_SERVICE_ROLE_KEY) with "
            "RS_USE_SUPABASE_QUEUE=1. A local queue cannot be shared across worker services."
        )
    return LocalQueue(Path(storage_root) / "queue")


def new_job(project_id: str, dataset_id: str, dataset_name: str,
            sources: list[dict[str, Any]], is_fixture: bool = False,
            created_by: str | None = None) -> Job:
    return Job(id=f"job_{uuid.uuid4().hex[:16]}", project_id=project_id, dataset_id=dataset_id,
               dataset_name=dataset_name, sources=sources, is_fixture=is_fixture,
               created_by=created_by)
