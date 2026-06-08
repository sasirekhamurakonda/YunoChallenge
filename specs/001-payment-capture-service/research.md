# Research: Payment Capture Scheduling Service

**Phase**: 0 — Outline & Research
**Date**: 2026-06-08 (revised for minimal deployment)
**Feature**: 001-payment-capture-service

> **Revision note**: Architecture revised from PostgreSQL + Docker Compose to SQLite + single-process for zero-infrastructure free deployment on Render.

---

## 1. Background Job Scheduling in Python

### Decision
Use **APScheduler 3.x** with a `BackgroundScheduler` (thread-based) and an `IntervalTrigger` (60-second poll interval).

### Rationale
- `BackgroundScheduler` runs the polling job in a daemon thread alongside FastAPI/uvicorn, no extra process needed.
- No external broker, no Redis, no Celery — just one Python process.
- Started inside FastAPI's `lifespan` context manager; cleanly shut down on app exit.
- For Serenity's scale (~93 bookings/day), a 60-second polling interval is more than sufficient.

### Alternatives Considered
| Alternative | Why Rejected |
|------------|-------------|
| Celery + Redis | Requires 2 extra services (broker + worker); violates single-service constraint |
| APScheduler AsyncIOScheduler | Works but requires async SQLAlchemy — adds complexity with SQLite |
| asyncio background task | No retry, no persistence, harder to manage lifecycle |
| Cron (system) | Not available on Render free tier; requires separate process |

---

## 2. Concurrency Safety: Preventing Double-Capture

### Decision
Use an **in-process `asyncio.Lock`** (or `threading.Lock` since APScheduler uses threads) combined with the `processing` status field as a guard.

