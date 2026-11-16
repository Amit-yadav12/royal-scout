from __future__ import annotations

from royalscout.db import Job, SupabaseQueue


def test_create_serializes_only_processing_jobs_columns():
    queue = SupabaseQueue(url="https://project.supabase.co", key="sb_secret_test")
    captured = {}
    row = {"id": "job_0123456789abcdef", "project_id": "royal-scout", "dataset_id": "ds_0123456789abcdef",
           "dataset_name": "Fixture", "sources": [], "status": "queued", "progress": 0,
           "stage": "queued", "detail": "", "attempts": 0, "max_attempts": 3,
           "is_fixture": True, "result": {}, "error": None}

    def fake_req(method, path, **kwargs):
        captured.update(kwargs["json"][0])
        return [row]

    queue._req = fake_req
    job = Job(id="job_0123456789abcdef", project_id="royal-scout", dataset_id="ds_0123456789abcdef",
              dataset_name="Fixture", is_fixture=True)
    queue.create(job)
    assert "logs" not in captured
    assert set(captured) <= queue.DB_COLUMNS
    assert captured["id"] == job.id


def test_claim_uses_database_atomic_rpc():
    queue = SupabaseQueue(url="https://project.supabase.co", key="sb_secret_test")
    called = []
    row = {"id": "job_0123456789abcdef", "project_id": "royal-scout", "dataset_id": "ds_0123456789abcdef",
           "dataset_name": "Fixture", "sources": [], "status": "running", "attempts": 1}

    def fake_rpc(function, payload=None):
        called.append((function, payload))
        return [row]

    queue.rpc = fake_rpc
    assert queue.claim_next().status == "running"
    assert called == [("claim_processing_job", None)]


def test_new_secret_never_gets_bearer_header():
    queue = SupabaseQueue(url="https://project.supabase.co", key="sb_secret_test")
    headers = queue._headers({"Prefer": "return=representation"})
    assert headers["apikey"] == "sb_secret_test"
    assert "Authorization" not in headers
    assert headers["Prefer"] == "return=representation"
