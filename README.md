# Payment Capture Scheduling Service

Automated payment capture scheduling service built for Serenity Cruises to eliminate ~€280K/month revenue leakage from missed manual captures.

**Live demo**: `https://payment-capture-service.onrender.com/docs`

---

## Architecture

```
┌─────────────────────────────────────────────┐
│        One uvicorn process on Render        │
│                                             │
│  FastAPI (REST + /docs OpenAPI UI)          │
│     ├── POST/GET /captures                  │
│     ├── POST /execution/trigger             │
│     ├── GET /captures/alerts (stretch)      │
│     └── GET /stats (stretch)               │
│                                             │
│  APScheduler BackgroundScheduler            │
│     └── poll_due_captures() every 60s       │
│                                             │
│  SQLite (captures.db — auto-created)        │
│     ├── scheduled_captures                  │
│     └── capture_attempts (audit log)        │
│                                             │
│  Simulated Gateway (in-process)             │
│     └── 85% success, 5 failure modes        │
└─────────────────────────────────────────────┘
```

**No Docker Compose. No Redis. No separate DB. One service. One URL.**

### Key design decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Database | SQLite | Zero infrastructure; auto-created on first run |
| Scheduler | APScheduler BackgroundScheduler | Runs in-process alongside uvicorn; no broker needed |
| Concurrency safety | `threading.Lock` + `processing` status | Single-process deployment; no distributed locking needed |
| Retry algorithm | Exponential backoff + jitter (base 30s, max 3) | Prevents thundering herd; configurable via env vars |
| Free deployment | Render Web Service | Permanent HTTPS URL, auto-deploy on push, $0 cost |
| Always-on | UptimeRobot free (ping every 5 min) | Prevents Render's 15-min idle sleep |

---

## Quick Start

### Run locally (2 commands)

```bash
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000
```

On first start: SQLite DB is created, tables set up, and 100+ demo captures are auto-seeded.

**OpenAPI docs**: http://localhost:8000/docs

### Run tests

```bash
pytest tests/ -v
```

---

## Deploy Free to Render

1. Push this repo to GitHub
2. Go to [render.com](https://render.com) → New → Web Service
3. Connect your GitHub repo — Render auto-detects `render.yaml`
4. Click **Deploy**

Your service will be live at `https://<your-app>.onrender.com`

### Keep it awake (UptimeRobot — free)

1. Sign up at [uptimerobot.com](https://uptimerobot.com) (free)
2. Add monitor: type=HTTP, URL=`https://<your-app>.onrender.com/health`, interval=5 min
3. Done — the service stays awake permanently

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Service health check |
| POST | `/captures` | Schedule a new capture |
| GET | `/captures` | List captures (filterable by status, date, booking_id) |
| GET | `/captures/{id}` | Get a specific capture |
| POST | `/captures/{id}/cancel` | Cancel a pending capture |
| GET | `/captures/{id}/attempts` | Audit trail for a capture |
| POST | `/execution/trigger` | Manually trigger execution engine (demo) |
| GET | `/captures/alerts` | Captures at risk of missing auth window (stretch) |
| GET | `/stats` | Aggregate metrics (stretch) |

### Schedule a capture

```bash
curl -X POST https://<your-app>.onrender.com/captures \
  -H "Content-Type: application/json" \
  -d '{
    "booking_id": "SC-2026-DEMO-001",
    "payment_reference": "auth_yuno_unique_001",
    "amount": 1250.00,
    "currency": "EUR",
    "scheduled_capture_at": "2026-07-15T09:00:00Z",
    "auth_expires_at": "2026-07-20T23:59:59Z"
  }'
```

### List pending captures

```bash
curl "https://<your-app>.onrender.com/captures?status=pending&page=1&page_size=20"
```

### Trigger execution engine

```bash
curl -X POST "https://<your-app>.onrender.com/execution/trigger?batch_size=50"
# {"processed":12,"succeeded":10,"failed":1,"retrying":1,"duration_ms":843}
```

### View retry audit trail

```bash
curl https://<your-app>.onrender.com/captures/<id>/attempts
```

### Deadline alerts

```bash
curl "https://<your-app>.onrender.com/captures/alerts"
curl "https://<your-app>.onrender.com/captures/alerts?alert_type=expiry_imminent&threshold_hours=24"
```

### Statistics

```bash
curl "https://<your-app>.onrender.com/stats"
curl "https://<your-app>.onrender.com/stats?date_from=2026-06-01T00:00:00Z&date_to=2026-06-30T23:59:59Z"
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./captures.db` | SQLite file path |
| `MAX_RETRIES` | `3` | Max retries per capture before permanent failure |
| `RETRY_BASE_DELAY_SECONDS` | `30` | Base delay for exponential backoff |
| `GATEWAY_SUCCESS_RATE` | `0.85` | Simulated payment success rate (0.0–1.0) |
| `EXECUTION_POLL_INTERVAL_SECONDS` | `60` | Scheduler poll interval |
| `ALERT_THRESHOLD_HOURS` | `48` | Hours-before-expiry to trigger `expiry_imminent` alert |

---

## Capture State Machine

```
pending ──[due + lock]──▶ processing ──[success]──▶ captured (terminal)
                                    ──[fail, retries left]──▶ retrying ──[next_retry_at]──▶ processing
                                    ──[fail, no retries]──▶ failed (terminal)
pending/retrying ──[cancel]──▶ cancelled (terminal)
```

---

## Trade-offs

| Trade-off | Decision |
|-----------|----------|
| SQLite vs PostgreSQL | SQLite for zero infra cost; upgrade path is a one-line `DATABASE_URL` change |
| In-process scheduler vs task queue | APScheduler sufficient for ~93 bookings/day; Celery+Redis for high volume |
| Single instance vs multi-instance | Single Render instance; `threading.Lock` prevents double-capture safely |
| Ephemeral SQLite on Render | Data resets on redeploy; auto-seed runs on startup; acceptable for demo |
