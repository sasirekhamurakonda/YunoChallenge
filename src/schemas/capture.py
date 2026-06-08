import re
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from pydantic import BaseModel, field_validator, model_validator, Field

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


class CreateCaptureRequest(BaseModel):
    booking_id: str = Field(min_length=1, max_length=100)
    payment_reference: str = Field(min_length=1, max_length=200)
    amount: float = Field(gt=0)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    scheduled_capture_at: datetime
    auth_expires_at: Optional[datetime] = None

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        if not _CURRENCY_RE.match(v):
            raise ValueError("currency must be a 3-letter ISO 4217 uppercase code")
        return v

    @field_validator("scheduled_capture_at")
    @classmethod
    def validate_scheduled_at(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        grace = timedelta(minutes=5)
        if v < datetime.now(timezone.utc) - grace:
            raise ValueError("scheduled_capture_at cannot be more than 5 minutes in the past")
        return v

    @field_validator("auth_expires_at")
    @classmethod
    def normalize_auth_expires(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is not None and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v

    @model_validator(mode="after")
    def validate_expires_after_scheduled(self) -> "CreateCaptureRequest":
        if self.auth_expires_at is not None:
            scheduled = self.scheduled_capture_at
            expires = self.auth_expires_at
            if scheduled.tzinfo is None:
                scheduled = scheduled.replace(tzinfo=timezone.utc)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires < scheduled:
                raise ValueError("auth_expires_at must be >= scheduled_capture_at")
        return self


class CaptureResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    booking_id: str
    payment_reference: str
    amount: float
    currency: str
    status: str
    scheduled_capture_at: str
    auth_expires_at: Optional[str] = None
    retry_count: int
    max_retries: int
    next_retry_at: Optional[str] = None
    failure_reason: Optional[str] = None
    captured_at: Optional[str] = None
    cancelled_at: Optional[str] = None
    created_at: str
    updated_at: str


class PaginatedCapturesResponse(BaseModel):
    items: List[CaptureResponse]
    total: int
    page: int
    page_size: int
    pages: int


class CaptureAttemptResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    scheduled_capture_id: str
    attempt_number: int
    status: str
    failure_reason: Optional[str] = None
    gateway_response: Optional[str] = None
    attempted_at: str
    duration_ms: Optional[int] = None
