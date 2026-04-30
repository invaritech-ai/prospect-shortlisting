# Prospect Console

B2B prospect shortlisting tool. Scrapes company websites, classifies them with AI, discovers and reveals contact emails, and validates them — all driven by a PostgreSQL-backed async queue (Procrastinate).

Architecture overview: [docs/repository-mental-model.md](docs/repository-mental-model.md)
State vocabulary spec: [docs/superpowers/plans/2026-04-29-state-vocabulary-spec.md](docs/superpowers/plans/2026-04-29-state-vocabulary-spec.md)

---

## How the queue works

Procrastinate uses PostgreSQL **LISTEN/NOTIFY** — when a job is enqueued the worker wakes up immediately via a Postgres notification. No Redis, no external broker. All job state lives in the `procrastinate_jobs` table alongside your business data.

Five named queues, three worker processes:

| Queue | Worker | Concurrency | Rate-limited by |
|---|---|---|---|
| `scrape` | `worker-scrape` | 4 | Browserless sessions |
| `ai_decision` | `worker-ai` | 2 | OpenRouter RPM |
| `contact_fetch` | `worker-provider` | 2 | Apollo / Snov req/min |
| `email_reveal` | `worker-provider` | 2 | Snov reveal credits |
| `validation` | `worker-provider` | 1 | ZeroBounce req/sec |

---

## Running locally (development)

### Prerequisites

- Python 3.12+ with `uv`
- Node 22+
- PostgreSQL 16 running locally (or via Docker)

### 1. Environment

```bash
cp .env.example .env
# Required keys in .env:
# DATABASE_URL=postgresql://prospect:prospect@localhost:5432/prospect
# OPENROUTER_API_KEY=...
# BROWSERLESS_API_KEY=...   (for actual scraping)
# SNOV_CLIENT_ID / SNOV_CLIENT_SECRET
# APOLLO_API_KEY
# ZEROBOUNCE_API_KEY
```

### 2. Install dependencies

```bash
uv sync
cd apps/web && npm ci && cd ../..
```

### 3. Apply DB migrations

```bash
uv run alembic upgrade head
uv run python -m procrastinate --app=app.queue:app schema --apply
```

The second command creates Procrastinate's internal tables (`procrastinate_jobs`, etc.). It is idempotent — safe to run repeatedly.

### 4. Start the API

```bash
uv run uvicorn app.main:app --reload --port 8000
```

Health check: `curl http://localhost:8000/v1/health/live`

### 5. Start the frontend

```bash
cd apps/web && npm run dev
# → http://localhost:5173
```

### 6. Start the Procrastinate workers (in separate terminals)

**S1 — Scraping:**
```bash
PS_WORKER_PROCESS=1 PROCRASTINATE_CONNECTION_STRING=$DATABASE_URL \
  uv run python -m procrastinate --app=app.queue.app worker --queue scrape --concurrency 4
```

**S2 — AI Decision:**
```bash
PS_WORKER_PROCESS=1 PROCRASTINATE_CONNECTION_STRING=$DATABASE_URL \
  uv run python -m procrastinate --app=app.queue.app worker --queue ai_decision --concurrency 2
```

**S3/S4/S5 — Provider (contact fetch, reveal, validation):**
```bash
PS_WORKER_PROCESS=1 PROCRASTINATE_CONNECTION_STRING=$DATABASE_URL \
  uv run python -m procrastinate --app=app.queue.app worker \
  --queue contact_fetch --queue email_reveal --queue validation --concurrency 5
```

`PS_WORKER_PROCESS=1` switches the DB pool to NullPool (one connection per task, no persistent pool).
`PROCRASTINATE_CONNECTION_STRING` tells the Procrastinate CLI which database to connect to.

You only need to run the workers for the pipeline stages you are actively testing. The API works independently of the workers for all read/write endpoints.

### 7. Verify a scrape job runs end-to-end

```bash
# Enqueue one job
curl -s -X POST http://localhost:8000/v1/scrape-jobs \
  -H "Content-Type: application/json" \
  -d '{"website_url": "https://example.com"}' | jq .

# Poll status (replace <id>)
curl -s http://localhost:8000/v1/scrape-jobs/<id> | jq '.state, .terminal_state'

# Check Procrastinate's own table
psql $DATABASE_URL -c \
  "SELECT id, task_name, queue, status, attempts FROM procrastinate_jobs ORDER BY id DESC LIMIT 5"
```

---

## Running with Docker (full stack)

No local Python or Node needed. Everything runs in containers.

### 1. Environment

```bash
cp .env.example .env
# Set the same keys as above. DATABASE_URL is managed by docker-compose;
# leave it unset or set to: postgresql://prospect:prospect@postgres:5432/prospect
```

### 2. Start all services

```bash
docker compose up --build -d
```

This starts:

| Service | Role |
|---|---|
| `postgres` | Database (port 5432, internal only) |
| `api` | FastAPI on port 8000. Runs `alembic upgrade head` and `procrastinate schema --apply` on startup. |
| `worker-scrape` | Procrastinate worker, queue=`scrape`, concurrency=4 |
| `worker-ai` | Procrastinate worker, queue=`ai_decision`, concurrency=2 |
| `worker-provider` | Procrastinate worker, queues=`contact_fetch,email_reveal,validation`, concurrency=5 |

### 3. Check health

```bash
docker compose ps
curl -s http://localhost:8000/v1/health/live
```

### 4. View worker logs

```bash
docker compose logs -f worker-scrape
docker compose logs -f worker-ai
docker compose logs -f worker-provider
```

### 5. Frontend (optional, development only)

```bash
docker compose --profile ui up -d web
# → http://localhost:5173
```

Or run the frontend on the host directly (`npm run dev`) pointing at `http://localhost:8000`.

---

## Running tests

```bash
# Full suite
uv run pytest -q tests/

# Smoke test (fast, no external calls)
uv run pytest tests/test_state_enum_contracts.py -q

# Queue architecture
uv run pytest tests/test_procrastinate_queue_architecture.py -q
```

---

## Key environment variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `OPENROUTER_API_KEY` | Yes | AI classification (S2) |
| `BROWSERLESS_API_KEY` | For S1 | Headless browser scraping |
| `SNOV_CLIENT_ID` / `SNOV_CLIENT_SECRET` | For S3/S4 | Contact discovery + email reveal |
| `APOLLO_API_KEY` | For S3 | Contact discovery |
| `ZEROBOUNCE_API_KEY` | For S5 | Email validation |
| `PS_WORKER_PROCESS` | Workers only | Set to `1` to activate NullPool |
