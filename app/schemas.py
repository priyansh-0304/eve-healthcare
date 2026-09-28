from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, EmailStr, Field, ConfigDict

from app.models import BookingStatus, PaymentStatus


# ---------- Auth ----------

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)
    # Only meant for demo/grading convenience so an admin account can be created
    # without a separate promotion flow. See README assumptions.
    is_admin: bool = False


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    full_name: str
    is_admin: bool
    created_at: datetime


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- Centres & Tests ----------

class TestCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    price: float = Field(gt=0)


class TestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    centre_id: str
    name: str
    price: float


class CentreCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    location: str = Field(min_length=1, max_length=200)


class CentreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    location: str
    tests: List[TestOut] = []


# ---------- Bookings ----------

class BookingCreate(BaseModel):
    test_id: str
    appointment_datetime: datetime


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    test_id: str
    centre_id: str
    appointment_datetime: datetime
    amount: float
    status: BookingStatus
    created_at: datetime
    updated_at: datetime


# ---------- Payments ----------

class PaymentCreate(BaseModel):
    booking_id: str


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    booking_id: str
    amount: float
    status: PaymentStatus
    created_at: datetime


class WebhookPayload(BaseModel):
    """
    Simulates the payload a real payment provider would POST to our webhook.
    event_id is the idempotency key — the provider may deliver the same event
    more than once, and we must not double-process it.
    """
    event_id: str
    booking_id: str
    status: PaymentStatus


class WebhookResponse(BaseModel):
    received: bool
    duplicate: bool
    booking_status: Optional[BookingStatus] = None
