from datetime import datetime, timezone, timedelta


def _future(days=7):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _past(minutes=10):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def test_create_capture_201(client):
    r = client.post("/captures", json={
        "booking_id": "SC-001",
        "payment_reference": "auth_001",
        "amount": 1250.00,
        "currency": "EUR",
        "scheduled_capture_at": _future(7),
        "auth_expires_at": _future(14),
    })
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "pending"
    assert data["booking_id"] == "SC-001"
    assert data["amount"] == 1250.00


def test_get_capture_200(client):
    r = client.post("/captures", json={
        "booking_id": "SC-002",
        "payment_reference": "auth_002",
        "amount": 500.00,
        "currency": "EUR",
        "scheduled_capture_at": _future(3),
    })
    cid = r.json()["id"]
    r2 = client.get(f"/captures/{cid}")
    assert r2.status_code == 200
    assert r2.json()["id"] == cid


def test_get_capture_404(client):
    r = client.get("/captures/non-existent-id")
    assert r.status_code == 404
    assert r.json()["code"] == "CAPTURE_NOT_FOUND"


def test_list_captures_filter_by_status(client):
    client.post("/captures", json={
        "booking_id": "SC-003",
        "payment_reference": "auth_003",
        "amount": 300.00,
        "currency": "EUR",
        "scheduled_capture_at": _future(5),
    })
    r = client.get("/captures?status=pending")
    assert r.status_code == 200
    assert r.json()["total"] >= 1
    assert all(c["status"] == "pending" for c in r.json()["items"])


def test_cancel_capture(client):
    r = client.post("/captures", json={
        "booking_id": "SC-004",
        "payment_reference": "auth_004",
        "amount": 700.00,
        "currency": "EUR",
        "scheduled_capture_at": _future(10),
    })
    cid = r.json()["id"]
    r2 = client.post(f"/captures/{cid}/cancel")
    assert r2.status_code == 200
    assert r2.json()["status"] == "cancelled"


def test_cancel_already_cancelled_409(client):
    r = client.post("/captures", json={
        "booking_id": "SC-005",
        "payment_reference": "auth_005",
        "amount": 800.00,
        "currency": "EUR",
        "scheduled_capture_at": _future(10),
    })
    cid = r.json()["id"]
    client.post(f"/captures/{cid}/cancel")
    r2 = client.post(f"/captures/{cid}/cancel")
    assert r2.status_code == 409
    assert r2.json()["code"] == "INVALID_STATUS_TRANSITION"


def test_duplicate_payment_reference_409(client):
    payload = {
        "booking_id": "SC-006",
        "payment_reference": "auth_dup_001",
        "amount": 900.00,
        "currency": "EUR",
        "scheduled_capture_at": _future(7),
    }
    client.post("/captures", json=payload)
    payload["booking_id"] = "SC-007"
    r = client.post("/captures", json=payload)
    assert r.status_code == 409
    assert r.json()["code"] == "DUPLICATE_PAYMENT_REFERENCE"


def test_past_scheduled_capture_422(client):
    r = client.post("/captures", json={
        "booking_id": "SC-008",
        "payment_reference": "auth_008",
        "amount": 500.00,
        "currency": "EUR",
        "scheduled_capture_at": _past(10),
    })
    assert r.status_code == 422


def test_invalid_amount_422(client):
    r = client.post("/captures", json={
        "booking_id": "SC-009",
        "payment_reference": "auth_009",
        "amount": 0,
        "currency": "EUR",
        "scheduled_capture_at": _future(5),
    })
    assert r.status_code == 422


def test_auth_expires_before_scheduled_422(client):
    r = client.post("/captures", json={
        "booking_id": "SC-010",
        "payment_reference": "auth_010",
        "amount": 600.00,
        "currency": "EUR",
        "scheduled_capture_at": _future(10),
        "auth_expires_at": _future(5),
    })
    assert r.status_code == 422


def test_list_attempts_empty(client):
    r = client.post("/captures", json={
        "booking_id": "SC-011",
        "payment_reference": "auth_011",
        "amount": 400.00,
        "currency": "EUR",
        "scheduled_capture_at": _future(3),
    })
    cid = r.json()["id"]
    r2 = client.get(f"/captures/{cid}/attempts")
    assert r2.status_code == 200
    assert r2.json() == []
