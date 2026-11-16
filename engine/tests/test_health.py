from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from royalscout import api


def test_live_is_independent_of_supabase(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "STORAGE", tmp_path)
    monkeypatch.setattr(api, "SHARED_SECRET", "")
    response = TestClient(api.app).get("/health/live")
    assert response.status_code == 200
    assert response.json()["api_running"] is True


def test_readiness_performs_real_safe_dependency_probes(monkeypatch, tmp_path):
    secret = "sb_secret_private_example"
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", secret)
    monkeypatch.setenv("RS_ENV", "production")
    monkeypatch.setenv("RS_USE_SUPABASE_QUEUE", "1")
    monkeypatch.setenv("SUPABASE_ARTIFACT_BUCKET", "royal-scout-artifacts")
    monkeypatch.setattr(api, "STORAGE", tmp_path)
    monkeypatch.setattr(api, "SHARED_SECRET", "worker-secret")
    seen = []

    def fake_get(url, headers, timeout):
        seen.append((url, headers))
        return SimpleNamespace(status_code=200, is_success=True)

    monkeypatch.setattr("httpx.get", fake_get)
    response = TestClient(api.app).get("/health/ready")
    body = response.json()
    assert response.status_code == 200
    assert body["checks"]["queue_accessible"] is True
    assert body["checks"]["storage_accessible"] is True
    assert body["checks"]["supabase_key_type"] == "secret"
    assert len(seen) == 2
    assert all(headers["apikey"] == secret and "Authorization" not in headers for _, headers in seen)
    assert secret not in response.text
    assert "worker-secret" not in response.text


def test_readiness_reports_invalid_api_key_without_details(monkeypatch, tmp_path):
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_private_example")
    monkeypatch.setenv("RS_ENV", "production")
    monkeypatch.setattr(api, "STORAGE", tmp_path)
    monkeypatch.setattr(api, "SHARED_SECRET", "worker-secret")

    def unauthorized(url, headers, timeout):
        return SimpleNamespace(status_code=401, is_success=False)

    monkeypatch.setattr("httpx.get", unauthorized)
    response = TestClient(api.app).get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["checks"]["queue_diagnostic"] == "invalid_api_key"
    assert "private_example" not in response.text
