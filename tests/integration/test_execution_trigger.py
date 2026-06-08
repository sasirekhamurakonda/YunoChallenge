import uuid
from datetime import datetime, timezone, timedelta

from src.models.scheduled_capture import ScheduledCapture, utcnow


def _due_capture(db, ref_suffix: str) -> ScheduledCapture:
    """Insert a capture that is already due (scheduled 5 minutes ago)."""
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    c = ScheduledCapture(
        id=str(uuid.uuid4()),
        booking_id=f"SC-EXEC-{ref_suffix}",
        payment_reference=f"auth_exec_{ref_suffix}",
        amount=1000.00,
        currency="EUR",
        status="pending",
        scheduled_capture_at=past,
        retry_count=0,
        max_retries=3,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(c)
    db.commit()
    return c


def test_trigger_processes_due_captures(client, db):
    c1 = _due_capture(db, "001")
    c2 = _due_capture(db, "002")
    c3 = _due_capture(db, "003")

    r = client.post("/execution/trigger")
    assert r.status_code == 200
    data = r.json()
    assert data["processed"] == 3
    assert data["succeeded"] + data["failed"] + data["retrying"] == 3
    assert data["duration_ms"] >= 0


def test_trigger_updates_status(client, db):
    c = _due_capture(db, "status_check")
    r = client.post("/execution/trigger")
    assert r.status_code == 200

    r2 = client.get(f"/captures/{c.id}")
    assert r2.status_code == 200
    assert r2.json()["status"] in ("captured", "retrying", "failed")


def test_trigger_creates_attempts(client, db):
    c = _due_capture(db, "attempt_check")
    client.post("/execution/trigger")

    r = client.get(f"/captures/{c.id}/attempts")
    assert r.status_code == 200
    attempts = r.json()
    assert len(attempts) >= 1
    assert attempts[0]["attempt_number"] == 1
    assert attempts[0]["status"] in ("success", "failure")


def test_trigger_empty_batch(client):
    r = client.post("/execution/trigger")
    assert r.status_code == 200
    assert r.json()["processed"] >= 0


def test_stats_endpoint(client, db):
    _due_capture(db, "stats_001")
    _due_capture(db, "stats_002")
    client.post("/execution/trigger")

    r = client.get("/stats")
    assert r.status_code == 200
    data = r.json()
    assert "totals" in data
    assert "success_rate_pct" in data
    assert "failure_breakdown" in data


def test_alerts_endpoint(client):
    r = client.get("/captures/alerts")
    assert r.status_code == 200
    data = r.json()
    assert "alerts" in data
    assert "total" in data