### Rationale
- This is a **single-process** deployment on Render. There is exactly one execution engine thread. No distributed coordination is needed.
- The `processing` status still acts as a recovery checkpoint: if the app restarts mid-execution, a startup check resets stale `processing` records back to `pending` (with a timestamp threshold, e.g., older than 10 minutes).
- A `threading.Lock` prevents the scheduler job from overlapping with itself if one poll cycle takes longer than 60 seconds (APScheduler's `max_instances=1` setting also handles this).

### Alternatives Considered
| Alternative | Why Rejected |
|------------|-------------|
| `SELECT FOR UPDATE SKIP LOCKED` | PostgreSQL-only; not available in SQLite |
| Redis distributed lock | Requires Redis service; violates single-service constraint |
| Optimistic locking (version column) | Overkill for single-process; adds complexity |

---

## 3. Retry Strategy

### Decision
**Exponential backoff** with jitter: `base_delay * (2 ^ retry_count) + random_jitter`. Default: `base_delay=30s`, `max_retries=3`.

Retry schedule (demo):
- Attempt 1 (immediate): at `scheduled_capture_at`
- Attempt 2 (retry 1): +30s
- Attempt 3 (retry 2): +60s + jitter (0–10s)
- Attempt 4 (retry 3): +120s + jitter → permanent `failed`

All params configurable via env vars: `MAX_RETRIES`, `RETRY_BASE_DELAY_SECONDS`.

### Rationale
- Backoff prevents hammering a "failing" issuer with repeated fast retries.
- Demo-scale delays (30–120s) make failures and retries visible during a live demo within minutes.
- Production operators can set `RETRY_BASE_DELAY_SECONDS=3600` (1 hour) without changing code.

---

## 4. Simulated Payment Gateway

### Decision
`payment_gateway.py` — a pure Python function, no HTTP calls. Returns `GatewayResult` with success (85%) or random failure (15%) plus simulated latency (`time.sleep(random.uniform(0.05, 0.3))`).

Failure distribution (of 15%):
- `card_declined`: 40%
- `insufficient_funds`: 25%
- `authorization_expired`: 15%
- `network_timeout`: 12%
- `issuer_unavailable`: 8%

### Rationale
- Decoupled behind a clean interface — swapping in real Yuno requires only updating this one file.
- `time.sleep` (not `asyncio.sleep`) is correct here since the execution engine runs in APScheduler's background thread, not the asyncio event loop.

---

## 5. Database: SQLite

### Decision
**SQLite** (file at `./captures.db`) via SQLAlchemy sync ORM + `StaticPool` for tests.

### Rationale
- **Zero infrastructure** — no separate database service, no connection string management beyond a file path.
- SQLite is fully ACID-compliant with WAL mode enabled (`PRAGMA journal_mode=WAL`), which allows concurrent reads while a write is in progress.
- At Serenity's scale (~93 captures/day), SQLite comfortably handles the load with sub-millisecond query times.
- WAL mode + single-writer architecture eliminates any write contention concern.
- SQLite file is created automatically on first run; Alembic migrations run on startup.
- **Auto-seed**: if the DB is empty on startup, `seed_data.py` runs automatically to populate 100+ demo records.

### Trade-offs Documented
| Concern | Impact | Mitigation |
|---------|--------|-----------|
| Render free tier is ephemeral (disk resets on redeploy) | Test data lost on redeploy | Auto-seed on startup if DB is empty; acceptable for demo |
| No `SELECT FOR UPDATE SKIP LOCKED` | Single-process so not needed | `threading.Lock` + `processing` status achieves same guarantee |
| Not suitable for multi-process scale-out | Fine for single-instance demo | Document upgrade path to PostgreSQL in README |

### Alternatives Considered
| Alternative | Why Rejected |
|------------|-------------|
| PostgreSQL (Docker Compose) | Requires separate service; Docker Compose adds local setup friction |
| Render PostgreSQL add-on | Free tier deprecated; 90-day trial only; adds service dependency |
| Railway PostgreSQL | Requires Railway account, project, more config steps |
| TursoDB (SQLite edge) | Additional dependency and account; overkill for demo |

---

## 6. API Framework: FastAPI

### Decision
FastAPI 0.111 with Pydantic v2. Sync route handlers using `run_in_executor` for DB calls, or direct sync with SQLAlchemy sync engine (simpler for SQLite).

### Rationale
- Auto-generates OpenAPI/Swagger UI at `/docs` — reviewer can explore the API without writing curl commands.
- Pydantic v2 provides clear validation error messages for all edge cases.
- Using the sync SQLAlchemy engine with FastAPI is simpler and equally performant for this scale.

---

## 7. Free Deployment: Render

### Decision
Deploy to **Render Web Service** (free tier). Config committed as `render.yaml` in the repo for one-click setup.

### Why Render
| Property | Detail |
|----------|--------|
| Free tier | Permanent free web service (not just a trial) |
| URL | `https://<app-name>.onrender.com` — shareable, HTTPS |
| Deploy | Push to GitHub → auto-deploy (no manual steps) |
| Start command | `uvicorn src.main:app --host 0.0.0.0 --port $PORT` |
| RAM | 512MB — sufficient for FastAPI + SQLite + APScheduler |
| Sleep | Free tier sleeps after 15min inactivity (first request takes ~30s to wake) |
| Config | `render.yaml` in repo root for one-click "Deploy to Render" button |

### Alternatives Considered
| Alternative | Why Not Chosen |
|------------|---------------|
| Railway | Requires credit card for free tier verification (as of 2026) |
| Fly.io | More CLI steps; `fly launch` config can have errors on first try |
| Vercel | Serverless — no persistent background scheduler |
| Heroku | Free tier removed (2022) |
| Replit | Not suitable for professional demo delivery |

---

## 8. Auto-Seed on Startup

### Decision
In `main.py` lifespan hook: after migrations run, check `SELECT COUNT(*) FROM scheduled_captures`. If 0, run `seed_data.py` logic inline to populate 100+ records including 10–15 due "today".

### Rationale
- Reviewer gets a working demo immediately after deploy — no manual seed step.
- Idempotent: only seeds if the table is empty, so restarting the app doesn't duplicate data.

---

## All NEEDS CLARIFICATION Resolved

| Item | Resolution |
|------|-----------|
| Scheduler | APScheduler 3.x BackgroundScheduler |
| Concurrency safety | threading.Lock + `processing` status + single-process deployment |
| Retry algorithm | Exponential backoff with jitter, 3 retries, env-configurable |
| Simulated gateway | 85% success, 5 failure modes, sync sleep for latency |
| Database | SQLite + SQLAlchemy sync, WAL mode |
| API framework | FastAPI 0.111 + Pydantic v2, sync handlers |
| Free deployment | Render Web Service, `render.yaml`, auto-deploy on push |
| Auto-seed | Startup hook seeds if DB empty |
