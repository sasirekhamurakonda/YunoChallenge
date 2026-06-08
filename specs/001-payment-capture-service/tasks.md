# Tasks: Payment Capture Scheduling Service

**Input**: Design documents from `/specs/001-payment-capture-service/`

**Prerequisites**: plan.md ✅ · spec.md ✅ · research.md ✅ · data-model.md ✅ · contracts/ ✅ · quickstart.md ✅

**Stack**: Python 3.11 · FastAPI · SQLite · SQLAlchemy sync · APScheduler · Pydantic v2 · Render

**User Stories**:
- **US1** (P1, Core): Capture Scheduling API — FR-1
- **US2** (P1, Core): Capture Execution Engine — FR-2
- **US3** (P2, Stretch): Capture Deadline Alerts — FR-3
- **US4** (P2, Stretch): Batch Capture Statistics — FR-4

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project skeleton, dependencies, and deploy configuration. No business logic yet.

- [x] T001 Create full project directory structure: `src/models/`, `src/schemas/`, `src/api/`, `src/services/`, `tests/unit/`, `tests/integration/`, `scripts/`, `migrations/versions/`
- [x] T002 Create `requirements.txt` with pinned versions: fastapi, uvicorn[standard], sqlalchemy, alembic, pydantic-settings, apscheduler, httpx, pytest, pytest-cov
- [x] T003 [P] Create `.env.example` with all env vars and safe defaults (DATABASE_URL, MAX_RETRIES, RETRY_BASE_DELAY_SECONDS, GATEWAY_SUCCESS_RATE, EXECUTION_POLL_INTERVAL_SECONDS, ALERT_THRESHOLD_HOURS)
- [x] T004 [P] Create `render.yaml` for one-click Render free-tier deploy with start command `uvicorn src.main:app --host 0.0.0.0 --port $PORT`
- [x] T005 [P] Create `Dockerfile` (single-stage Python 3.11-slim, copies src/, installs requirements.txt, exposes PORT)
- [x] T006 [P] Create `src/__init__.py`, `src/models/__init__.py`, `src/schemas/__init__.py`, `src/api/__init__.py`, `src/services/__init__.py` (empty init files)

**Checkpoint**: `pip install -r requirements.txt` succeeds. Project structure matches plan.md.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that ALL user stories depend on. Must be complete before any feature work.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T007 Create `src/config.py` — pydantic-settings `Settings` class reading all env vars from `.env` with defaults; export a singleton `settings` instance
- [x] T008 Create `src/database.py` — SQLAlchemy sync engine (`create_engine` with `check_same_thread=False` for SQLite), `SessionLocal` factory, declarative `Base`; enable WAL mode via `event.listen` on connect; `get_db()` dependency
- [x] T009 Create `src/models/scheduled_capture.py` — `ScheduledCapture` ORM model with all columns from data-model.md; `CaptureStatus` string enum; `utcnow()` and `new_uuid()` helpers
- [x] T010 Create `src/models/capture_attempt.py` — `CaptureAttempt` ORM model with FK to `scheduled_captures`; `AttemptStatus` string enum
- [x] T011 Create `src/main.py` skeleton — FastAPI app with lifespan context manager that: (1) runs `Base.metadata.create_all(engine)`, (2) starts scheduler, (3) auto-seeds DB if empty; register all routers; global exception handlers returning structured `{"detail": ..., "code": ...}` JSON

**Checkpoint**: `uvicorn src.main:app --reload` starts without errors. `GET /` returns 404 (no routes yet). `captures.db` file is created automatically.

---

## Phase 3: User Story 1 — Capture Scheduling API (P1) 🎯 MVP

**Goal**: A developer can schedule a capture, retrieve it, list with filters, and cancel it. No execution yet.

**Independent Test**: `POST /captures` → 201. `GET /captures/{id}` → 200. `GET /captures?status=pending` → filtered list. `POST /captures/{id}/cancel` → 200 with status=cancelled. Duplicate `payment_reference` → 409. Past `scheduled_capture_at` → 422.

