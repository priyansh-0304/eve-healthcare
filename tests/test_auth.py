from tests.conftest import register_user, auth_headers


def test_signup_returns_token(client):
    token = register_user(client)
    assert token


def test_duplicate_signup_fails(client):
    register_user(client, email="dupe@example.com")
    resp = client.post(
        "/auth/signup",
        json={"email": "dupe@example.com", "password": "password123", "full_name": "Dupe"},
    )
    assert resp.status_code == 400


def test_login_success(client):
    register_user(client, email="login@example.com", password="correcthorse")
    resp = client.post(
        "/auth/login",
        data={"username": "login@example.com", "password": "correcthorse"},
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_wrong_password_fails(client):
    register_user(client, email="login2@example.com", password="correcthorse")
    resp = client.post(
        "/auth/login",
        data={"username": "login2@example.com", "password": "wrongpassword"},
    )
    assert resp.status_code == 401


def test_protected_route_without_token_fails(client):
    resp = client.get("/bookings/")
    assert resp.status_code == 401


def test_protected_route_with_invalid_token_fails(client):
    resp = client.get("/bookings/", headers=auth_headers("not-a-real-token"))
    assert resp.status_code == 401
