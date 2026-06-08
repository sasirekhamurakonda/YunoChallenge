import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, ForeignKey
from src.database import Base


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_uuid() -> str:
    return str(uuid.uuid4())


class CaptureAttempt(Base):
    __tablename__ = "capture_attempts"

    id = Column(String, primary_key=True, default=new_uuid)
    scheduled_capture_id = Column(
        String,
        ForeignKey("scheduled_captures.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_number = Column(Integer, nullable=False)
    status = Column(String(10), nullable=False)
    failure_reason = Column(String(100), nullable=True)
    gateway_response = Column(String, nullable=True)
    attempted_at = Column(String, nullable=False, default=utcnow)
    duration_ms = Column(Integer, nullable=True)
