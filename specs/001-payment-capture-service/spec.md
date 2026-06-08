# Feature Specification: Payment Capture Scheduling Service

**Feature ID**: 001-payment-capture-service
**Date**: 2026-06-08
**Source**: Yuno Challenge — Serenity Cruises Deposit Hold Leak

---

## Problem Statement

Serenity Cruises (Barcelona) loses ~€280,000/month because their manual spreadsheet-based process misses 15–20% of delayed payment captures. When the card authorization window expires, ~30% of re-authorizations decline, resulting in pure revenue leakage.

They process ~2,800 bookings/month. Each booking takes a 20% deposit at booking time:
- Authorization is placed immediately (funds reserved but not collected).
- Capture is intentionally deferred to 7 days before cruise departure to minimize refund overhead.
- Authorizations expire after 7–30 days depending on card network/issuer.

---

## Goal

Build an automated **Payment Capture Scheduling Service** that:
1. Accepts scheduled future captures via API.
2. Executes those captures automatically at the scheduled time.
3. Retries on failure with intelligent backoff.
4. Alerts on captures at risk of missing their authorization window.
5. Provides aggregate statistics.

---

## Functional Requirements

### FR-1: Capture Scheduling API (Core — Must Complete)

- **FR-1.1** Accept a new capture schedule with: `booking_id`, `payment_reference` (auth reference), `amount`, `currency`, `scheduled_capture_at`, and optionally `auth_expires_at`.
- **FR-1.2** Validate inputs: no past scheduled times (configurable grace period), valid amounts (>0), non-duplicate `payment_reference`.
- **FR-1.3** Return the created capture record with a unique `id` and initial status `pending`.
- **FR-1.4** Retrieve a single scheduled capture by ID.
- **FR-1.5** List all scheduled captures with filtering: `status`, `date_from`, `date_to`, `booking_id`; paginated.
- **FR-1.6** Cancel a `pending` capture (transition to `cancelled`).

### FR-2: Capture Execution Engine (Core — Must Complete)

- **FR-2.1** Background job polls for due captures (`status=pending` AND `scheduled_capture_at ≤ now`).
- **FR-2.2** Marks a capture as `processing` atomically before executing (prevents double-processing).
- **FR-2.3** Calls simulated payment gateway: 85% success, 15% random failure (reasons: `insufficient_funds`, `authorization_expired`, `card_declined`, `network_timeout`, `issuer_unavailable`).
- **FR-2.4** On success: status → `captured`, `captured_at` = now.
- **FR-2.5** On failure (retriable): status → `retrying`, increment `retry_count`; re-schedule with exponential backoff (base 30s for demo, configurable).
- **FR-2.6** On failure (retry exhausted, default max 3): status → `failed`, `failure_reason` logged.
- **FR-2.7** Every attempt recorded in `capture_attempts` audit table.
- **FR-2.8** Expose a manual trigger endpoint `POST /execution/trigger` for demo purposes.

### FR-3: Capture Deadline Alerts (Stretch Goal)

- **FR-3.1** Detect captures where `scheduled_capture_at > auth_expires_at` (scheduling conflict).
- **FR-3.2** Detect captures where `auth_expires_at - now < alert_threshold` (default 48h) and status is still `pending` or `retrying`.
- **FR-3.3** Expose via `GET /captures/alerts` with risk classification (`scheduling_conflict`, `expiry_imminent`).

### FR-4: Batch Capture Statistics (Stretch Goal)

- **FR-4.1** `GET /stats` returns: total scheduled, total captured, total failed, total pending, average capture latency (scheduled→captured), success rate, breakdown by date range.
- **FR-4.2** Support `date_from` / `date_to` query params to slice the window.

---

## Non-Functional Requirements

| Attribute | Requirement |
|-----------|-------------|
| Correctness | Captures must not be processed more than once (idempotent execution) |
| Reliability | Failed captures must be retried; exhausted captures must be flagged |
| Auditability | Every attempt must be logged with reason and timestamp |
| Observability | Structured logging on all state transitions |
| Simplicity | Backend only; no UI required; clear REST API with OpenAPI docs |
| Demo-ability | Manual trigger endpoint + test dataset of ≥100 records |

---

## Edge Cases

| Case | Expected Behavior |
|------|-------------------|
| Duplicate `payment_reference` | 409 Conflict |
| `scheduled_capture_at` in the past | 422 Unprocessable (configurable grace: allow up to 5 min in past) |
| Invalid amount (≤0) | 422 Unprocessable |
| Capture already `captured` or `failed` | Cannot cancel; 409 returned |
| Authorization expired before capture | Simulated as `authorization_expired` failure |
| Concurrent execution (same record picked twice) | Atomic `processing` lock via DB-level optimistic lock or `SELECT FOR UPDATE SKIP LOCKED` |

---

## Test Data Requirements

- ≥ 100 scheduled captures across a 60-day window (past/present/future).
- Status mix: `pending`, `captured`, `failed`, `retrying`.
- Amounts: €200–€5,000.
- 10–15 captures due "today" for live demo.
- Failed captures with realistic `failure_reason` values.
- Seeded via a script (`scripts/seed_data.py`).

---

## Acceptance Criteria

- [ ] Developer can schedule a capture via `POST /captures`.
- [ ] Developer can list/filter captures via `GET /captures`.
- [ ] Execution engine processes due captures; statuses update correctly.
- [ ] Failed captures are retried; permanently failed ones show `failure_reason`.
- [ ] Edge cases handled gracefully (duplicates, past dates, invalid data).
- [ ] `GET /captures/alerts` flags at-risk captures (stretch).
- [ ] `GET /stats` returns aggregate metrics (stretch).
- [ ] README covers: setup, API docs, architecture decisions, trade-offs.

---

## Out of Scope

- Real Yuno payment gateway integration.
- Frontend UI.
- Multi-merchant / multi-tenant support.
- Webhook notifications.
