from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.services.payment_service import simulate_payment, process_webhook_event

router = APIRouter(prefix="/payments", tags=["payments"])

# Lightweight per-IP rate limiting on the payment-facing endpoints (bonus:
# rate limiting). Webhook and payment-initiation endpoints are the most
# sensitive to abuse/retries, so they're the ones limited here.
limiter = Limiter(key_func=get_remote_address)


def _get_payable_booking(db: Session, booking_id: str, user: models.User) -> models.Booking:
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    if booking.user_id != user.id and not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to pay for this booking",
        )
    if booking.status == models.BookingStatus.CONFIRMED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Booking is already paid for")
    if booking.status == models.BookingStatus.CANCELLED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot pay for a cancelled booking")
    return booking


@router.post("/", response_model=schemas.PaymentOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def initiate_payment(
    request: Request,
    payload: schemas.PaymentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Mock payment endpoint. In a real integration this would redirect to /
    call out to a payment gateway and return a pending state; here we
    synchronously simulate the provider's decision.
    """
    booking = _get_payable_booking(db, payload.booking_id, current_user)
    payment = simulate_payment(db, booking)
    return payment


@router.post("/webhook/", response_model=schemas.WebhookResponse)
@limiter.limit("30/minute")
def payment_webhook(
    request: Request,
    payload: schemas.WebhookPayload,
    db: Session = Depends(get_db),
    x_webhook_secret: str = Header(default=""),
):
    """
    Simulated payment-provider webhook. Must be idempotent: re-delivering the
    same event_id must not create duplicate payments or corrupt booking state
    (see app/services/payment_service.process_webhook_event).
    """
    if x_webhook_secret != settings.webhook_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook secret")

    booking = db.query(models.Booking).filter(models.Booking.id == payload.booking_id).first()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")

    booking, was_duplicate = process_webhook_event(
        db=db,
        event_id=payload.event_id,
        booking=booking,
        payload_status=payload.status,
    )

    return schemas.WebhookResponse(
        received=True,
        duplicate=was_duplicate,
        booking_status=booking.status,
    )
