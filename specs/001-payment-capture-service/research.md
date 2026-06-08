# Research: Payment Capture Scheduling Service

**Phase**: 0 — Outline & Research
**Date**: 2026-06-08
**Feature**: 001-payment-capture-service

> **Architecture note**: Single-process deployment on Render free tier. Database is **PostgreSQL hosted on Neon** (serverless, free tier) — connected via `DATABASE_URL` env var. The database layer also supports SQLite as a local-dev/test fallback (auto-detected from the URL scheme). No Docker Compose, no Redis, no broker.

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
| APScheduler AsyncIOScheduler | Works but requires async SQLAlchemy — adds complexity for no benefit at this scale |
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
| `SELECT FOR UPDATE SKIP LOCKED` | Available in PostgreSQL but unnecessary for single-process — `threading.Lock` + `processing` status achieves the same guarantee with less complexity |
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

## 5. Database: PostgreSQL on Neon

### Decision
**PostgreSQL** hosted on **Neon** (serverless, free tier) via SQLAlchemy sync ORM + `psycopg2-binary` driver. Connection URL injected via `DATABASE_URL` env var. For local development and tests, the database layer auto-detects SQLite from the URL scheme and falls back gracefully — no Neon account needed to run locally.

### Rationale
- **Zero infrastructure cost** — Neon free tier provides 0.5 GB PostgreSQL with no credit card required and no idle shutdown.
- **Persistent across redeployments** — unlike an in-container SQLite file, Neon data survives Render redeployments. Auto-seed runs only when the table is empty (first deploy).
- **Production-grade** — real PostgreSQL means full ACID guarantees and a clear upgrade path for production scale-out.
- `SELECT FOR UPDATE SKIP LOCKED` is available if needed for future multi-process scale-out (not used now — single-process `threading.Lock` is sufficient).
- Schema is created via `Base.metadata.create_all()` on startup — no Alembic needed for this scope.
- **Auto-seed**: if the DB is empty on startup, `seed_data.py` runs automatically to populate 100+ demo records.

### Trade-offs Documented
| Concern | Impact | Mitigation |
|---------|--------|-----------|
| External dependency (Neon) | Network latency vs in-process SQLite | Neon is co-located in ap-southeast-1; latency negligible at Serenity's scale |
| Neon free tier connection limits | 10 concurrent connections max | Single-process + SQLAlchemy default pool (5) — well within limit |
| Local dev requires DATABASE_URL or SQLite fallback | Slightly more setup than a pure-SQLite approach | SQLite fallback auto-activates when `DATABASE_URL` is not set; zero friction locally |

### Alternatives Considered
| Alternative | Why Not Chosen |
|------------|---------------|
| SQLite (in-container file) | Ephemeral on Render — data lost on every redeploy; not suitable for a persistent demo |
| Render PostgreSQL add-on | Free tier deprecated; 90-day trial only |
| Railway PostgreSQL | Requires credit card for free tier verification (as of 2026) |
| TursoDB (SQLite edge) | Additional dependency and account; limited SQLAlchemy support |
| Supabase PostgreSQL | Free tier available but heavier setup and dashboard complexity for a simple demo |

---

## 6. API Framework: FastAPI

### Decision
FastAPI 0.111 with Pydantic v2. Sync route handlers with SQLAlchemy sync engine and psycopg2 driver.

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
| RAM | 512MB — sufficient for FastAPI + APScheduler + psycopg2 |
| Sleep | Free tier sleeps after 15min inactivity (mitigated by UptimeRobot) |
| Config | `render.yaml` in repo root; `DATABASE_URL` set via Render dashboard |

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
In `main.py` lifespan hook: after `Base.metadata.create_all()` runs, check `SELECT COUNT(*) FROM scheduled_captures`. If 0, run `seed_data.py` logic inline to populate 100+ records including 10–15 due "today".

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
| Database | PostgreSQL on Neon (serverless free) + SQLAlchemy sync; SQLite fallback for local dev/tests |
| API framework | FastAPI 0.111 + Pydantic v2, sync handlers |
| Free deployment | Render Web Service + Neon PostgreSQL; `render.yaml`; `DATABASE_URL` via env var |
| Auto-seed | Startup hook seeds if DB empty (idempotent — only on first deploy) |
