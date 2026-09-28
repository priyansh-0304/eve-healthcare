import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    String,
    Float,
    ForeignKey,
    DateTime,
    Enum as SAEnum,
    Boolean,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class BookingStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uuid)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    # Simplification for this assignment: whoever signs up with is_admin=True can manage
    # centres/tests. A real system would gate this behind an invite/approval flow.
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)

    bookings = relationship("Booking", back_populates="user")


class DiagnosticCentre(Base):
    __tablename__ = "diagnostic_centres"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    location = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)

    tests = relationship("DiagnosticTest", back_populates="centre", cascade="all, delete-orphan")


class DiagnosticTest(Base):
    __tablename__ = "diagnostic_tests"

    id = Column(String, primary_key=True, default=_uuid)
    centre_id = Column(String, ForeignKey("diagnostic_centres.id"), nullable=False)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)

    centre = relationship("DiagnosticCentre", back_populates="tests")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    test_id = Column(String, ForeignKey("diagnostic_tests.id"), nullable=False)
    centre_id = Column(String, ForeignKey("diagnostic_centres.id"), nullable=False)
    appointment_datetime = Column(DateTime(timezone=True), nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(SAEnum(BookingStatus), default=BookingStatus.PENDING, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    user = relationship("User", back_populates="bookings")
    test = relationship("DiagnosticTest")
    centre = relationship("DiagnosticCentre")
    payments = relationship("Payment", back_populates="booking")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(String, primary_key=True, default=_uuid)
    booking_id = Column(String, ForeignKey("bookings.id"), nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(SAEnum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)

    booking = relationship("Booking", back_populates="payments")


class WebhookEvent(Base):
    """
    Records every processed webhook event_id so re-deliveries are detected and
    ignored. This is what makes POST /payments/webhook/ idempotent.
    """

    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("event_id", name="uq_webhook_event_id"),)

    id = Column(String, primary_key=True, default=_uuid)
    event_id = Column(String, nullable=False, index=True)
    booking_id = Column(String, ForeignKey("bookings.id"), nullable=False)
    payload_status = Column(String, nullable=False)
    received_at = Column(DateTime(timezone=True), default=_now)
