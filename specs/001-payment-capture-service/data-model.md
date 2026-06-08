# Data Model: Payment Capture Scheduling Service

**Phase**: 1 — Design & Contracts
**Date**: 2026-06-08
**Feature**: 001-payment-capture-service
**Database**: SQLite (WAL mode) via SQLAlchemy 2.x sync ORM

---

## Entities

### 1. ScheduledCapture

The core domain entity. One row per authorized payment that has been scheduled for delayed capture.

**Table**: `scheduled_captures`

| Column | SQLite Type | Constraints | Description |
|--------|-------------|-------------|-------------|
| `id` | TEXT | PK, default `uuid4()` in Python | UUID as string |
| `booking_id` | TEXT | NOT NULL | Serenity booking ref (e.g., `SC-2026-00123`) |
| `payment_reference` | TEXT | NOT NULL, UNIQUE | Yuno auth reference — idempotency key |
| `amount` | REAL | NOT NULL, CHECK (amount > 0) | Capture amount (e.g., 1250.00) |
| `currency` | TEXT | NOT NULL, DEFAULT 'EUR' | ISO 4217 code |
| `status` | TEXT | NOT NULL, DEFAULT 'pending' | See Status FSM below |
| `scheduled_capture_at` | TEXT | NOT NULL | ISO 8601 UTC datetime string |
| `auth_expires_at` | TEXT | NULLABLE | Auth expiry; used for deadline alerts |
| `retry_count` | INTEGER | NOT NULL, DEFAULT 0 | Retries attempted so far |
| `max_retries` | INTEGER | NOT NULL, DEFAULT 3 | Max retries before permanent failure |
| `next_retry_at` | TEXT | NULLABLE | When to retry next (set during backoff) |
| `failure_reason` | TEXT | NULLABLE | Last failure code on terminal failure |
| `captured_at` | TEXT | NULLABLE | Timestamp when capture succeeded |
| `cancelled_at` | TEXT | NULLABLE | Timestamp when capture was cancelled |
| `created_at` | TEXT | NOT NULL, default now() in Python | Record creation time |
| `updated_at` | TEXT | NOT NULL, updated on every write | Last modification time |

> All datetimes stored as ISO 8601 UTC strings (`2026-07-15T09:00:00Z`). SQLAlchemy `DateTime` with `timezone=True` handles serialization. SQLite does not have a native datetime type — this is standard practice.

---

### 2. CaptureAttempt

Immutable audit log. One row per execution attempt (including retries). Never updated, only inserted.

**Table**: `capture_attempts`

| Column | SQLite Type | Constraints | Description |
|--------|-------------|-------------|-------------|
| `id` | TEXT | PK, default `uuid4()` in Python | UUID as string |
| `scheduled_capture_id` | TEXT | NOT NULL, FK → scheduled_captures(id) | Parent capture |
| `attempt_number` | INTEGER | NOT NULL | 1-based sequence (1 = first attempt) |
| `status` | TEXT | NOT NULL | `success` or `failure` |
| `failure_reason` | TEXT | NULLABLE | Failure code if status = failure |
| `gateway_response` | TEXT | NULLABLE | JSON-serialized gateway payload |
| `attempted_at` | TEXT | NOT NULL, default now() | When this attempt was made |
| `duration_ms` | INTEGER | NULLABLE | Gateway call duration in ms |

> `gateway_response` is stored as a JSON string (TEXT) — parsed/serialized in the service layer. SQLite has no native JSONB; this is equivalent for demo purposes.

---

## Status Values

```python
class CaptureStatus(str, Enum):
    pending    = "pending"     # waiting for scheduled_capture_at
    processing = "processing"  # locked by execution engine (in-flight)
    captured   = "captured"    # successfully captured (terminal)
    retrying   = "retrying"    # failed; waiting for next_retry_at
    failed     = "failed"      # all retries exhausted (terminal)
    cancelled  = "cancelled"   # manually cancelled (terminal)

class AttemptStatus(str, Enum):
    success = "success"
    failure = "failure"
```

---

## State Machine: ScheduledCapture.status

```
  [POST /captures]
       │
       ▼
  ┌─────────┐   [engine polls & locks]   ┌────────────┐
  │ pending │ ─────────────────────────▶ │ processing │
  └─────────┘                            └─────┬──────┘
      ▲                                        │
      │                   ┌────────────────────┤
      │                   │                    │
      │            [success]              [failure]
      │                   │                    │
      │                   ▼                    ▼
      │             ┌──────────┐     ┌──────────────────┐
      │             │ captured │     │ retry_count       │
      │             │(terminal)│     │ < max_retries?    │
      │             └──────────┘     └──────────────────┘
      │                                   │        │
      │                               [yes]      [no]
      │                                   │        │
      │                            ┌──────────┐  ┌────────┐
      └────────────────────────────│ retrying │  │ failed │
        [next_retry_at arrives]    │          │  │(term.) │
                                   └──────────┘  └────────┘

  [POST /captures/{id}/cancel]  ←── valid from: pending, retrying
       │
       ▼
  ┌───────────┐
  │ cancelled │
  │ (terminal)│
  └───────────┘
```

