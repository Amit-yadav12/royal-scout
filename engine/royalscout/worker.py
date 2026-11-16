"""Background worker: claims queued jobs and runs the pipeline.

Deployed separately from Vercel (Railway/Render/Fly) so that archive extraction
and analytics never run inside a serverless request. Supports retries with
attempt accounting, structured logging, and progress heartbeats written back to
the queue so the UI can show live status.
"""
from __future__ import annotations

import os
import signal
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from .config import DEFAULT_CONFIG
from .db import JOB_FAILED, JOB_SUCCEEDED, Job, make_queue
from .pipeline import run_pipeline
from .store import publish_to_supabase

_shutdown = False


def _handle_signal(signum: int, frame: Any) -> None:  # pragma: no cover
    global _shutdown
    _shutdown = True
    print(f"[worker] received signal {signum}; finishing current job then exiting", flush=True)


def fetch_sources(job: Job, staging: Path) -> list[Path]:
    """Materialise a job's sources locally.

    Local jobs carry absolute/relative filesystem paths. Remote jobs carry
    ``{"bucket": ..., "path": ...}`` objects which are downloaded from Supabase
    Storage with the service-role key (private buckets, signed by the worker).
    """
    staging.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for src in job.sources:
        if "local_path" in src:
            p = Path(src["local_path"])
            if p.exists():
                paths.append(p)
            continue
        bucket, obj = src.get("bucket"), src.get("path")
        if not bucket or not obj:
            continue
        url = (os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not (url and key):
            raise RuntimeError("remote source supplied but SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY "
                               "are not configured on the worker")
        import httpx
        target = staging / Path(obj).name
        with httpx.stream("GET", f"{url}/storage/v1/object/{bucket}/{obj}",
                          headers={"apikey": key, "Authorization": f"Bearer {key}"}, timeout=300) as r:
            if r.status_code >= 300:
                raise RuntimeError(f"failed to download s3://{bucket}/{obj}: HTTP {r.status_code}")
            with open(target, "wb") as fh:
                for chunk in r.iter_bytes(1 << 20):
                    fh.write(chunk)
        paths.append(target)
    return paths


def process_job(job: Job, queue: Any, storage: Path, export: bool = True) -> dict[str, Any]:
    def progress(stage: str, pct: float, detail: str) -> None:
        try:
            queue.log(job.id, stage, detail or stage, pct)
        except Exception:
            pass
        if detail:
            print(f"[job {job.id}] {pct:5.1f}% {stage}: {detail}", flush=True)

    staging = Path(storage) / "staging" / job.id
    sources = fetch_sources(job, staging)
    if not sources:
        raise RuntimeError("job has no readable sources (all paths missing or empty)")
    bundle = run_pipeline(
        sources=sources, storage_root=Path(storage), project_id=job.project_id,
        dataset_id=job.dataset_id, dataset_name=job.dataset_name, cfg=DEFAULT_CONFIG,
        is_fixture=job.is_fixture, progress=progress, export=export)

    dataset_dir = Path(storage) / "projects" / job.project_id / "datasets" / job.dataset_id
    artefacts = [dataset_dir / "bundle.json"]
    for sub in ("exports", "canonical"):
        d = dataset_dir / sub
        if d.exists():
            artefacts.extend(sorted(p for p in d.iterdir() if p.is_file()))
    uploads = publish_to_supabase(artefacts, os.getenv("SUPABASE_ARTIFACT_BUCKET", "royal-scout-artifacts"),
                                  f"{job.project_id}/{job.dataset_id}")
    return {
        "bundle_path": str(dataset_dir / "bundle.json"),
        "artefacts": [str(p) for p in artefacts],
        "uploads": uploads,
        "summary": bundle["ingestion"]["summary"],
        "batters_ranked": len(bundle["leaderboards"]["global"]["batters"]),
        "bowlers_ranked": len(bundle["leaderboards"]["global"]["bowlers"]),
        "quality_score": bundle["quality"]["score"],
    }


def run_worker(storage: Path, once: bool = False, interval: float = 5.0, max_jobs: int = 0) -> int:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    queue = make_queue(storage)
    print(f"[worker] queue={type(queue).__name__} storage={storage}", flush=True)
    processed = 0
    while not _shutdown:
        job = queue.claim_next()
        if job is None:
            if once:
                print("[worker] no jobs available", flush=True)
                return 0
            time.sleep(interval)
            continue
        print(f"[worker] claimed job {job.id} ({job.project_id}/{job.dataset_id}) "
              f"attempt {job.attempts}/{job.max_attempts}", flush=True)
        try:
            result = process_job(job, queue, Path(storage))
            queue.update(job.id, status=JOB_SUCCEEDED, progress=100, stage="complete",
                         detail="pipeline finished", result=result,
                         finished_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            print(f"[worker] job {job.id} succeeded", flush=True)
            processed += 1
        except Exception as exc:
            tb = traceback.format_exc()
            retryable = job.attempts < job.max_attempts
            queue.update(job.id, status=JOB_FAILED if not retryable else "failed",
                         stage="failed", error=f"{type(exc).__name__}: {exc}",
                         detail=("will retry" if retryable else "retries exhausted"),
                         finished_at=None if retryable else time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            print(f"[worker] job {job.id} failed ({'retryable' if retryable else 'exhausted'}): {exc}\n{tb}",
                  file=sys.stderr, flush=True)
        if max_jobs and processed >= max_jobs:
            return 0
        if once:
            return 0
    return 0
