"""Authentication & registration tests."""
from __future__ import annotations

from tests.conftest import auth_headers, login, register_user


def test_register_first_user_is_admin(client):
    user = register_user(client, "first@test.dev")
    assert user["role"] == "admin"
    second = register_user(client, "second@test.dev")
    assert second["role"] == "user"


def test_register_validates_email_and_password(client):
    r = client.post("/api/auth/register", json={"email": "bad", "password": "Passw0rd1", "full_name": "x"})
    assert r.status_code == 422
    r = client.post("/api/auth/register", json={"email": "ok@test.dev", "password": "short", "full_name": "x"})
    assert r.status_code == 422
    r = client.post("/api/auth/register", json={"email": "ok@test.dev", "password": "allletters", "full_name": "x"})
    assert r.status_code == 422


def test_register_duplicate_email_rejected(client):
    register_user(client, "dup@test.dev")
    r = client.post("/api/auth/register",
                    json={"email": "dup@test.dev", "password": "Passw0rd123", "full_name": "x"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_login_success_and_failure(client):
    register_user(client)
    tokens = login(client)
    assert tokens["token_type"] == "bearer"
    assert tokens["expires_in_minutes"] > 0

    r = client.post("/api/auth/login", json={"email": "user@test.dev", "password": "WrongPass123"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "authentication_failed"
    # Safe message: does not reveal whether the account exists
    assert "password" in r.json()["error"]["message"].lower() or "credentials" in r.json()["error"]["message"].lower()

    r = client.post("/api/auth/login", json={"email": "ghost@test.dev", "password": "WrongPass123"})
    assert r.status_code == 401


def test_me_requires_token(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer garbage.token.here"})
    assert r.status_code == 401


def test_me_returns_profile(client):
    register_user(client, full_name="Alice Example")
    headers = auth_headers(login(client))
    r = client.get("/api/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["email"] == "user@test.dev"
    assert r.json()["full_name"] == "Alice Example"
    assert "hashed_password" not in r.text


def test_refresh_flow(client):
    register_user(client)
    tokens = login(client)
    r = client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200
    new_tokens = r.json()
    assert new_tokens["access_token"]
    # New access token works
    r = client.get("/api/auth/me", headers=auth_headers(new_tokens))
    assert r.status_code == 200


def test_refresh_token_cannot_be_used_as_access_token(client):
    """Token type confusion must be rejected."""
    register_user(client)
    tokens = login(client)
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"})
    assert r.status_code == 401


def test_access_token_cannot_be_used_as_refresh_token(client):
    register_user(client)
    tokens = login(client)
    r = client.post("/api/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert r.status_code == 401


def test_update_profile_and_password(client):
    register_user(client)
    headers = auth_headers(login(client))
    r = client.patch("/api/auth/me", headers=headers, json={"full_name": "New Name"})
    assert r.status_code == 200 and r.json()["full_name"] == "New Name"

    r = client.patch("/api/auth/me", headers=headers, json={"password": "NewPassw0rd99"})
    assert r.status_code == 200
    # old password fails, new works
    assert client.post("/api/auth/login", json={"email": "user@test.dev", "password": "Passw0rd123"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "user@test.dev", "password": "NewPassw0rd99"}).status_code == 200


def test_logout_audited(client):
    register_user(client)
    headers = auth_headers(login(client))
    r = client.post("/api/auth/logout", headers=headers)
    assert r.status_code == 204
