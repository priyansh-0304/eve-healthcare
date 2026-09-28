from datetime import datetime, timedelta, timezone

from tests.conftest import auth_headers, register_user


def _future(days=2):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def test_create_booking_success(client, user_token, centre_and_test):
    centre, test = centre_and_test
    resp = client.post(
        "/bookings/",
        json={"test_id": test["id"], "appointment_datetime": _future()},
        headers=auth_headers(user_token),
    )
    assert resp.status_code == 201, resp.text
    booking = resp.json()
    assert booking["status"] == "PENDING"
    assert booking["amount"] == test["price"]
    assert booking["centre_id"] == centre["id"]


def test_create_booking_past_date_fails(client, user_token, centre_and_test):
    _, test = centre_and_test
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    resp = client.post(
        "/bookings/",
        json={"test_id": test["id"], "appointment_datetime": past},
        headers=auth_headers(user_token),
    )
    assert resp.status_code == 400


def test_create_booking_invalid_test_fails(client, user_token):
    resp = client.post(
        "/bookings/",
        json={"test_id": "does-not-exist", "appointment_datetime": _future()},
        headers=auth_headers(user_token),
    )
    assert resp.status_code == 404


def test_create_booking_requires_auth(client, centre_and_test):
    _, test = centre_and_test
    resp = client.post(
        "/bookings/",
        json={"test_id": test["id"], "appointment_datetime": _future()},
    )
    assert resp.status_code == 401


def test_cannot_view_another_users_booking(client, user_token, centre_and_test):
    _, test = centre_and_test
    booking = client.post(
        "/bookings/",
        json={"test_id": test["id"], "appointment_datetime": _future()},
        headers=auth_headers(user_token),
    ).json()

    other_token = register_user(client, email="other@example.com")
    resp = client.get(f"/bookings/{booking['id']}", headers=auth_headers(other_token))
    assert resp.status_code == 403


def test_cancel_booking_success(client, user_token, centre_and_test):
    _, test = centre_and_test
    booking = client.post(
        "/bookings/",
        json={"test_id": test["id"], "appointment_datetime": _future()},
        headers=auth_headers(user_token),
    ).json()

    resp = client.patch(f"/bookings/{booking['id']}/cancel", headers=auth_headers(user_token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"


def test_cancel_already_cancelled_booking_fails(client, user_token, centre_and_test):
    _, test = centre_and_test
    booking = client.post(
        "/bookings/",
        json={"test_id": test["id"], "appointment_datetime": _future()},
        headers=auth_headers(user_token),
    ).json()
    client.patch(f"/bookings/{booking['id']}/cancel", headers=auth_headers(user_token))

    resp = client.patch(f"/bookings/{booking['id']}/cancel", headers=auth_headers(user_token))
    assert resp.status_code == 400


def test_cannot_cancel_another_users_booking(client, user_token, centre_and_test):
    _, test = centre_and_test
    booking = client.post(
        "/bookings/",
        json={"test_id": test["id"], "appointment_datetime": _future()},
        headers=auth_headers(user_token),
    ).json()

    other_token = register_user(client, email="other2@example.com")
    resp = client.patch(f"/bookings/{booking['id']}/cancel", headers=auth_headers(other_token))
    assert resp.status_code == 403
