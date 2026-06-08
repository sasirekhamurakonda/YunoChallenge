# Quickstart: Payment Capture Scheduling Service

**Stack**: Python 3.11 · FastAPI · PostgreSQL (Neon) · APScheduler
**Deploy**: Render free tier + Neon free tier → `https://<your-app>.onrender.com`

---

## Run Locally (2 commands)

```bash
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000
```

That's it. On first start:
- Database tables are auto-created via `Base.metadata.create_all()`
- 100+ demo captures are auto-seeded if the DB is empty
- Background scheduler starts polling every 60 seconds

**Default local DB**: If `DATABASE_URL` is not set, the app falls back to SQLite (`./captures.db`) — no Postgres setup needed for local development.
**Production DB**: Set `DATABASE_URL` to your Neon PostgreSQL connection string (see `.env.example`).

**Open API docs**: http://localhost:8000/docs
**Demo UI**: http://localhost:8000/ui

---

## Deploy Free to Render + Neon (4 steps, ~10 minutes)

### Step 1 — Create a Neon Database (free)

1. Go to [neon.tech](https://neon.tech) → Sign up free
2. Create a new project → copy the **connection string** (looks like `postgresql://user:pass@host/dbname?sslmode=require`)

### Step 2 — Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

### Step 3 — Create Render Web Service

1. Go to [render.com](https://render.com) → **New → Web Service**
2. Connect your GitHub repo
3. Render auto-detects `render.yaml` — confirm the settings:
   - **Runtime**: Python 3
   - **Build command**: `pip install -r requirements.txt`
   - **Start command**: `uvicorn src.main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: Free
4. Set the `DATABASE_URL` environment variable to your Neon connection string
5. Click **Deploy**

### Step 4 — Get your URL

Render gives you: `https://payment-capture-service.onrender.com`

On first boot (takes ~30s):
- Tables are created in Neon PostgreSQL
- 100+ demo captures are seeded automatically
- Background scheduler starts

**Your API is live.** Share `https://payment-capture-service.onrender.com/docs` for the demo.

---

### `render.yaml` (committed in repo root)

```yaml
services:
  - type: web
    name: payment-capture-service
    runtime: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn src.main:app --host 0.0.0.0 --port $PORT
    plan: free
    envVars:
      - key: DATABASE_URL
        value: <your-neon-connection-string>   # set via Render dashboard
      - key: MAX_RETRIES
        value: "3"
      - key: RETRY_BASE_DELAY_SECONDS
        value: "30"
      - key: GATEWAY_SUCCESS_RATE
        value: "0.85"
      - key: EXECUTION_POLL_INTERVAL_SECONDS
        value: "60"
      - key: ALERT_THRESHOLD_HOURS
        value: "48"
```

---

## Core API Workflows

### Schedule a capture

```bash
curl -X POST https://<your-app>.onrender.com/captures \
  -H "Content-Type: application/json" \
  -d '{
    "booking_id": "SC-2026-DEMO-001",
    "payment_reference": "auth_demo_unique_001",
    "amount": 1250.00,
    "currency": "EUR",
    "scheduled_capture_at": "2026-06-08T15:00:00Z",
    "auth_expires_at": "2026-06-15T23:59:59Z"
  }'
```

### List pending captures

```bash
curl "https://<your-app>.onrender.com/captures?status=pending"
```

### Trigger execution engine (demo)

```bash
curl -X POST https://<your-app>.onrender.com/execution/trigger
```

Response:
```json
{"processed": 12, "succeeded": 10, "failed": 1, "retrying": 1, "duration_ms": 843}
```

### See status updates

```bash
curl "https://<your-app>.onrender.com/captures?status=captured"
curl "https://<your-app>.onrender.com/captures?status=failed"
```

### View retry audit trail

```bash
curl https://<your-app>.onrender.com/captures/<capture-id>/attempts
```

### Deadline alerts (stretch)

```bash
curl "https://<your-app>.onrender.com/captures/alerts"
```

### Stats (stretch)

```bash
curl "https://<your-app>.onrender.com/stats"
```

---

## Architecture (Single Process)

```
┌──────────────────────────────────────────────────┐
│          One uvicorn process on Render            │
│                                                   │
│  FastAPI (REST + /docs + /ui)                     │
│     ├── /captures         (CRUD)                  │
│     ├── /execution/trigger (manual demo)          │
│     ├── /captures/alerts   (stretch)              │
│     └── /stats             (stretch)              │
│                                                   │
│  APScheduler BackgroundScheduler                  │
│     └── poll_due_captures() every 60s             │
│                                                   │
│  Simulated Gateway (in-process)                   │
│     └── 85% success, 5 failure modes              │
└──────────────────────────────────────────────────┘
                         │
                         │ DATABASE_URL (env var)
                         ▼
              ┌─────────────────────┐
              │  Neon PostgreSQL    │  ← production
              │  (serverless, free) │
              │                     │
              │  scheduled_captures │
              │  capture_attempts   │
              └─────────────────────┘

  Local dev fallback: SQLite (./captures.db) when DATABASE_URL not set
```

**No Docker. No Compose. No Redis. One service. One URL. $0 cost.**

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./captures.db` | PostgreSQL connection string in production (Neon); falls back to SQLite for local dev |
| `MAX_RETRIES` | `3` | Max retry attempts per capture |
| `RETRY_BASE_DELAY_SECONDS` | `30` | Base for exponential backoff |
| `GATEWAY_SUCCESS_RATE` | `0.85` | Simulated success rate (0.0–1.0) |
| `EXECUTION_POLL_INTERVAL_SECONDS` | `60` | Scheduler poll interval |
| `ALERT_THRESHOLD_HOURS` | `48` | Hours before expiry for `expiry_imminent` alert |

---

## Keeping the Service Always Awake (Free)

Render free tier sleeps after 15 minutes of inactivity. To prevent this — so reviewers can access the service at any time without a cold start — use **UptimeRobot** (free, no credit card needed).

### Step-by-step: UptimeRobot setup

1. Go to [uptimerobot.com](https://uptimerobot.com) → Sign up free
2. Click **+ Add New Monitor**
3. Fill in:
   - **Monitor Type**: HTTP(s)
   - **Friendly Name**: `Payment Capture Service`
   - **URL**: `https://<your-app>.onrender.com/health`
   - **Monitoring Interval**: **5 minutes**
4. Click **Create Monitor**

That's it. UptimeRobot pings `/health` every 5 minutes — Render sees it as activity and never sleeps the process.

**Why `/health` and not `/`?**
The health endpoint returns a tiny `{"status":"ok"}` response instantly with zero DB work. Pinging `/docs` or `/captures` would be heavier and wasteful.

### The `/health` endpoint (already in the app)

```python
@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}
```

### Free plan limits (UptimeRobot)
- 50 monitors free
- 5-minute minimum interval (sufficient — Render sleeps after 15 min)
- Email alerts if the service goes down (bonus)
- No credit card required

---

## Render Free Tier Notes

- **Always awake**: With UptimeRobot pinging every 5 min, the service never sleeps.
- **Persistence**: Data is stored in Neon PostgreSQL — survives redeployments. Auto-seed only runs when the table is empty (first deploy).
- **Neon free tier**: 0.5 GB storage, no idle shutdown — fully suitable for this demo.

---

## Run Tests

```bash
pytest tests/ -v
```

Tests use an in-memory SQLite DB (`StaticPool`) — no Neon or external DB setup required. The database layer auto-detects SQLite from the URL scheme during testing.
