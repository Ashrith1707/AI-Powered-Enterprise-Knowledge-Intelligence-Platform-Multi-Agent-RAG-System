from tests.conftest import TEST_USER


def test_register_login_me_flow(anon_client):
    res = anon_client.post("/api/auth/register", json=TEST_USER)
    assert res.status_code == 201
    body = res.json()
    assert body["user"]["role"] == "admin"          # first user becomes admin
    assert "access_token" in body and "refresh_token" in body

    res = anon_client.post("/api/auth/login", json={
        "email": TEST_USER["email"], "password": TEST_USER["password"]})
    assert res.status_code == 200
    token = res.json()["access_token"]

    res = anon_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["email"] == TEST_USER["email"]


def test_wrong_password_rejected(anon_client):
    anon_client.post("/api/auth/register", json=TEST_USER)
    res = anon_client.post("/api/auth/login", json={
        "email": TEST_USER["email"], "password": "wrong-password"})
    assert res.status_code == 401


def test_duplicate_email_rejected(anon_client):
    anon_client.post("/api/auth/register", json=TEST_USER)
    res = anon_client.post("/api/auth/register", json=TEST_USER)
    assert res.status_code == 400


def test_protected_endpoint_requires_token(anon_client):
    assert anon_client.get("/api/documents").status_code == 401
    assert anon_client.get("/api/analytics/dashboard").status_code == 401


def test_refresh_rotation(anon_client):
    res = anon_client.post("/api/auth/register", json=TEST_USER)
    refresh = res.json()["refresh_token"]

    res = anon_client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert res.status_code == 200
    new_refresh = res.json()["refresh_token"]
    assert new_refresh != refresh

    # Old token was rotated out — reuse must fail.
    res = anon_client.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert res.status_code == 401

    # New one still works.
    res = anon_client.post("/api/auth/refresh", json={"refresh_token": new_refresh})
    assert res.status_code == 200


def test_logout_revokes_refresh(anon_client):
    res = anon_client.post("/api/auth/register", json=TEST_USER)
    refresh = res.json()["refresh_token"]
    assert anon_client.post("/api/auth/logout",
                            json={"refresh_token": refresh}).status_code == 204
    assert anon_client.post("/api/auth/refresh",
                            json={"refresh_token": refresh}).status_code == 401


def test_second_user_is_analyst(anon_client):
    anon_client.post("/api/auth/register", json=TEST_USER)
    res = anon_client.post("/api/auth/register", json={
        "email": "second@corp.com", "password": "AnotherPass1!"})
    assert res.json()["user"]["role"] == "analyst"
