#!/usr/bin/env python3
"""Download a processed private Supabase bundle into the Next.js build snapshot.

Usage:
  python scripts/publish_bundle_from_storage.py --project royal-scout --dataset ds_...

This intentionally publishes only the bundle JSON. It does not publish raw uploads,
canonical Parquet files, or the competition-specific final-selection files.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))
from royalscout.supabase_auth import get_supabase_server_key, get_supabase_url, supabase_api_headers
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "web" / "src" / "data" / "bundle.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="Royal Scout project ID")
    parser.add_argument("--dataset", required=True, help="Processed dataset ID, e.g. ds_...")
    parser.add_argument("--bucket", default=os.getenv("SUPABASE_ARTIFACT_BUCKET", "royal-scout-artifacts"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        base_url, key = get_supabase_url(), get_supabase_server_key()
    except Exception as exc:
        print(f"Invalid Supabase server configuration: {exc}", file=sys.stderr)
        return 2
    if not args.project.replace("-", "").replace("_", "").isalnum() or not args.dataset.startswith("ds_"):
        print("Invalid project or dataset ID.", file=sys.stderr)
        return 2

    object_path = f"{args.project}/{args.dataset}/bundle.json"
    encoded = "/".join(quote(part, safe="") for part in object_path.split("/"))
    response = httpx.get(
        f"{base_url}/storage/v1/object/{quote(args.bucket, safe='')}/{encoded}",
        headers=supabase_api_headers(key=key),
        timeout=180,
    )
    if response.status_code >= 300:
        print(f"Could not download {args.bucket}/{object_path}: HTTP {response.status_code}", file=sys.stderr)
        return 1

    try:
        bundle = response.json()
    except ValueError:
        print("Storage object was not valid JSON.", file=sys.stderr)
        return 1
    meta = bundle.get("meta") or {}
    if meta.get("dataset_id") != args.dataset:
        print(f"Dataset ID mismatch: expected {args.dataset}, got {meta.get('dataset_id')!r}.", file=sys.stderr)
        return 1
    if meta.get("is_fixture"):
        print("Refusing to publish a synthetic fixture as the real production dashboard bundle.", file=sys.stderr)
        return 1
    if not bundle.get("leaderboards", {}).get("global"):
        print("Bundle is missing global leaderboards; refusing to replace the current snapshot.", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"Validated {args.project}/{args.dataset}: {len(response.content):,} bytes; would publish to {OUTPUT}")
        return 0

    backup = OUTPUT.with_name(f"bundle.backup.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
    if OUTPUT.exists():
        backup.write_bytes(OUTPUT.read_bytes())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUTPUT.with_suffix(".json.tmp")
    tmp.write_bytes(response.content)
    tmp.replace(OUTPUT)
    print(f"Published dataset {args.dataset} to {OUTPUT}")
    if backup.exists():
        print(f"Previous snapshot backed up to {backup}")
    print("Run the Vercel production build/deploy to make the new snapshot live.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
