"""
Seed script: generates 100+ realistic test captures across a 60-day window.
Idempotent — checks for existing data before inserting.

Usage:
    python3 scripts/seed_data.py
"""
import json
import random
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _past(days: float) -> str:
    return (_utcnow() - timedelta(days=days)).isoformat()


def _future(days: float) -> str:
    return (_utcnow() + timedelta(days=days)).isoformat()


def _minutes_ago(minutes: float) -> str:
    return (_utcnow() - timedelta(minutes=minutes)).isoformat()


def _minutes_from_now(minutes: float) -> str:
    return (_utcnow() + timedelta(minutes=minutes)).isoformat()


_PREFIXES = ["SC", "CRU", "LUX", "MDT", "ATC", "VOY"]
_FAILURES = [
    "card_declined",
    "insufficient_funds",
    "authorization_expired",
    "network_timeout",
    "issuer_unavailable",
]


def _booking_id() -> str:
    return f"{random.choice(_PREFIXES)}-2026-{random.randint(10000, 99999)}"


def _ref() -> str:
    return f"auth_yuno_{uuid.uuid4().hex[:12]}"


def _amount() -> float:
    return round(random.uniform(200, 5000), 2)


def _attempt(capture_id: str, num: int, success: bool, when: str) -> dict:
    reason = None if success else random.choice(_FAILURES)
    return dict(
        id=str(uuid.uuid4()),
        scheduled_capture_id=capture_id,
        attempt_number=num,
        status="success" if success else "failure",
        failure_reason=reason,
        gateway_response=json.dumps({
            "gateway": "yuno_simulated",
            "success": success,
            **({"transaction_id": f"txn_sim_{uuid.uuid4().hex[:12]}"} if success else {"reason": reason}),
        }),
        attempted_at=when,
        duration_ms=random.randint(80, 380),
    )