### Implementation

- [x] T012 [P] [US1] Create `src/schemas/capture.py` — Pydantic v2 models: `CreateCaptureRequest` (with validators for amount>0, future datetime, currency regex), `CaptureResponse`, `PaginatedCapturesResponse`, `CaptureAttemptResponse`
- [x] T013 [P] [US1] Create `src/schemas/stats.py` — placeholder file; add `AlertItem`, `AlertsResponse`, `StatsResponse` schemas (used by US3/US4 but defined now to avoid circular imports)
- [x] T014 [US1] Create `src/services/capture_service.py` — implement: `create_capture(db, request) -> ScheduledCapture` (duplicate check → 409, past datetime check → 422, insert); `get_capture(db, id) -> ScheduledCapture` (404 if missing); `list_captures(db, status, date_from, date_to, booking_id, page, page_size) -> (items, total)` with dynamic filters; `cancel_capture(db, id) -> ScheduledCapture` (state guard → 409 if not pending/retrying); `list_attempts(db, capture_id) -> list[CaptureAttempt]`
- [x] T015 [US1] Create `src/api/captures.py` — FastAPI router with: `POST /captures` → 201, `GET /captures` → paginated, `GET /captures/{id}` → 200, `POST /captures/{id}/cancel` → 200, `GET /captures/{id}/attempts` → list; wire `capture_service` calls; proper HTTP status codes and error responses matching contracts/endpoints.md
- [x] T016 [US1] Register captures router in `src/main.py` lifespan; add `GET /health` endpoint returning `{"status": "ok", "version": "1.0.0"}`

**Checkpoint**: All FR-1 acceptance criteria pass. `/docs` shows 5 capture endpoints + `/health`. Edge cases (duplicate, past date, invalid amount, cancel-captured) return correct error codes.

---

## Phase 4: User Story 2 — Capture Execution Engine (P1) 🎯 Core

**Goal**: Due captures are processed automatically. Failures retry with backoff. All attempts are audited. Manual trigger available for demo.

**Independent Test**: Seed 3 captures with `scheduled_capture_at = now - 1 min`. `POST /execution/trigger` → processed=3. `GET /captures?status=captured` shows successes. `GET /captures?status=retrying` or `status=failed` shows failures. `GET /captures/{id}/attempts` shows audit trail with `attempt_number`, `failure_reason`, `duration_ms`.

### Implementation

- [x] T017 [P] [US2] Create `src/services/payment_gateway.py` — `GatewayResult` dataclass (success: bool, failure_reason: str|None, transaction_id: str|None, duration_ms: int); `execute_capture(payment_reference, amount, currency) -> GatewayResult` using `random` with configurable `GATEWAY_SUCCESS_RATE`; failure distribution per research.md; `time.sleep(random.uniform(0.05, 0.3))` latency simulation
- [x] T018 [US2] Create `src/services/execution_engine.py` — `ExecutionEngine` class with `threading.Lock`; `_process_single(db, capture) -> dict` (mark processing → call gateway → update status + insert CaptureAttempt → compute next_retry_at on failure using exponential backoff); `run_batch(db, batch_size) -> ExecutionResult` (query due pending+retrying captures, lock, process each, return summary); ensure stale `processing` records (>10 min) are reset to `pending` at batch start
- [x] T019 [US2] Create `src/scheduler.py` — APScheduler `BackgroundScheduler`; `start_scheduler(app)` registers `run_batch` as `IntervalTrigger` job with `max_instances=1`; `stop_scheduler()` for lifespan shutdown
- [x] T020 [US2] Create `src/api/execution.py` — `POST /execution/trigger` accepts optional `{"batch_size": int}`, calls `execution_engine.run_batch()` directly (bypasses scheduler for immediate demo trigger), returns `ExecutionResult` as JSON
- [x] T021 [US2] Create `scripts/seed_data.py` — generate 100+ `ScheduledCapture` records: 60-day spread (past 30 / future 30), realistic status distribution (40% captured, 30% pending, 15% failed, 10% retrying, 5% cancelled), amounts €200–€5,000, 10–15 records with `scheduled_capture_at` within the current hour for live demo, `CaptureAttempt` rows for all non-pending records; use `faker` for booking IDs and customer refs
- [x] T022 [US2] Wire execution engine into `src/main.py` lifespan: start scheduler on startup, call `seed_data` inline if `SELECT COUNT(*) FROM scheduled_captures = 0`, stop scheduler on shutdown; register execution router

