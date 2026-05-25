"""Security tests (EX3 — Session 11 requirement).

Verifies that protected endpoints reject:
- Missing Authorization header
- Expired tokens
- Malformed / tampered tokens
"""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.security import create_access_token


@pytest.fixture
def unauth_client(client: TestClient) -> TestClient:
    """TestClient with no Authorization header, backed by the in-memory test DB."""
    client.headers.pop("Authorization", None)
    return client


# ── Missing token ──────────────────────────────────────────────────────────────

def test_exercises_no_token(unauth_client: TestClient):
    resp = unauth_client.get("/exercises/")
    assert resp.status_code == 401


def test_profile_no_token(unauth_client: TestClient):
    resp = unauth_client.get("/profile/")
    assert resp.status_code == 401


def test_analytics_summary_no_token(unauth_client: TestClient):
    resp = unauth_client.get("/analytics/summary")
    assert resp.status_code == 401


# ── Expired token ──────────────────────────────────────────────────────────────

def test_expired_token_rejected(unauth_client: TestClient):
    """A token whose exp is in the past must be rejected with 401."""
    expired = create_access_token(
        {"user_id": "fake-id", "email": "x@x.com"},
        expires_delta=timedelta(seconds=-1),
    )
    resp = unauth_client.get(
        "/exercises/",
        headers={"Authorization": f"Bearer {expired}"},
    )
    assert resp.status_code == 401


def test_expired_token_on_profile(unauth_client: TestClient):
    """Expired token also rejected on profile routes."""
    expired = create_access_token(
        {"user_id": "fake-id", "email": "x@x.com"},
        expires_delta=timedelta(seconds=-60),
    )
    resp = unauth_client.get(
        "/profile/",
        headers={"Authorization": f"Bearer {expired}"},
    )
    assert resp.status_code == 401


# ── Malformed / tampered token ─────────────────────────────────────────────────

def test_malformed_token_rejected(unauth_client: TestClient):
    resp = unauth_client.get(
        "/exercises/",
        headers={"Authorization": "Bearer not-a-valid-jwt"},
    )
    assert resp.status_code == 401


def test_wrong_scheme_rejected(unauth_client: TestClient):
    """Basic auth scheme (not Bearer) is rejected."""
    resp = unauth_client.get(
        "/exercises/",
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert resp.status_code == 401


def test_token_with_nonexistent_user(unauth_client: TestClient):
    """A valid JWT whose user_id does not exist in the DB returns 401/404."""
    fake_token = create_access_token({"user_id": "00000000-0000-0000-0000-000000000000"})
    resp = unauth_client.get(
        "/exercises/",
        headers={"Authorization": f"Bearer {fake_token}"},
    )
    # App may return 401 or 404 depending on implementation — both are acceptable
    assert resp.status_code in (401, 404)


# ── Valid token flow ───────────────────────────────────────────────────────────

def test_valid_token_accepted(client: TestClient):
    """A freshly issued token allows access to protected endpoints."""
    resp = client.get("/exercises/")
    assert resp.status_code == 200


# ── Role / scope checks ────────────────────────────────────────────────────────

def test_admin_endpoint_requires_admin_role(client: TestClient):
    """Regular user token (role=user) must be rejected by admin endpoints with 403."""
    # client fixture registers a normal user — role defaults to 'user'
    resp = client.get("/admin/stats")
    assert resp.status_code == 403


def test_admin_endpoint_rejected_without_token(unauth_client: TestClient):
    """Admin endpoint is also rejected when no token is provided."""
    resp = unauth_client.get("/admin/stats")
    assert resp.status_code == 401


def test_admin_endpoint_rejected_with_expired_token(unauth_client: TestClient):
    """Admin endpoint rejects expired tokens before even checking role."""
    expired = create_access_token(
        {"user_id": "fake-id", "email": "x@x.com", "role": "admin"},
        expires_delta=timedelta(seconds=-1),
    )
    resp = unauth_client.get(
        "/admin/stats",
        headers={"Authorization": f"Bearer {expired}"},
    )
    assert resp.status_code == 401


def test_role_claim_in_token(client: TestClient):
    """Freshly registered users receive a token with role='user' embedded."""
    import json, base64

    resp = client.post(
        "/auth/register",
        json={"email": "roletest@example.com", "password": "RoleTest1!", "name": "Role Tester"},
    )
    # May conflict if already registered — that's fine
    if resp.status_code == 409:
        resp = client.post(
            "/auth/login",
            json={"email": "roletest@example.com", "password": "RoleTest1!"},
        )
    token = resp.json()["access_token"]
    # Decode payload (middle segment, no verification needed here — just inspect)
    payload_b64 = token.split(".")[1]
    padding = 4 - len(payload_b64) % 4
    payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=" * padding))
    assert payload.get("role") == "user"
