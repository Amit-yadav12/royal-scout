from __future__ import annotations

import pytest

from royalscout.supabase_auth import (
    SupabaseConfigurationError,
    get_supabase_server_key,
    get_supabase_url,
    supabase_api_headers,
    supabase_key_type,
)


def test_new_secret_is_apikey_only(monkeypatch):
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "  sb_secret_example-private  ")
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    headers = supabase_api_headers()
    assert headers["apikey"] == "sb_secret_example-private"
    assert "Authorization" not in headers
    assert headers["Content-Type"] == "application/json"
    assert supabase_key_type() == "secret"


def test_legacy_service_role_jwt_gets_both_headers(monkeypatch):
    legacy = "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0.signature"
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", legacy)
    headers = supabase_api_headers({"Prefer": "return=representation"})
    assert headers["apikey"] == legacy
    assert headers["Authorization"] == f"Bearer {legacy}"
    assert headers["Prefer"] == "return=representation"


def test_secret_key_cannot_be_overridden_with_bearer_by_extra_headers():
    headers = supabase_api_headers({"Authorization": "Bearer injected", "apikey": "injected", "Prefer": "return=representation"},
                                   key="sb_secret_private-example")
    assert headers["apikey"] == "sb_secret_private-example"
    assert "Authorization" not in headers
    assert headers["Prefer"] == "return=representation"


def test_jwt_without_service_role_claim_is_rejected():
    monkeypatch_key = "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoiYW5vbiJ9.signature"
    with pytest.raises(SupabaseConfigurationError, match="service_role"):
        supabase_api_headers(key=monkeypatch_key)


def test_secret_key_precedes_legacy_key(monkeypatch):
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_current")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "a.b.c")
    assert get_supabase_server_key() == "sb_secret_current"


def test_publishable_key_is_rejected(monkeypatch):
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_publishable_public")
    with pytest.raises(SupabaseConfigurationError, match="private"):
        supabase_api_headers()


def test_missing_private_key_fails_closed(monkeypatch):
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    with pytest.raises(SupabaseConfigurationError, match="required"):
        get_supabase_server_key()


def test_invalid_or_missing_url_fails(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "not-a-url")
    with pytest.raises(SupabaseConfigurationError, match="malformed"):
        get_supabase_url()
    monkeypatch.delenv("SUPABASE_URL")
    monkeypatch.delenv("NEXT_PUBLIC_SUPABASE_URL", raising=False)
    with pytest.raises(SupabaseConfigurationError, match="missing"):
        get_supabase_url()


def test_wrong_project_url_is_not_misreported_as_a_private_key(monkeypatch):
    # A syntactically valid but wrong project URL remains URL-shaped; live
    # connectivity checks in /health/ready determine whether it is reachable.
    monkeypatch.setenv("SUPABASE_URL", "https://wrong-project.supabase.co")
    assert get_supabase_url() == "https://wrong-project.supabase.co"
