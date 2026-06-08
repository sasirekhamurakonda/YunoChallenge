import math
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple

from sqlalchemy.orm import Session

from src.exceptions import AppException
from src.models.scheduled_capture import ScheduledCapture, new_uuid, utcnow
from src.models.capture_attempt import CaptureAttempt
from src.schemas.capture import CreateCaptureRequest
from src.schemas.stats import AlertItem, AlertsResponse, StatsResponse, StatsWindow, StatsTotals
from src.config import settings


def create_capture(db: Session, request: CreateCaptureRequest) -> ScheduledCapture:
    existing = (
        db.query(ScheduledCapture)
        .filter(
            ScheduledCapture.payment_reference == request.payment_reference,
            ScheduledCapture.status != "cancelled",
        )
        .first()
    )
    if existing:
        raise AppException(
            status_code=409,
            message="A scheduled capture with this payment_reference already exists.",
            code="DUPLICATE_PAYMENT_REFERENCE",
        )

    capture = ScheduledCapture(
        id=new_uuid(),
        booking_id=request.booking_id,
        payment_reference=request.payment_reference,
        amount=request.amount,
        currency=request.currency,
        status="pending",
        scheduled_capture_at=request.scheduled_capture_at.isoformat(),
        auth_expires_at=request.auth_expires_at.isoformat() if request.auth_expires_at else None,
        retry_count=0,
        max_retries=settings.max_retries,
    )
    db.add(capture)
    db.commit()
    db.refresh(capture)
    return capture


def get_capture(db: Session, capture_id: str) -> ScheduledCapture:
    capture = db.query(ScheduledCapture).filter(ScheduledCapture.id == capture_id).first()
    if not capture:
        raise AppException(
            status_code=404,
            message="Scheduled capture not found.",
            code="CAPTURE_NOT_FOUND",
        )
    return capture


