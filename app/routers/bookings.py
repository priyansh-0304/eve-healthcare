from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_current_user

router = APIRouter(prefix="/bookings", tags=["bookings"])


def _get_owned_booking_or_404(db: Session, booking_id: str, user: models.User) -> models.Booking:
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    if booking.user_id != user.id and not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this booking",
        )
    return booking


@router.post("/", response_model=schemas.BookingOut, status_code=status.HTTP_201_CREATED)
def create_booking(
    payload: schemas.BookingCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    test = db.query(models.DiagnosticTest).filter(models.DiagnosticTest.id == payload.test_id).first()
    if not test:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diagnostic test not found")

    appointment_dt = payload.appointment_datetime
    if appointment_dt.tzinfo is None:
        appointment_dt = appointment_dt.replace(tzinfo=timezone.utc)

    if appointment_dt <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Appointment datetime must be in the future",
        )

    booking = models.Booking(
        user_id=current_user.id,
        test_id=test.id,
        centre_id=test.centre_id,
        appointment_datetime=appointment_dt,
        amount=test.price,
        status=models.BookingStatus.PENDING,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


@router.get("/", response_model=List[schemas.BookingOut])
def list_my_bookings(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.Booking)
        .filter(models.Booking.user_id == current_user.id)
        .order_by(models.Booking.created_at.desc())
        .all()
    )


@router.get("/{booking_id}", response_model=schemas.BookingOut)
def get_booking(
    booking_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _get_owned_booking_or_404(db, booking_id, current_user)


@router.patch("/{booking_id}/cancel", response_model=schemas.BookingOut)
def cancel_booking(
    booking_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    booking = _get_owned_booking_or_404(db, booking_id, current_user)

    if booking.status not in (models.BookingStatus.PENDING, models.BookingStatus.CONFIRMED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel a booking with status {booking.status.value}",
        )

    booking.status = models.BookingStatus.CANCELLED
    db.commit()
    db.refresh(booking)
    return booking