**Checkpoint**: `POST /execution/trigger` processes due captures, statuses update correctly. Scheduler fires automatically every 60s. Retry records show `next_retry_at` advancing. `capture_attempts` table accumulates one row per attempt. Auto-seed runs on fresh DB.

---

## Phase 5: User Story 3 — Capture Deadline Alerts (P2, Stretch)

**Goal**: Expose captures at risk of missing their auth window so Serenity can act before it's too late.

**Independent Test**: `GET /captures/alerts` returns records where `scheduled_capture_at > auth_expires_at` (conflict) and where `auth_expires_at - now < 48h` and status is pending/retrying (imminent). Filter by `alert_type` returns only that type.

### Implementation

- [x] T023 [P] [US3] Add `get_alerts(db, alert_type, threshold_hours) -> list[AlertItem]` to `src/services/capture_service.py` — two queries: (1) `scheduled_capture_at > auth_expires_at` for `scheduling_conflict`; (2) `auth_expires_at IS NOT NULL AND auth_expires_at - now < threshold AND status IN (pending, retrying)` for `expiry_imminent`; compute `hours_until_expiry` for each result
- [x] T024 [US3] Create `src/api/alerts.py` — `GET /captures/alerts` with `alert_type` and `threshold_hours` query params; return `AlertsResponse` matching contracts/endpoints.md; register router in `src/main.py`

**Checkpoint**: `GET /captures/alerts` returns correctly classified alerts. Seeded data includes at least 2–3 records with `auth_expires_at` that will trigger both alert types.

---

## Phase 6: User Story 4 — Batch Capture Statistics (P2, Stretch)

**Goal**: Single endpoint returning aggregate metrics for the configured date window.

**Independent Test**: `GET /stats` returns `totals` dict with counts matching actual DB records. `success_rate_pct` = (captured / (captured+failed)) * 100. `GET /stats?date_from=...&date_to=...` returns counts only within that window.

### Implementation

- [x] T025 [P] [US4] Add `get_stats(db, date_from, date_to) -> StatsResponse` to `src/services/capture_service.py` — aggregate queries: counts by status, average latency (avg of `captured_at - scheduled_capture_at` for captured records), failure breakdown by `failure_reason` from `capture_attempts`; apply optional date window filter on `scheduled_capture_at`
- [x] T026 [US4] Create `src/api/stats.py` — `GET /stats` with optional `date_from`/`date_to` query params; return `StatsResponse`; register router in `src/main.py`

**Checkpoint**: `GET /stats` reflects accurate counts from seeded data. `success_rate_pct` ~= 85% (matching GATEWAY_SUCCESS_RATE). `failure_breakdown` shows realistic distribution.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: README, final wiring, edge case hardening, deploy validation.

- [x] T027 Write `README.md` covering: project overview, architecture diagram (ASCII from quickstart.md), local setup (2 commands), Render deploy steps, UptimeRobot keep-alive setup, all API endpoints with curl examples, environment variables table, trade-offs and design decisions
- [x] T028 [P] Add `tests/conftest.py` — in-memory SQLite `StaticPool` engine + `TestClient` fixture; override `get_db` dependency for isolated tests
- [x] T029 [P] Add `tests/integration/test_capture_api.py` — happy path tests: create, get, list with filter, cancel; edge cases: duplicate ref, past date, cancel-captured
- [x] T030 [P] Add `tests/integration/test_execution_trigger.py` — seed 3 due captures, trigger, assert statuses updated and attempts created
- [x] T031 Verify `render.yaml` deploy config end-to-end: push to GitHub, confirm Render detects `render.yaml`, confirm startup logs show DB init + auto-seed + scheduler start, confirm `/health` returns 200, confirm `/docs` loads