def list_captures(
    db: Session,
    status: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    booking_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> Tuple[List[ScheduledCapture], int]:
    query = db.query(ScheduledCapture)
    if status:
        query = query.filter(ScheduledCapture.status == status)
    if date_from:
        query = query.filter(ScheduledCapture.scheduled_capture_at >= date_from.isoformat())
    if date_to:
        query = query.filter(ScheduledCapture.scheduled_capture_at <= date_to.isoformat())
    if booking_id:
        query = query.filter(ScheduledCapture.booking_id == booking_id)

    total = query.count()
    items = (
        query.order_by(ScheduledCapture.scheduled_capture_at)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return items, total


def cancel_capture(db: Session, capture_id: str) -> ScheduledCapture:
    capture = get_capture(db, capture_id)
    if capture.status not in ("pending", "retrying"):
        raise AppException(
            status_code=409,
            message=f"Cannot cancel a capture in status '{capture.status}'.",
            code="INVALID_STATUS_TRANSITION",
        )
    capture.status = "cancelled"
    capture.cancelled_at = utcnow()
    capture.updated_at = utcnow()
    db.commit()
    db.refresh(capture)
    return capture


def list_attempts(db: Session, capture_id: str) -> List[CaptureAttempt]:
    get_capture(db, capture_id)
    return (
        db.query(CaptureAttempt)
        .filter(CaptureAttempt.scheduled_capture_id == capture_id)
        .order_by(CaptureAttempt.attempt_number)
        .all()
    )


def get_alerts(
    db: Session,
    alert_type: Optional[str] = None,
    threshold_hours: int = 48,
) -> AlertsResponse:
    now = datetime.now(timezone.utc)
    alerts: List[AlertItem] = []

    if alert_type in (None, "scheduling_conflict"):
        conflicts = (
            db.query(ScheduledCapture)
            .filter(
                ScheduledCapture.auth_expires_at.isnot(None),
                ScheduledCapture.scheduled_capture_at > ScheduledCapture.auth_expires_at,
                ScheduledCapture.status.in_(["pending", "retrying"]),
            )
            .all()
        )
        for c in conflicts:
            expires_dt = _parse_dt(c.auth_expires_at)
            hours_until = (expires_dt - now).total_seconds() / 3600
            alerts.append(
                AlertItem(
                    capture_id=c.id,
                    booking_id=c.booking_id,
                    payment_reference=c.payment_reference,
                    amount=c.amount,
                    currency=c.currency,
                    status=c.status,
                    alert_type="scheduling_conflict",
                    alert_message=(
                        f"Capture scheduled for {c.scheduled_capture_at[:10]} but "
                        f"authorization expires {c.auth_expires_at[:10]}"
                    ),
                    scheduled_capture_at=c.scheduled_capture_at,
                    auth_expires_at=c.auth_expires_at,
                    hours_until_expiry=round(hours_until, 1),
                )
            )

    if alert_type in (None, "expiry_imminent"):
        threshold_dt = now + timedelta(hours=threshold_hours)
        imminent = (
            db.query(ScheduledCapture)
            .filter(
                ScheduledCapture.auth_expires_at.isnot(None),
                ScheduledCapture.auth_expires_at <= threshold_dt.isoformat(),
                ScheduledCapture.auth_expires_at > now.isoformat(),
                ScheduledCapture.status.in_(["pending", "retrying"]),
                ScheduledCapture.scheduled_capture_at <= ScheduledCapture.auth_expires_at,
            )
            .all()
        )
        for c in imminent:
            expires_dt = _parse_dt(c.auth_expires_at)
            hours_until = (expires_dt - now).total_seconds() / 3600
            alerts.append(
                AlertItem(
                    capture_id=c.id,
                    booking_id=c.booking_id,
                    payment_reference=c.payment_reference,
                    amount=c.amount,
                    currency=c.currency,
                    status=c.status,
                    alert_type="expiry_imminent",
                    alert_message=(
                        f"Authorization expires in {hours_until:.1f} hours, "
                        f"capture still {c.status}"
                    ),
                    scheduled_capture_at=c.scheduled_capture_at,
                    auth_expires_at=c.auth_expires_at,
                    hours_until_expiry=round(hours_until, 1),
                )
            )

    return AlertsResponse(alerts=alerts, total=len(alerts))


def get_stats(
    db: Session,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> StatsResponse:
    query = db.query(ScheduledCapture)
    if date_from:
        query = query.filter(ScheduledCapture.scheduled_capture_at >= date_from.isoformat())
    if date_to:
        query = query.filter(ScheduledCapture.scheduled_capture_at <= date_to.isoformat())

    all_captures = query.all()
    totals = StatsTotals(
        scheduled=len(all_captures),
        captured=sum(1 for c in all_captures if c.status == "captured"),
        failed=sum(1 for c in all_captures if c.status == "failed"),
        retrying=sum(1 for c in all_captures if c.status == "retrying"),
        pending=sum(1 for c in all_captures if c.status == "pending"),
        cancelled=sum(1 for c in all_captures if c.status == "cancelled"),
        processing=sum(1 for c in all_captures if c.status == "processing"),
    )

    terminal = totals.captured + totals.failed
    success_rate = round((totals.captured / terminal * 100) if terminal > 0 else 0.0, 2)

    latencies = []
    for c in all_captures:
        if c.status == "captured" and c.captured_at and c.scheduled_capture_at:
            try:
                scheduled = _parse_dt(c.scheduled_capture_at)
                captured = _parse_dt(c.captured_at)
                latencies.append((captured - scheduled).total_seconds() / 3600)
            except Exception:
                pass
    avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else None

    ids = [c.id for c in all_captures]
    breakdown: dict = {}
    if ids:
        for attempt in (
            db.query(CaptureAttempt)
            .filter(
                CaptureAttempt.scheduled_capture_id.in_(ids),
                CaptureAttempt.status == "failure",
                CaptureAttempt.failure_reason.isnot(None),
            )
            .all()
        ):
            breakdown[attempt.failure_reason] = breakdown.get(attempt.failure_reason, 0) + 1

    return StatsResponse(
        window=StatsWindow(
            date_from=date_from.isoformat() if date_from else None,
            date_to=date_to.isoformat() if date_to else None,
        ),
        totals=totals,
        success_rate_pct=success_rate,
        avg_capture_latency_hours=avg_latency,
        failure_breakdown=breakdown,
    )


def _parse_dt(iso_str: str) -> datetime:
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
