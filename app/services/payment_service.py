import logging
import random

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.config import settings

logger = logging.getLogger("eve.payments")


def roll_payment_outcome() -> models.PaymentStatus:
    """
    Isolated in its own function (rather than inlined) so tests can monkeypatch
    it to force a deterministic SUCCESS/FAILED outcome instead of depending on
    real randomness.
    """
    return (
        models.PaymentStatus.SUCCESS
        if random.random() < settings.payment_success_rate
        else models.PaymentStatus.FAILED
    )


def simulate_payment(db: Session, booking: models.Booking) -> models.Payment:
    """
    Creates a Payment record for a booking and simulates a provider deciding
    SUCCESS or FAILED, then updates the booking status to match.

    Guardrails:
    - A booking that is already CONFIRMED cannot be paid again.
    - A CANCELLED booking cannot be paid.
    """
    outcome = roll_payment_outcome()

    payment = models.Payment(
        booking_id=booking.id,
        amount=booking.amount,
        status=outcome,
    )
    db.add(payment)

    booking.status = (
        models.BookingStatus.CONFIRMED
        if outcome == models.PaymentStatus.SUCCESS
        else models.BookingStatus.FAILED
    )

    db.commit()
    db.refresh(payment)
    db.refresh(booking)

    logger.info(
        "payment_simulated booking_id=%s payment_id=%s outcome=%s",
        booking.id, payment.id, outcome.value,
    )
    return payment


def process_webhook_event(
    db: Session,
    event_id: str,
    booking: models.Booking,
    payload_status: models.PaymentStatus,
) -> tuple[models.Booking, bool]:
    """
    Applies a webhook's payment-status update to a booking, idempotently.

    Returns (booking, was_duplicate). If event_id has already been recorded,
    the booking is returned unchanged and was_duplicate=True — no new Payment
    row is created and the booking status is not touched again.

    Idempotency is enforced by a unique constraint on webhook_events.event_id:
    even under concurrent duplicate deliveries, only one insert can win: the
    DB is the source of truth, not an in-memory check.
    """
    existing = (
        db.query(models.WebhookEvent)
        .filter(models.WebhookEvent.event_id == event_id)
        .first()
    )
    if existing is not None:
        logger.info("webhook_duplicate_ignored event_id=%s booking_id=%s", event_id, booking.id)
        return booking, True

    event = models.WebhookEvent(
        event_id=event_id,
        booking_id=booking.id,
        payload_status=payload_status.value,
    )
    db.add(event)

    # A CANCELLED booking should never be flipped back to CONFIRMED/FAILED by a
    # late-arriving webhook.
    if booking.status != models.BookingStatus.CANCELLED:
        booking.status = (
            models.BookingStatus.CONFIRMED
            if payload_status == models.PaymentStatus.SUCCESS
            else models.BookingStatus.FAILED
        )

    payment = models.Payment(
        booking_id=booking.id,
        amount=booking.amount,
        status=payload_status,
    )
    db.add(payment)

    try:
        db.commit()
    except IntegrityError:
        # Belt-and-braces: two concurrent deliveries of the same event both
        # passed the existence check above before either committed. The
        # unique constraint on event_id is the real source of truth here —
        # whichever request loses the race backs off and reports a duplicate.
        db.rollback()
        logger.info("webhook_duplicate_race event_id=%s booking_id=%s", event_id, booking.id)
        return booking, True

    db.refresh(booking)

    logger.info("webhook_processed event_id=%s booking_id=%s status=%s", event_id, booking.id, payload_status.value)
    return booking, False