def seed(db: Session) -> int:
    from src.models.scheduled_capture import ScheduledCapture
    from src.models.capture_attempt import CaptureAttempt

    captures = []
    attempts = []

    # 40 CAPTURED
    for _ in range(40):
        days_ago = random.uniform(1, 28)
        cid = str(uuid.uuid4())
        retries = random.randint(0, 2)
        captures.append(ScheduledCapture(
            id=cid,
            booking_id=_booking_id(),
            payment_reference=_ref(),
            amount=_amount(),
            currency="EUR",
            status="captured",
            scheduled_capture_at=_past(days_ago + 0.02),
            auth_expires_at=_future(random.uniform(1, 15)) if random.random() > 0.3 else _past(random.uniform(0.1, 3)),
            retry_count=retries,
            max_retries=3,
            captured_at=_past(days_ago),
            created_at=_past(days_ago + 7),
            updated_at=_past(days_ago),
        ))
        for r in range(retries):
            attempts.append(_attempt(cid, r + 1, False, _past(days_ago + 0.02 * (retries - r))))
        attempts.append(_attempt(cid, retries + 1, True, _past(days_ago)))

    # 15 FAILED
    for _ in range(15):
        days_ago = random.uniform(0.5, 18)
        cid = str(uuid.uuid4())
        reason = random.choice(_FAILURES)
        captures.append(ScheduledCapture(
            id=cid,
            booking_id=_booking_id(),
            payment_reference=_ref(),
            amount=_amount(),
            currency="EUR",
            status="failed",
            scheduled_capture_at=_past(days_ago),
            auth_expires_at=_past(days_ago - random.uniform(0, 1)),
            retry_count=3,
            max_retries=3,
            failure_reason=reason,
            created_at=_past(days_ago + 7),
            updated_at=_past(days_ago - 0.01),
        ))
        for r in range(3):
            attempts.append(_attempt(cid, r + 1, False, _past(days_ago - r * 0.01)))

    # 10 RETRYING
    for _ in range(10):
        cid = str(uuid.uuid4())
        retries = random.randint(1, 2)
        captures.append(ScheduledCapture(
            id=cid,
            booking_id=_booking_id(),
            payment_reference=_ref(),
            amount=_amount(),
            currency="EUR",
            status="retrying",
            scheduled_capture_at=_past(random.uniform(0.1, 3)),
            auth_expires_at=_future(random.uniform(2, 25)),
            retry_count=retries,
            max_retries=3,
            next_retry_at=_minutes_from_now(random.uniform(2, 10)),
            failure_reason=random.choice(_FAILURES),
            created_at=_past(random.uniform(1, 7)),
            updated_at=_past(0.01),
        ))
        for r in range(retries):
            attempts.append(_attempt(cid, r + 1, False, _past(0.05 + r * 0.01)))

    # 5 CANCELLED
    for _ in range(5):
        captures.append(ScheduledCapture(
            id=str(uuid.uuid4()),
            booking_id=_booking_id(),
            payment_reference=_ref(),
            amount=_amount(),
            currency="EUR",
            status="cancelled",
            scheduled_capture_at=_future(random.uniform(1, 30)),
            auth_expires_at=_future(random.uniform(35, 60)),
            retry_count=0,
            max_retries=3,
            cancelled_at=_past(random.uniform(0.1, 3)),
            created_at=_past(random.uniform(1, 10)),
            updated_at=_past(0.1),
        ))

    # 12 DUE NOW (for live demo — scheduled in the last 1–30 min)
    for _ in range(12):
        captures.append(ScheduledCapture(
            id=str(uuid.uuid4()),
            booking_id=_booking_id(),
            payment_reference=_ref(),
            amount=_amount(),
            currency="EUR",
            status="pending",
            scheduled_capture_at=_minutes_ago(random.uniform(1, 30)),
            auth_expires_at=_future(random.uniform(3, 20)),
            retry_count=0,
            max_retries=3,
            created_at=_past(7),
            updated_at=_past(0),
        ))

    # 18 FUTURE PENDING
    for _ in range(18):
        captures.append(ScheduledCapture(
            id=str(uuid.uuid4()),
            booking_id=_booking_id(),
            payment_reference=_ref(),
            amount=_amount(),
            currency="EUR",
            status="pending",
            scheduled_capture_at=_future(random.uniform(1, 30)),
            auth_expires_at=_future(random.uniform(35, 60)),
            retry_count=0,
            max_retries=3,
            created_at=_past(random.uniform(1, 10)),
            updated_at=_past(0),
        ))

    # 3 SCHEDULING CONFLICT alerts demo
    for _ in range(3):
        captures.append(ScheduledCapture(
            id=str(uuid.uuid4()),
            booking_id=_booking_id(),
            payment_reference=_ref(),
            amount=_amount(),
            currency="EUR",
            status="pending",
            scheduled_capture_at=_future(random.uniform(35, 45)),
            auth_expires_at=_future(random.uniform(25, 33)),
            retry_count=0,
            max_retries=3,
            created_at=_past(1),
            updated_at=_past(0),
        ))

    # 3 EXPIRY IMMINENT alerts demo (expires within 48h)
    for _ in range(3):
        captures.append(ScheduledCapture(
            id=str(uuid.uuid4()),
            booking_id=_booking_id(),
            payment_reference=_ref(),
            amount=_amount(),
            currency="EUR",
            status="pending",
            scheduled_capture_at=_future(random.uniform(0.5, 1.5)),
            auth_expires_at=_future(random.uniform(1, 2)),
            retry_count=0,
            max_retries=3,
            created_at=_past(1),
            updated_at=_past(0),
        ))

    db.bulk_save_objects(captures)
    db.bulk_save_objects([CaptureAttempt(**a) for a in attempts])
    db.commit()
    print(f"✅ Seeded {len(captures)} captures and {len(attempts)} attempts")
    return len(captures)


if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from src.database import SessionLocal, engine, Base
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        from src.models.scheduled_capture import ScheduledCapture
        count = db.query(ScheduledCapture).count()
        if count > 0:
            print(f"Database already has {count} records. Skipping. Use --force to override.")
            sys.exit(0)
        seed(db)
    finally:
        db.close()
