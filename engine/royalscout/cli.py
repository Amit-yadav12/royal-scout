"""Command line interface for the Royal Scout engine.

Examples
--------
    python -m royalscout.cli ingest --project rr-scouting --name "RR Domestic 2025" \
        --paths ../data/uploads --storage ../storage --fixture

    python -m royalscout.cli worker --storage ../storage --once
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from .config import DEFAULT_CONFIG
from .pipeline import run_pipeline
from .store import ArtifactStore


def _progress(stage: str, pct: float, detail: str) -> None:
    print(f"[{pct:5.1f}%] {stage:<32} {detail}", file=sys.stderr, flush=True)


def cmd_ingest(args: argparse.Namespace) -> int:
    sources = [Path(p) for p in args.paths]
    missing = [p for p in sources if not p.exists()]
    if missing:
        print(f"error: path(s) not found: {missing}", file=sys.stderr)
        return 2
    dataset_id = args.dataset_id or f"ds_{uuid.uuid4().hex[:12]}"
    bundle = run_pipeline(
        sources=sources, storage_root=Path(args.storage), project_id=args.project,
        dataset_id=dataset_id, dataset_name=args.name, cfg=DEFAULT_CONFIG,
        is_fixture=args.fixture, progress=_progress, export=not args.no_export)
    out = ArtifactStore(Path(args.storage)).dataset_dir(args.project, dataset_id) / "bundle.json"
    print(json.dumps({
        "dataset_id": dataset_id, "bundle": str(out),
        "batters_ranked": len(bundle["leaderboards"]["global"]["batters"]),
        "bowlers_ranked": len(bundle["leaderboards"]["global"]["bowlers"]),
        "quality_score": bundle["quality"]["score"],
        "files": bundle["ingestion"]["summary"],
    }, indent=2))
    if args.publish:
        dest = Path(args.publish)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(bundle, default=str), encoding="utf-8")
        print(json.dumps({"published": str(dest), "bytes": dest.stat().st_size}))
    return 0


def cmd_worker(args: argparse.Namespace) -> int:
    from .worker import run_worker
    return run_worker(storage=Path(args.storage), once=args.once, interval=args.interval,
                      max_jobs=args.max_jobs)


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn
    uvicorn.run("royalscout.api:app", host=args.host, port=args.port, reload=False,
                log_level=args.log_level)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="royalscout", description="Royal Scout intelligence engine")
    sub = p.add_subparsers(dest="command", required=True)

    ing = sub.add_parser("ingest", help="run the full pipeline over files/directories")
    ing.add_argument("--paths", nargs="+", required=True)
    ing.add_argument("--project", default="default")
    ing.add_argument("--dataset-id", default=None)
    ing.add_argument("--name", default="Untitled dataset")
    ing.add_argument("--storage", default="./storage")
    ing.add_argument("--fixture", action="store_true", help="mark as synthetic test data")
    ing.add_argument("--no-export", action="store_true")
    ing.add_argument("--publish", default=None, help="also write the bundle to this path")
    ing.set_defaults(func=cmd_ingest)

    wk = sub.add_parser("worker", help="poll the job queue and process jobs")
    wk.add_argument("--storage", default="./storage")
    wk.add_argument("--once", action="store_true")
    wk.add_argument("--interval", type=float, default=5.0)
    wk.add_argument("--max-jobs", type=int, default=0)
    wk.set_defaults(func=cmd_worker)

    sv = sub.add_parser("serve", help="run the worker HTTP API")
    sv.add_argument("--host", default="0.0.0.0")
    sv.add_argument("--port", type=int, default=8080)
    sv.add_argument("--log-level", default="info")
    sv.set_defaults(func=cmd_serve)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
