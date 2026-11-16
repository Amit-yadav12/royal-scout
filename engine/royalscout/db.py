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
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

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
    """Production queue over the `processing_jobs` table (service-role key only)."""

    def __init__(self, url: str | None = None, key: str | None = None, table: str = "processing_jobs"):
        self.url = (url or os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
        self.key = key or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
        self.table = table
        if not (self.url and self.key):
            raise RuntimeError("SupabaseQueue requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        h = {"apikey": self.key, "Authorization": f"Bearer {self.key}",
             "Content-Type": "application/json"}
        if extra:
            h.update(extra)
        return h

    def _req(self, method: str, path: str, **kw: Any) -> Any:
        import httpx
        r = httpx.request(method, f"{self.url}/rest/v1/{path}", headers=self._headers(kw.pop("headers", None)),
                          timeout=60, **kw)
        if r.status_code >= 300:
            raise RuntimeError(f"supabase {method} {path} -> {r.status_code}: {r.text[:300]}")
        return r.json() if r.text else None

    def _row_to_job(self, row: dict[str, Any]) -> Job:
        return Job(
            id=row["id"], project_id=row["project_id"], dataset_id=row["dataset_id"],
            dataset_name=row.get("dataset_name") or "dataset",
            sources=row.get("sources") or [], status=row.get("status") or JOB_QUEUED,
            progress=float(row.get("progress") or 0), stage=row.get("stage") or "queued",
            detail=row.get("detail") or "", attempts=int(row.get("attempts") or 0),
            max_attempts=int(row.get("max_attempts") or 3), is_fixture=bool(row.get("is_fixture")),
            created_at=row.get("created_at") or _now(), updated_at=row.get("updated_at") or _now(),
            started_at=row.get("started_at"), finished_at=row.get("finished_at"),
            error=row.get("error"), logs=row.get("logs") or [], result=row.get("result") or {},
            created_by=row.get("created_by"))

    def create(self, job: Job) -> Job:
        payload = job.to_dict()
        payload.pop("id", None) if not job.id else None
        rows = self._req("POST", self.table, json=[payload], headers={"Prefer": "return=representation"})
        return self._row_to_job(rows[0])

    def get(self, job_id: str) -> Job | None:
        rows = self._req("GET", f"{self.table}?id=eq.{job_id}&select=*")
        return self._row_to_job(rows[0]) if rows else None

    def list(self, project_id: str | None = None, limit: int = 50) -> list[Job]:
        q = f"{self.table}?select=*&order=created_at.desc&limit={limit}"
        if project_id:
            q += f"&project_id=eq.{project_id}"
        return [self._row_to_job(r) for r in (self._req("GET", q) or [])]

    def claim_next(self) -> Job | None:
        rows = self._req("GET", f"{self.table}?status=eq.{JOB_QUEUED}&select=*&order=created_at.asc&limit=1")
        if not rows:
            retry = self._req("GET", f"{self.table}?status=eq.{JOB_FAILED}&select=*&order=created_at.asc&limit=1")
            rows = [r for r in (retry or []) if int(r.get("attempts") or 0) < int(r.get("max_attempts") or 3)]
        if not rows:
            return None
        job = self._row_to_job(rows[0])
        # optimistic claim: only succeeds if nobody else flipped the status
        updated = self._req(
            "PATCH", f"{self.table}?id=eq.{job.id}&status=eq.{job.status}",
            json={"status": JOB_RUNNING, "attempts": job.attempts + 1, "started_at": _now(),
                  "stage": "starting", "updated_at": _now()},
            headers={"Prefer": "return=representation"})
        return self._row_to_job(updated[0]) if updated else None

    def update(self, job_id: str, **fields: Any) -> Job | None:
        fields["updated_at"] = _now()
        rows = self._req("PATCH", f"{self.table}?id=eq.{job_id}", json=fields,
                         headers={"Prefer": "return=representation"})
        return self._row_to_job(rows[0]) if rows else None

    def log(self, job_id: str, stage: str, message: str, progress: float | None = None) -> None:
        payload: dict[str, Any] = {"stage": stage, "detail": message}
        if progress is not None:
            payload["progress"] = progress
        self.update(job_id, **payload)
        try:
            self._req("POST", "processing_logs",
                      json=[{"job_id": job_id, "stage": stage, "message": message,
                             "progress": progress}])
        except Exception:
            pass  # logging must never break the job


def make_queue(storage_root: Path) -> JobQueue:
    """Use Supabase for multi-service production; use a local queue only in development.

    A local JSON queue is not shared between separate Railway/Render services and
    must therefore never be selected silently in production.
    """
    use_supabase = os.getenv("RS_USE_SUPABASE_QUEUE", "1") == "1"
    has_supabase = bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
    if use_supabase and has_supabase:
        return SupabaseQueue()
    if os.getenv("RS_ENV", "development").lower() == "production":
        raise RuntimeError(
            "Production requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY with "
            "RS_USE_SUPABASE_QUEUE=1. A local queue cannot be shared across worker services."
        )
    return LocalQueue(Path(storage_root) / "queue")


def new_job(project_id: str, dataset_id: str, dataset_name: str,
            sources: list[dict[str, Any]], is_fixture: bool = False,
            created_by: str | None = None) -> Job:
    return Job(id=f"job_{uuid.uuid4().hex[:16]}", project_id=project_id, dataset_id=dataset_id,
               dataset_name=dataset_name, sources=sources, is_fixture=is_fixture,
               created_by=created_by)