**Checkpoint**: `pytest tests/ -v` passes. Render deploy URL is live. UptimeRobot monitor active. `/docs` accessible at `https://<app>.onrender.com/docs`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — **BLOCKS all user stories**
- **Phase 3 (US1 — Scheduling API)**: Depends on Phase 2 only
- **Phase 4 (US2 — Execution Engine)**: Depends on Phase 2 + Phase 3 (needs ScheduledCapture model and capture_service)
- **Phase 5 (US3 — Alerts)**: Depends on Phase 3 (needs capture_service and schemas)
- **Phase 6 (US4 — Stats)**: Depends on Phase 3 (needs capture_service and schemas)
- **Phase 7 (Polish)**: Depends on all phases above

### User Story Dependencies

```
Phase 1 (Setup)
    └── Phase 2 (Foundational)
            ├── Phase 3 (US1: Scheduling API)  ← MVP deliverable
            │       ├── Phase 4 (US2: Execution Engine)  ← Core complete
            │       ├── Phase 5 (US3: Alerts)  [P] can run alongside Phase 4
            │       └── Phase 6 (US4: Stats)   [P] can run alongside Phase 4/5
            └── (Phases 5 & 6 also independent of each other)
```

### Within Each Phase

- Models before services
- Services before API routers
- Routers registered in `main.py` last
- `[P]` tasks within a phase can be written concurrently (different files)

### Parallel Opportunities

```bash
# Phase 1 — all tasks are independent files:
T003 (.env.example) || T004 (render.yaml) || T005 (Dockerfile) || T006 (__init__ files)

# Phase 2 — models can be written alongside config:
T007 (config.py) || T008 (database.py)  →  then T009 + T010 (models)  →  then T011 (main.py)

# Phase 3:
T012 (schemas/capture.py) || T013 (schemas/stats.py)  →  T014 (capture_service.py)  →  T015 (api/captures.py)

# Phase 4:
T017 (payment_gateway.py) || T021 (seed_data.py)  →  T018 (execution_engine.py)  →  T019 + T020

# Phases 5 & 6 can run in parallel once Phase 3 is done:
T023 + T024 (alerts) || T025 + T026 (stats)

# Phase 7 tests are all independent:
T028 (conftest) || T029 (capture api tests) || T030 (execution tests)
```

---

## Implementation Strategy

### MVP (90-minute target)

1. ✅ Phase 1: Setup (~10 min)
2. ✅ Phase 2: Foundational (~15 min)
3. ✅ Phase 3: US1 Scheduling API (~20 min)
4. ✅ Phase 4: US2 Execution Engine (~25 min)
5. ✅ Phase 7: README + deploy (~10 min)
6. **STOP**: Core requirements delivered. Demo-ready with live URL.

### Full Delivery (with stretch goals)

After MVP is deployed and verified:
7. ✅ Phase 5: US3 Alerts (~15 min)
8. ✅ Phase 6: US4 Stats (~15 min)
9. ✅ Phase 7: Tests + final polish (~20 min)

### Delivery Checkpoints

| Checkpoint | What's deliverable |
|------------|-------------------|
| After Phase 3 | Schedule + query captures via API |
| After Phase 4 | Full core: execution + retry + audit trail + seeded demo data |
| After Phase 5 | Stretch: deadline alerts |
| After Phase 6 | Stretch: statistics dashboard |
| After Phase 7 | All tests pass, deployed on Render with live URL |

---

## Notes

- `[P]` = different files, no blocking dependencies — write concurrently
- `[US#]` = maps to user story for traceability
- Commit after each phase checkpoint
- `pytest tests/ -v` should pass at each checkpoint before moving forward
- All config (retries, delays, success rate) via env vars — never hardcoded
- No secrets in source code — `.env` in `.gitignore`
