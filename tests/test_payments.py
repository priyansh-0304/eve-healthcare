from datetime import datetime, timedelta, timezone

import app.services.payment_service as payment_service
from app.models import PaymentStatus
from tests.conftest import auth_headers, WEBHOOK_SECRET


def _future():
    return (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()


def _create_booking(client, token, test):
    resp = client.post(
        "/bookings/",
        json={"test_id": test["id"], "appointment_datetime": _future()},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_successful_payment_confirms_booking(client, user_token, centre_and_test, monkeypatch):
    monkeypatch.setattr(payment_service, "roll_payment_outcome", lambda: PaymentStatus.SUCCESS)
    _, test = centre_and_test
    booking = _create_booking(client, user_token, test)

    resp = client.post("/payments/", json={"booking_id": booking["id"]}, headers=auth_headers(user_token))
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "SUCCESS"

    booking_after = client.get(f"/bookings/{booking['id']}", headers=auth_headers(user_token)).json()
    assert booking_after["status"] == "CONFIRMED"


def test_failed_payment_marks_booking_failed(client, user_token, centre_and_test, monkeypatch):
    monkeypatch.setattr(payment_service, "roll_payment_outcome", lambda: PaymentStatus.FAILED)
    _, test = centre_and_test
    booking = _create_booking(client, user_token, test)

    resp = client.post("/payments/", json={"booking_id": booking["id"]}, headers=auth_headers(user_token))
    assert resp.status_code == 201
    assert resp.json()["status"] == "FAILED"

    booking_after = client.get(f"/bookings/{booking['id']}", headers=auth_headers(user_token)).json()
    assert booking_after["status"] == "FAILED"


def test_cannot_pay_for_already_confirmed_booking(client, user_token, centre_and_test, monkeypatch):
    monkeypatch.setattr(payment_service, "roll_payment_outcome", lambda: PaymentStatus.SUCCESS)
    _, test = centre_and_test
    booking = _create_booking(client, user_token, test)
    client.post("/payments/", json={"booking_id": booking["id"]}, headers=auth_headers(user_token))

    resp = client.post("/payments/", json={"booking_id": booking["id"]}, headers=auth_headers(user_token))
    assert resp.status_code == 400


def test_cannot_pay_for_someone_elses_booking(client, user_token, centre_and_test):
    from tests.conftest import register_user

    _, test = centre_and_test
    booking = _create_booking(client, user_token, test)

    other_token = register_user(client, email="notyours@example.com")
    resp = client.post("/payments/", json={"booking_id": booking["id"]}, headers=auth_headers(other_token))
    assert resp.status_code == 403


def test_payment_for_unknown_booking_404s(client, user_token):
    resp = client.post("/payments/", json={"booking_id": "does-not-exist"}, headers=auth_headers(user_token))
    assert resp.status_code == 404


# ---------- Webhook idempotency — the core requirement ----------

def test_webhook_confirms_pending_booking(client, user_token, centre_and_test):
    _, test = centre_and_test
    booking = _create_booking(client, user_token, test)

    resp = client.post(
        "/payments/webhook/",
        json={"event_id": "evt_1", "booking_id": booking["id"], "status": "SUCCESS"},
        headers={"X-Webhook-Secret": WEBHOOK_SECRET},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["duplicate"] is False
    assert body["booking_status"] == "CONFIRMED"


def test_duplicate_webhook_event_is_ignored(client, user_token, centre_and_test, db_session):
    _, test = centre_and_test
    booking = _create_booking(client, user_token, test)

    event = {"event_id": "evt_dupe", "booking_id": booking["id"], "status": "SUCCESS"}
    headers = {"X-Webhook-Secret": WEBHOOK_SECRET}

    first = client.post("/payments/webhook/", json=event, headers=headers)
    assert first.status_code == 200
    assert first.json()["duplicate"] is False

    # Re-deliver the exact same event three more times, as a flaky provider might.
    for _ in range(3):
        again = client.post("/payments/webhook/", json=event, headers=headers)
        assert again.status_code == 200
        assert again.json()["duplicate"] is True
        assert again.json()["booking_status"] == "CONFIRMED"

    # Exactly one Payment row should exist for this booking, not four.
    from app import models

    payments = (
        db_session.query(models.Payment)
        .filter(models.Payment.booking_id == booking["id"])
        .all()
    )
    assert len(payments) == 1


def test_webhook_wrong_secret_rejected(client, user_token, centre_and_test):
    _, test = centre_and_test
    booking = _create_booking(client, user_token, test)

    resp = client.post(
        "/payments/webhook/",
        json={"event_id": "evt_bad_secret", "booking_id": booking["id"], "status": "SUCCESS"},
        headers={"X-Webhook-Secret": "wrong-secret"},
    )
    assert resp.status_code == 401


def test_webhook_unknown_booking_404s(client):
    resp = client.post(
        "/payments/webhook/",
        json={"event_id": "evt_unknown", "booking_id": "does-not-exist", "status": "SUCCESS"},
        headers={"X-Webhook-Secret": WEBHOOK_SECRET},
    )
    assert resp.status_code == 404


def test_webhook_does_not_reopen_cancelled_booking(client, user_token, centre_and_test):
    _, test = centre_and_test
    booking = _create_booking(client, user_token, test)
    client.patch(f"/bookings/{booking['id']}/cancel", headers=auth_headers(user_token))

    resp = client.post(
        "/payments/webhook/",
        json={"event_id": "evt_after_cancel", "booking_id": booking["id"], "status": "SUCCESS"},
        headers={"X-Webhook-Secret": WEBHOOK_SECRET},
    )
    assert resp.status_code == 200
    # Booking stays CANCELLED; a late webhook must not override a cancellation.
    assert resp.json()["booking_status"] == "CANCELLED"
