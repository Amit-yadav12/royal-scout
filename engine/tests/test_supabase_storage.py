from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from royalscout.db import Job
from royalscout.store import publish_to_supabase
from royalscout.worker import fetch_sources


def test_artifact_upload_uses_secret_apikey_only_and_checks_status(monkeypatch, tmp_path):
    file_path = tmp_path / "bundle.json"
    file_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_storage-test")
    seen = {}

    def fake_post(url, headers, content, timeout):
        seen.update(url=url, headers=headers, body=content.read())
        return SimpleNamespace(status_code=200, is_success=True)

    monkeypatch.setattr("httpx.post", fake_post)
    results = publish_to_supabase([file_path], "private-artifacts", "project/dataset")
    assert results[0]["status"] == "uploaded"
    assert seen["headers"]["apikey"] == "sb_secret_storage-test"
    assert "Authorization" not in seen["headers"]
    assert seen["headers"]["x-upsert"] == "true"
    assert seen["body"] == b"{}"
    assert "/private-artifacts/project/dataset/bundle.json" in seen["url"]


def test_artifact_upload_failure_is_not_reported_as_success(monkeypatch, tmp_path):
    file_path = tmp_path / "bundle.json"
    file_path.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_storage-test")
    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: SimpleNamespace(status_code=403, is_success=False))
    result = publish_to_supabase([file_path], "private-artifacts", "project/dataset")[0]
    assert result["status"] == "failed"
    assert result["http_status"] == 403


def test_worker_stream_download_is_confined_and_authenticates_with_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_download-test")
    monkeypatch.setenv("SUPABASE_UPLOAD_BUCKET", "uploads")

    class StreamResponse:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_bytes(self, size):
            yield b"a,b\n1,2\n"

    seen = {}

    def fake_stream(method, url, headers, timeout):
        seen.update(method=method, url=url, headers=headers)
        return StreamResponse()

    monkeypatch.setattr("httpx.stream", fake_stream)
    job = Job(id="job_0123456789abcdef", project_id="royal-scout", dataset_id="ds_0123456789abcdef",
              dataset_name="sample", sources=[{"bucket": "uploads", "path": "royal-scout/ds_0123456789abcdef/input.csv"}])
    paths = fetch_sources(job, tmp_path / "staging")
    assert len(paths) == 1 and paths[0].parent == (tmp_path / "staging").resolve()
    assert paths[0].read_bytes() == b"a,b\n1,2\n"
    assert seen["method"] == "GET"
    assert seen["headers"]["apikey"] == "sb_secret_download-test"
    assert "Authorization" not in seen["headers"]


def test_worker_rejects_unauthorised_bucket_and_production_local_path(monkeypatch, tmp_path):
    monkeypatch.setenv("RS_ENV", "production")
    job = Job(id="job_0123456789abcdef", project_id="p", dataset_id="d", dataset_name="x",
              sources=[{"bucket": "other", "path": "p/d/file.csv"}])
    try:
        fetch_sources(job, tmp_path / "stage")
    except RuntimeError as exc:
        assert "not authorised" in str(exc)
    else:
        raise AssertionError("worker accepted a non-authorised bucket")

    local_job = Job(id="job_0123456789abcdef", project_id="p", dataset_id="d", dataset_name="x",
                    sources=[{"local_path": str(tmp_path / "local.csv")}])
    try:
        fetch_sources(local_job, tmp_path / "stage")
    except RuntimeError as exc:
        assert "local_path" in str(exc)
    else:
        raise AssertionError("production worker accepted local_path")
