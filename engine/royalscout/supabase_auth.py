"""Central, fail-closed authentication for trusted Supabase server operations.

New sb_secret_* API keys are API keys, not JWTs: send them only as ``apikey``.
Legacy service-role JWTs remain compatible with both headers. Never log key values.
"""
from __future__ import annotations

import base64
import json
import os
import re
from urllib.parse import urlparse


class SupabaseConfigurationError(RuntimeError):
    """Invalid or missing privileged Supabase configuration."""


def validate_supabase_url(value: str) -> str:
    value = value.strip()
    parsed = urlparse(value)
    if not value or parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise SupabaseConfigurationError("SUPABASE_URL is missing or malformed")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SupabaseConfigurationError("SUPABASE_URL is malformed")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise SupabaseConfigurationError("SUPABASE_URL must use HTTPS")
    return value.rstrip("/")


def get_supabase_url() -> str:
    value = (os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").strip()
    return validate_supabase_url(value)


def _classify_key(key: str) -> str:
    if not key:
        raise SupabaseConfigurationError("A private Supabase server key is required")
    if key.startswith("sb_publishable_"):
        raise SupabaseConfigurationError("SUPABASE_SECRET_KEY must be private; publishable keys cannot authenticate backend operations")
    if key.startswith("sb_secret_"):
        if len(key) <= len("sb_secret_") or any(ch.isspace() for ch in key):
            raise SupabaseConfigurationError("SUPABASE_SECRET_KEY is malformed")
        return "secret"
    # Supabase legacy service_role keys are JWTs. Do not treat arbitrary strings
    # as bearer credentials; validate their compact-token shape without decoding/logging.
    parts = key.split(".")
    if len(parts) == 3 and all(re.fullmatch(r"[A-Za-z0-9_-]+", part) for part in parts):
        try:
            header_part = parts[0] + "=" * (-len(parts[0]) % 4)
            payload_part = parts[1] + "=" * (-len(parts[1]) % 4)
            jwt_header = json.loads(base64.urlsafe_b64decode(header_part.encode("ascii")))
            claims = json.loads(base64.urlsafe_b64decode(payload_part.encode("ascii")))
        except (ValueError, UnicodeError, json.JSONDecodeError):
            jwt_header, claims = None, None
        if (isinstance(jwt_header, dict) and isinstance(jwt_header.get("alg"), str)
                and jwt_header["alg"].lower() != "none" and isinstance(claims, dict)
                and claims.get("role") == "service_role"):
            return "legacy_jwt"
        raise SupabaseConfigurationError("Legacy Supabase JWT must be a service_role key")
    raise SupabaseConfigurationError("SUPABASE_SECRET_KEY is malformed (expected sb_secret_* or a legacy service_role JWT)")


def get_supabase_server_key() -> str:
    key = (os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    _classify_key(key)
    return key


def supabase_key_type(key: str | None = None) -> str:
    return _classify_key((key if key is not None else get_supabase_server_key()).strip())


def supabase_api_headers(extra: dict[str, str] | None = None, *, key: str | None = None) -> dict[str, str]:
    """Headers for server-key REST and Storage APIs; never for user JWT requests."""
    server_key = (key if key is not None else get_supabase_server_key()).strip()
    kind = _classify_key(server_key)
    headers = {"Content-Type": "application/json"}
    if extra:
        headers.update(extra)
    # Authentication headers are authoritative and cannot be overridden by call sites.
    headers["apikey"] = server_key
    if kind == "legacy_jwt":
        headers["Authorization"] = f"Bearer {server_key}"
    else:
        headers.pop("Authorization", None)
    return headers
