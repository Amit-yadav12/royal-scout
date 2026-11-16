"""Artifact storage.

Local filesystem is the reference implementation; the Supabase adapter uploads the
same artefacts to private Storage buckets when credentials are configured. The web
app reads the committed bundle in static deployments and Supabase in full
deployments.
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ArtifactStore:
    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    def dataset_dir(self, project_id: str, dataset_id: str) -> Path:
        d = self.root / "projects" / project_id / "datasets" / dataset_id
        d.mkdir(parents=True, exist_ok=True)
        for sub in ("originals", "extracted", "canonical", "exports", "logs", "uploads"):
            (d / sub).mkdir(exist_ok=True)
        return d

    def write_json(self, path: Path, payload: Any) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return path

    def read_json(self, path: Path) -> Any:
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def copy_in(self, src: Path, dest_dir: Path, prefer_name: str | None = None) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        name = prefer_name or Path(src).name
        target = dest_dir / name
        i = 1
        while target.exists():
            stem, suffix = Path(name).stem, Path(name).suffix
            target = dest_dir / f"{stem}_{i}{suffix}"
            i += 1
        shutil.copy2(src, target)
        return target

    def write_parquet(self, path: Path, frame) -> Path | None:
        """Best-effort Parquet write; returns None when the frame is empty."""
        if frame is None:
            return None
        try:
            height = frame.height
        except AttributeError:
            height = len(frame)
        if not height:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import polars as pl
            if isinstance(frame, pl.DataFrame):
                frame.write_parquet(path)
            else:
                pl.from_pandas(frame).write_parquet(path)
            return path
        except Exception:
            return None


def publish_to_supabase(paths: list[Path], bucket: str, prefix: str) -> list[dict[str, Any]]:
    """Upload artefacts to Supabase Storage (private bucket, service role).

    Returns a per-file result list. Never raises: failures are reported so the job
    can mark itself partially complete instead of silently losing artefacts.
    """
    url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not (url and key):
        return [{"file": str(p), "status": "skipped", "reason": "Supabase credentials not configured"} for p in paths]
    import httpx

    results: list[dict[str, Any]] = []
    for p in paths:
        key_path = f"{prefix.strip('/')}/{Path(p).name}" if prefix else Path(p).name
        try:
            with open(p, "rb") as fh:
                r = httpx.post(
                    f"{url.rstrip('/')}/storage/v1/object/{bucket}/{key_path}",
                    headers={"apikey": key, "Authorization": f"Bearer {key}", "x-upsert": "true",
                             "Content-Type": _content_type(p)},
                    content=fh, timeout=300)
            results.append({"file": str(p), "object": key_path,
                            "status": "uploaded" if r.status_code < 300 else "failed",
                            "http_status": r.status_code,
                            "detail": None if r.status_code < 300 else r.text[:300]})
        except Exception as exc:  # network error must not kill the job
            results.append({"file": str(p), "status": "failed", "detail": f"{type(exc).__name__}: {exc}"})
    return results


def _content_type(p: Path) -> str:
    return {
        ".json": "application/json", ".csv": "text/csv", ".parquet": "application/octet-stream",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".pdf": "application/pdf",
    }.get(Path(p).suffix.lower(), "application/octet-stream")
