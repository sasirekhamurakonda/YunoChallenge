# API Contracts: Payment Capture Scheduling Service

**Version**: 1.0.0
**Base URL**: `http://localhost:8000`
**OpenAPI Docs**: `http://localhost:8000/docs`

---

## Health Check

### GET /health — Service health (used by UptimeRobot to keep the service awake)

**Response**: `200 OK`
```json
{"status": "ok", "version": "1.0.0"}
```
Lightweight — no DB query, instant response. Pinged every 5 minutes by UptimeRobot to prevent Render free-tier sleep.

---

## Authentication

No authentication for demo purposes. In production, use Bearer token / API key.

---

## Common Response Schemas

### Error Response

```json
{
  "detail": "Human-readable error message",
  "code": "MACHINE_READABLE_ERROR_CODE"
}
```

### Pagination Envelope

```json
{
  "items": [ ... ],
  "total": 142,
  "page": 1,
  "page_size": 20,
  "pages": 8
}
```

---

## Endpoints

---

### POST /captures — Schedule a new capture

**Description**: Register a new scheduled payment capture.

**Request Body** (`application/json`):

```json
{
  "booking_id": "SC-2026-00123",
  "payment_reference": "auth_yuno_abc123xyz",
  "amount": 1250.00,
  "currency": "EUR",
  "scheduled_capture_at": "2026-07-15T09:00:00Z",
  "auth_expires_at": "2026-07-20T23:59:59Z"
}
```

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `booking_id` | string | ✅ | 1–100 chars, alphanumeric + hyphens/underscores |
| `payment_reference` | string | ✅ | 1–200 chars, unique across non-cancelled captures |
| `amount` | number | ✅ | > 0, ≤ 99,999,999.99 |
| `currency` | string | ❌ (default: EUR) | ISO 4217, 3 uppercase letters |
| `scheduled_capture_at` | ISO 8601 datetime | ✅ | Must not be more than 5 min in the past |
| `auth_expires_at` | ISO 8601 datetime | ❌ | If provided, must be ≥ `scheduled_capture_at` |

**Responses**:

`201 Created`
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "booking_id": "SC-2026-00123",
  "payment_reference": "auth_yuno_abc123xyz",
  "amount": 1250.00,
  "currency": "EUR",
  "status": "pending",
  "scheduled_capture_at": "2026-07-15T09:00:00Z",
  "auth_expires_at": "2026-07-20T23:59:59Z",
  "retry_count": 0,
  "max_retries": 3,
  "failure_reason": null,
  "captured_at": null,
  "created_at": "2026-06-08T14:30:00Z",
  "updated_at": "2026-06-08T14:30:00Z"
}
```

`409 Conflict` — `payment_reference` already exists
```json
{
  "detail": "A scheduled capture with this payment_reference already exists.",
  "code": "DUPLICATE_PAYMENT_REFERENCE"
}
```

`422 Unprocessable Entity` — Validation errors
```json
{
  "detail": [
    { "loc": ["body", "amount"], "msg": "Amount must be greater than 0", "type": "value_error" }
  ]
}
```

---

### GET /captures — List scheduled captures

**Description**: Returns paginated list of scheduled captures with optional filters.

**Query Parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `status` | string (enum) | Filter by status: `pending`, `processing`, `captured`, `retrying`, `failed`, `cancelled` |
| `date_from` | ISO 8601 | Filter captures with `scheduled_capture_at ≥ date_from` |
| `date_to` | ISO 8601 | Filter captures with `scheduled_capture_at ≤ date_to` |
| `booking_id` | string | Filter by booking ID (exact match) |
| `page` | int | Page number (default: 1) |
| `page_size` | int | Items per page (default: 20, max: 100) |

**Response**: `200 OK`

```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "booking_id": "SC-2026-00123",
      "payment_reference": "auth_yuno_abc123xyz",
      "amount": 1250.00,
      "currency": "EUR",
      "status": "pending",
      "scheduled_capture_at": "2026-07-15T09:00:00Z",
      "auth_expires_at": "2026-07-20T23:59:59Z",
      "retry_count": 0,
      "max_retries": 3,
      "failure_reason": null,
      "captured_at": null,
      "created_at": "2026-06-08T14:30:00Z",
      "updated_at": "2026-06-08T14:30:00Z"
    }
  ],
  "total": 142,
  "page": 1,
  "page_size": 20,
  "pages": 8
}
```

---

### GET /captures/{id} — Get a specific capture

**Path Parameters**: `id` (UUID)

**Response**: `200 OK` — Same shape as single item above.

`404 Not Found`
```json
{
  "detail": "Scheduled capture not found.",
  "code": "CAPTURE_NOT_FOUND"
}
```

---

### POST /captures/{id}/cancel — Cancel a pending capture

**Path Parameters**: `id` (UUID)

**Request Body**: None

**Response**: `200 OK` — Updated capture record with `status: "cancelled"`.

`409 Conflict` — Capture is not in a cancellable state
```json
{
  "detail": "Cannot cancel a capture in status 'captured'.",
  "code": "INVALID_STATUS_TRANSITION"
}
```

`404 Not Found` — Capture ID does not exist.

---

### GET /captures/{id}/attempts — List attempts for a capture

**Path Parameters**: `id` (UUID)

**Response**: `200 OK`

```json
[
  {
    "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "scheduled_capture_id": "550e8400-e29b-41d4-a716-446655440000",
    "attempt_number": 1,
    "status": "failure",
    "failure_reason": "card_declined",
    "gateway_response": {
      "gateway": "yuno_simulated",
      "success": false,
      "reason": "card_declined",
      "message": "Card was declined by issuer"
    },
    "attempted_at": "2026-07-15T09:00:03Z",
    "duration_ms": 187
  },
  {
    "id": "3d2c1b0a-...",
    "attempt_number": 2,
    "status": "success",
    "failure_reason": null,
    "gateway_response": {
      "gateway": "yuno_simulated",
      "success": true,
      "transaction_id": "txn_sim_20260715090103"
    },
    "attempted_at": "2026-07-15T09:01:03Z",
    "duration_ms": 213
  }
]
```

---

### POST /execution/trigger — Manually trigger execution engine

**Description**: For demo purposes — immediately runs one poll cycle of the capture execution engine, processing all due captures.

**Request Body**: None (optional batch size override):
```json
{
  "batch_size": 50
}
```

**Response**: `200 OK`

```json
{
  "processed": 12,
  "succeeded": 10,
  "failed": 1,
  "retrying": 1,
  "duration_ms": 2341
}
```

---

### GET /captures/alerts — Deadline alerts (Stretch Goal)

**Description**: Returns captures at risk of missing their authorization window.

**Query Parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `alert_type` | string | `scheduling_conflict`, `expiry_imminent`, or omit for both |
| `threshold_hours` | int | Hours before expiry to trigger `expiry_imminent` (default: 48) |

**Response**: `200 OK`

```json
{
  "alerts": [
    {
      "capture_id": "550e8400-...",
      "booking_id": "SC-2026-00456",
      "payment_reference": "auth_yuno_def456",
      "amount": 2800.00,
      "currency": "EUR",
      "status": "pending",
      "alert_type": "scheduling_conflict",
      "alert_message": "Capture scheduled for 2026-08-20 but authorization expires 2026-08-15",
      "scheduled_capture_at": "2026-08-20T09:00:00Z",
      "auth_expires_at": "2026-08-15T23:59:59Z",
      "hours_until_expiry": -120.5
    },
    {
      "capture_id": "6f7e8d9c-...",
      "alert_type": "expiry_imminent",
      "alert_message": "Authorization expires in 36 hours, capture still pending",
      "hours_until_expiry": 36.2
    }
  ],
  "total": 2
}
```

---

### GET /stats — Batch capture statistics (Stretch Goal)

**Description**: Returns aggregate metrics for the capture service.

**Query Parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `date_from` | ISO 8601 | Start of the stats window |
| `date_to` | ISO 8601 | End of the stats window |

**Response**: `200 OK`

```json
{
  "window": {
    "from": "2026-06-01T00:00:00Z",
    "to": "2026-06-08T23:59:59Z"
  },
  "totals": {
    "scheduled": 145,
    "captured": 118,
    "failed": 12,
    "retrying": 4,
    "pending": 9,
    "cancelled": 2
  },
  "success_rate_pct": 90.77,
  "avg_capture_latency_hours": 167.3,
  "failure_breakdown": {
    "card_declined": 5,
    "insufficient_funds": 3,
    "authorization_expired": 2,
    "network_timeout": 1,
    "issuer_unavailable": 1
  }
}
```

---

## Error Codes Reference

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `DUPLICATE_PAYMENT_REFERENCE` | 409 | `payment_reference` already scheduled |
| `CAPTURE_NOT_FOUND` | 404 | No capture with given ID |
| `INVALID_STATUS_TRANSITION` | 409 | Transition not allowed (e.g., cancel a captured record) |
| `CAPTURE_IN_PAST` | 422 | `scheduled_capture_at` too far in the past |
| `AUTH_EXPIRES_BEFORE_CAPTURE` | 422 | `auth_expires_at` is before `scheduled_capture_at` |
| `VALIDATION_ERROR` | 422 | Pydantic validation failure |
| `INTERNAL_ERROR` | 500 | Unexpected server error |