**Allowed transitions**:

| From | To | Trigger |
|------|----|---------|
| `pending` | `processing` | Execution engine acquires threading.Lock |
| `pending` | `cancelled` | `POST /captures/{id}/cancel` |
| `processing` | `captured` | Gateway returns success |
| `processing` | `retrying` | Gateway fails, retries remaining |
| `processing` | `failed` | Gateway fails, no retries remaining |
| `retrying` | `processing` | `next_retry_at` arrives, engine re-locks |
| `retrying` | `cancelled` | `POST /captures/{id}/cancel` |

**Terminal states** (`captured`, `failed`, `cancelled`) — no further transitions allowed.

---

## Validation Rules

| Field | Rule |
|-------|------|
| `amount` | > 0 (Pydantic `gt=0`) |
| `currency` | 3 uppercase letters matching ISO 4217 regex `^[A-Z]{3}$` |
| `scheduled_capture_at` | Must not be more than 5 minutes in the past (configurable grace) |
| `auth_expires_at` | If provided, must be ≥ `scheduled_capture_at` (else `AUTH_EXPIRES_BEFORE_CAPTURE` error) |
| `payment_reference` | Must be unique across all non-cancelled records; 409 on duplicate |
| `booking_id` | Required, 1–100 chars |

---

## SQLAlchemy ORM Models (Python)

```python
# src/models/scheduled_capture.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, UniqueConstraint, CheckConstraint
from src.database import Base

def utcnow():
    return datetime.now(timezone.utc).isoformat()

def new_uuid():
    return str(uuid.uuid4())

class ScheduledCapture(Base):
    __tablename__ = "scheduled_captures"
    __table_args__ = (
        UniqueConstraint("payment_reference", name="uq_payment_reference"),
        CheckConstraint("amount > 0", name="ck_amount_positive"),
    )

    id                   = Column(String, primary_key=True, default=new_uuid)
    booking_id           = Column(String(100), nullable=False)
    payment_reference    = Column(String(200), nullable=False)
    amount               = Column(Float, nullable=False)
    currency             = Column(String(3), nullable=False, default="EUR")
    status               = Column(String(20), nullable=False, default="pending")
    scheduled_capture_at = Column(String, nullable=False)
    auth_expires_at      = Column(String, nullable=True)
    retry_count          = Column(Integer, nullable=False, default=0)
    max_retries          = Column(Integer, nullable=False, default=3)
    next_retry_at        = Column(String, nullable=True)
    failure_reason       = Column(String(100), nullable=True)
    captured_at          = Column(String, nullable=True)
    cancelled_at         = Column(String, nullable=True)
    created_at           = Column(String, nullable=False, default=utcnow)
    updated_at           = Column(String, nullable=False, default=utcnow, onupdate=utcnow)


# src/models/capture_attempt.py
from sqlalchemy import Column, String, Integer, ForeignKey
from src.database import Base

class CaptureAttempt(Base):
    __tablename__ = "capture_attempts"

    id                   = Column(String, primary_key=True, default=new_uuid)
    scheduled_capture_id = Column(String, ForeignKey("scheduled_captures.id"), nullable=False)
    attempt_number       = Column(Integer, nullable=False)
    status               = Column(String(10), nullable=False)
    failure_reason       = Column(String(100), nullable=True)
    gateway_response     = Column(String, nullable=True)   # JSON string
    attempted_at         = Column(String, nullable=False, default=utcnow)
    duration_ms          = Column(Integer, nullable=True)
```

---

## Indexes (via Alembic migration)

```python
# migrations/versions/001_initial_schema.py
from alembic import op
import sqlalchemy as sa

def upgrade():
    # Tables created by Base.metadata.create_all() in database.py on startup
    # Additional performance indexes:
    op.create_index("idx_sc_status_scheduled",  "scheduled_captures", ["status", "scheduled_capture_at"])
    op.create_index("idx_sc_status_next_retry", "scheduled_captures", ["status", "next_retry_at"])
    op.create_index("idx_sc_booking_id",        "scheduled_captures", ["booking_id"])
    op.create_index("idx_ca_parent",            "capture_attempts",   ["scheduled_capture_id"])
```

> Alternatively, because this is a demo with SQLite, `Base.metadata.create_all(engine)` on startup is sufficient and simpler than running Alembic — the migration file is kept for documentation and future PostgreSQL upgrade path.

---

## Relationships

```
scheduled_captures (1) ──────── (N) capture_attempts
```
