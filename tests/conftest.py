import os

# Must be set before any `app.*` module is imported, since app.config.settings
# is built once at import time.
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("WEBHOOK_SECRET", "test-webhook-secret")
os.environ.setdefault("PAYMENT_SUCCESS_RATE", "0.8")

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, engine, SessionLocal
from app.cache import cache_delete
from app.routers.centres import CENTRES_DEFAULT_CACHE_KEY, TESTS_DEFAULT_CACHE_KEY

WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]


@pytest.fixture(autouse=True)
def _fresh_db():
    """
    Every test starts with a clean DB *and* a clean cache. The DB resets per
    test, but Redis (if reachable) doesn't know that — without this, a value
    cached by one test could leak into the next test's assertions. If Redis
    isn't running, cache_delete() is a silent no-op (see app/cache.py).
    """
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    cache_delete(CENTRES_DEFAULT_CACHE_KEY, TESTS_DEFAULT_CACHE_KEY)
    yield
    Base.metadata.drop_all(bind=engine)
    cache_delete(CENTRES_DEFAULT_CACHE_KEY, TESTS_DEFAULT_CACHE_KEY)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def register_user(client, email="user@example.com", password="password123", full_name="Test User", is_admin=False):
    resp = client.post(
        "/auth/signup",
        json={"email": email, "password": password, "full_name": full_name, "is_admin": is_admin},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["access_token"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_token(client):
    return register_user(client, email="admin@example.com", is_admin=True)


@pytest.fixture
def user_token(client):
    return register_user(client, email="patient@example.com", is_admin=False)


@pytest.fixture
def centre_and_test(client, admin_token):
    """Creates one diagnostic centre with one test under it, via the admin API."""
    centre_resp = client.post(
        "/centres/",
        json={"name": "City Diagnostics", "location": "Delhi"},
        headers=auth_headers(admin_token),
    )
    assert centre_resp.status_code == 201, centre_resp.text
    centre = centre_resp.json()

    test_resp = client.post(
        f"/centres/{centre['id']}/tests/",
        json={"name": "Complete Blood Count", "price": 499.0},
        headers=auth_headers(admin_token),
    )
    assert test_resp.status_code == 201, test_resp.text
    test = test_resp.json()

    return centre, test
