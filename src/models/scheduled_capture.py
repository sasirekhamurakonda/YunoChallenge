import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, UniqueConstraint, CheckConstraint
from src.database import Base


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_uuid() -> str:
    return str(uuid.uuid4())


class ScheduledCapture(Base):
    __tablename__ = "scheduled_captures"
    __table_args__ = (
        UniqueConstraint("payment_reference", name="uq_payment_reference"),
        CheckConstraint("amount > 0", name="ck_amount_positive"),
    )

    id = Column(String, primary_key=True, default=new_uuid)
    booking_id = Column(String(100), nullable=False)
    payment_reference = Column(String(200), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(3), nullable=False, default="EUR")
    status = Column(String(20), nullable=False, default="pending")
    scheduled_capture_at = Column(String, nullable=False)
    auth_expires_at = Column(String, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    next_retry_at = Column(String, nullable=True)
    failure_reason = Column(String(100), nullable=True)
    captured_at = Column(String, nullable=True)
    cancelled_at = Column(String, nullable=True)
    created_at = Column(String, nullable=False, default=utcnow)
    updated_at = Column(String, nullable=False, default=utcnow, onupdate=utcnow)
