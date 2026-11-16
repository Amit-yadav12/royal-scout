"""Background worker: claims queued jobs and runs the pipeline.

Deployed separately from Vercel (Railway/Render/Fly) so that archive extraction
and analytics never run inside a serverless request. Supports retries with
attempt accounting, structured logging, and progress heartbeats written back to
the queue so the UI can show live status.
"""
from __future__ import annotations

import os
import hashlib
import signal
import sys
import threading
import time
import traceback
from urllib.parse import quote

from .supabase_auth import get_supabase_server_key, get_supabase_url, supabase_api_headers
from pathlib import Path
from typing import Any

from .config import DEFAULT_CONFIG
from .db import JOB_FAILED, JOB_SUCCEEDED, Job, SupabaseQueue, make_queue
from .pipeline import run_pipeline
from .store import publish_to_supabase

_shutdown = False


def _handle_signal(signum: int, frame: Any) -> None:  # pragma: no cover
    global _shutdown
    _shutdown = True
    print(f"[worker] received signal {signum}; finishing current job then exiting", flush=True)


def fetch_sources(job: Job, staging: Path) -> list[Path]:
    """Download private object refs into this job's confined staging directory."""
    staging = Path(staging).resolve()
    staging.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    total_bytes = 0
    max_files = DEFAULT_CONFIG.limits.max_files_per_upload
    max_file_bytes = DEFAULT_CONFIG.limits.max_single_file_bytes
    max_total_bytes = DEFAULT_CONFIG.limits.max_total_extracted_bytes
    if len(job.sources) > max_files:
        raise RuntimeError("job source count exceeds the configured file limit")
    for src in job.sources:
        if "local_path" in src:
            if os.getenv("RS_ENV", "development").lower() == "production":
                raise RuntimeError("production jobs must reference private Storage objects, not local_path")
            p = Path(src["local_path"]).resolve()
            if p.is_file() and p.stat().st_size:
                size = p.stat().st_size
                total_bytes += size
                if size > max_file_bytes or total_bytes > max_total_bytes:
                    raise RuntimeError("source files exceed the configured processing size limit")
                paths.append(p)
            continue
        bucket, obj = src.get("bucket"), src.get("path")
        if not isinstance(bucket, str) or not isinstance(obj, str) or not bucket or not obj:
            continue
        if obj.startswith("/") or "\\" in obj or any(part in {"", ".", ".."} for part in obj.split("/")):
            raise RuntimeError("source object path is invalid")
        allowed = {os.getenv("SUPABASE_UPLOAD_BUCKET", "uploads"), "fixtures"}
        if bucket not in allowed:
            raise RuntimeError("source bucket is not authorised for worker processing")
        url, key = get_supabase_url(), get_supabase_server_key()
        import httpx
        safe_name = Path(obj).name[:160]
        stable_prefix = hashlib.sha256(obj.encode("utf-8")).hexdigest()[:10]
        target = (staging / f"{len(paths):03d}-{stable_prefix}-{safe_name}").resolve()
        if target.parent != staging:
            raise RuntimeError("source filename escapes staging directory")
        encoded_bucket = quote(bucket, safe="")
        encoded_obj = "/".join(quote(part, safe="") for part in obj.split("/"))
        tmp = target.with_suffix(target.suffix + ".part")
        try:
            with httpx.stream("GET", f"{url}/storage/v1/object/{encoded_bucket}/{encoded_obj}",
                              headers=supabase_api_headers(key=key), timeout=300) as response:
                if response.status_code >= 300:
                    raise RuntimeError(f"private source download failed (HTTP {response.status_code})")
                count = 0
                with tmp.open("wb") as output:
                    for chunk in response.iter_bytes(1 << 20):
                        if not chunk:
                            continue
                        count += len(chunk)
                        if count > max_file_bytes or total_bytes + count > max_total_bytes:
                            raise RuntimeError("source download exceeds the configured processing size limit")
                        output.write(chunk)
            if count <= 0:
                raise RuntimeError("downloaded source is empty")
            tmp.replace(target)
            total_bytes += count
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
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
    artefacts = [dataset_dir / name for name in ("bundle.json", "ingestion_report.json", "quality_report.json", "config.json")
                 if (dataset_dir / name).is_file()]
    for sub in ("exports", "canonical"):
        d = dataset_dir / sub
        if d.exists():
            artefacts.extend(sorted(p for p in d.iterdir() if p.is_file()))
    progress("publishing", 96, "publishing analytical artifacts to private storage")
    artifact_bucket = os.getenv("SUPABASE_ARTIFACT_BUCKET", "royal-scout-artifacts")
    uploads = publish_to_supabase(artefacts, artifact_bucket, f"{job.project_id}/{job.dataset_id}")
    bundle_upload = next((item for item in uploads if item.get("file") == "bundle.json"), None)
    if (os.getenv("RS_ENV", "development").lower() == "production" or isinstance(queue, SupabaseQueue)) and (
            not bundle_upload or bundle_upload.get("status") != "uploaded"):
        raise RuntimeError("required analytical bundle could not be published to private Storage")
    remote_mode = os.getenv("RS_ENV", "development").lower() == "production" or isinstance(queue, SupabaseQueue)
    result = {
        "bundle_object": f"{job.project_id}/{job.dataset_id}/bundle.json" if bundle_upload and bundle_upload.get("status") == "uploaded" else None,
        "bundle_path": None if remote_mode else str(dataset_dir / "bundle.json"),
        "artefacts": [item.get("object") for item in uploads if item.get("status") == "uploaded"],
        "artifact_bucket": artifact_bucket,
        "uploads": uploads,
        "summary": bundle["ingestion"]["summary"],
        "batters_ranked": len(bundle["leaderboards"]["global"]["batters"]),
        "bowlers_ranked": len(bundle["leaderboards"]["global"]["bowlers"]),
        "quality_score": bundle["quality"]["score"],
    }
    if remote_mode:
        import shutil
        shutil.rmtree(dataset_dir, ignore_errors=True)
    return result


def run_worker(storage: Path, once: bool = False, interval: float = 5.0, max_jobs: int = 0) -> int:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    queue = make_queue(storage)
    if hasattr(queue, "requeue_stale"):
        recovered = queue.requeue_stale()
        print(f"[worker] stale_jobs_requeued={recovered}", flush=True)
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
        heartbeat_stop = threading.Event()

        def heartbeat() -> None:
            while not heartbeat_stop.wait(60):
                try:
                    queue.update(job.id)  # refresh updated_at without replacing current stage/detail
                except Exception as exc:
                    print(f"[worker] heartbeat update failed for {job.id} ({type(exc).__name__})", file=sys.stderr, flush=True)

        heartbeat_thread = threading.Thread(target=heartbeat, name=f"heartbeat-{job.id}", daemon=True)
        heartbeat_thread.start()
        try:
            result = process_job(job, queue, Path(storage))
            completed = queue.update(job.id, status=JOB_SUCCEEDED, progress=100, stage="complete",
                                     detail="pipeline finished", result=result,
                                     finished_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            if completed is None:
                raise RuntimeError("job result was published but the queue could not record completion")
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
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=2)
        import shutil
        shutil.rmtree(Path(storage) / "staging" / job.id, ignore_errors=True)
        if max_jobs and processed >= max_jobs:
            return 0
        if once:
            return 0
    return 0
