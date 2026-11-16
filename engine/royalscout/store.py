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
from urllib.parse import quote

from .supabase_auth import get_supabase_server_key, get_supabase_url, supabase_api_headers
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
    """Stream files into a private Supabase bucket using central server auth.

    Returns status per object; callers must enforce required artifacts before
    transitioning a job to succeeded. Error details never include credentials.
    """
    try:
        url, key = get_supabase_url(), get_supabase_server_key()
    except Exception as exc:
        return [{"file": p.name, "status": "failed", "reason": str(exc)} for p in paths]
    import httpx

    safe_bucket = bucket.strip()
    if not safe_bucket or "/" in safe_bucket or ".." in safe_bucket:
        return [{"file": p.name, "status": "failed", "reason": "invalid artifact bucket"} for p in paths]
    results: list[dict[str, Any]] = []
    for p in paths:
        object_path = f"{prefix.strip('/')}/{p.name}" if prefix else p.name
        encoded = "/".join(quote(part, safe="") for part in object_path.split("/"))
        try:
            with p.open("rb") as fh:
                response = httpx.post(
                    f"{url}/storage/v1/object/{quote(safe_bucket, safe='')}/{encoded}",
                    headers=supabase_api_headers({"x-upsert": "true", "Content-Type": _content_type(p)}, key=key),
                    content=fh, timeout=300)
            results.append({"file": p.name, "object": object_path,
                            "status": "uploaded" if response.is_success else "failed",
                            "http_status": response.status_code,
                            "reason": None if response.is_success else f"Storage upload failed (HTTP {response.status_code})"})
        except Exception as exc:
            results.append({"file": p.name, "object": object_path, "status": "failed",
                            "reason": f"Storage upload failed ({type(exc).__name__})"})
    return results


def _content_type(p: Path) -> str:
    return {
        ".json": "application/json", ".csv": "text/csv", ".parquet": "application/octet-stream",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".pdf": "application/pdf",
    }.get(Path(p).suffix.lower(), "application/octet-stream")
