# Prospect Console

B2B prospect shortlisting tool. Scrapes company websites, classifies them with AI, discovers and reveals contact emails, and validates them — all driven by a PostgreSQL-backed async queue (Procrastinate).

Architecture overview: [docs/repository-mental-model.md](docs/repository-mental-model.md)
State vocabulary spec: [docs/superpowers/plans/2026-04-29-state-vocabulary-spec.md](docs/superpowers/plans/2026-04-29-state-vocabulary-spec.md)

---

## How the queue works

Procrastinate uses PostgreSQL **LISTEN/NOTIFY** — when a job is enqueued the worker wakes up immediately via a Postgres notification. No Redis, no external broker. All job state lives in the `procrastinate_jobs` table alongside your business data.

Named queues used by the current local pipeline:

| Queue | Worker | Concurrency | Rate-limited by |
|---|---|---|---|
| `scrape` | `worker-scrape` | 2 | Local browser resources |
| `ai_decision` | `worker-ai` | 2 | OpenRouter RPM |
| `contact_fetch` | `worker-provider` | 1 | Apollo / Snov req/min |
| `validation` | `worker-validation` | 1 | ZeroBounce req/sec |

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
# PS_DATABASE_URL=postgresql+psycopg://prospect:prospect@localhost:5432/prospect
# PS_OPENROUTER_API_KEY=...
# PS_SNOV_CLIENT_ID / PS_SNOV_CLIENT_SECRET
# PS_APOLLO_API_KEY
# PS_ZEROBOUNCE_API_KEY
```

### 2. Install dependencies

```bash
uv sync
cd apps/web && npm ci && cd ../..
```

### 3. Apply DB migrations

```bash
uv run alembic upgrade head
uv run python -m procrastinate --app=app.queue.app schema --apply
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

Use the restart wrapper so a transient DB blip doesn't leave the worker permanently dead:

**S1 — Scraping:**
```bash
./scripts/run_worker.sh scrape 2
```

**S2 — AI Decision:**
```bash
./scripts/run_worker.sh ai_decision 2
```

**S3 — Contacts & Email:**
```bash
./scripts/run_worker.sh contact_fetch 1
```

**S4 — Email Verification:**
```bash
./scripts/run_worker.sh validation 1
```

`run_worker.sh` is a thin `while true` loop that restarts the process after a 5 s delay on any exit. In production the same role is played by Docker's `restart: unless-stopped` policy.

The scrape worker uses static fetches first, then curl_cffi impersonation, then local Scrapling browser fallback. The browser fallback is local-only; `PS_BROWSERLESS_URL` is not used by the scraper.

`PS_WORKER_PROCESS=1` (set automatically by the wrapper) switches the **SQLAlchemy** pool to NullPool so each task opens and closes its own connection, avoiding pool contention between concurrent workers. The Procrastinate connector pool is separate and is tuned in `app/queue.py`.

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
psql "$PS_DATABASE_URL" -c \
  "SELECT id, task_name, queue, status, attempts FROM procrastinate_jobs ORDER BY id DESC LIMIT 5"
```

---

## Docker / Coolify deployment

Frontend and backend are deployed separately.

### Backend compose

Use the root [docker-compose.yml](docker-compose.yml) for the backend app in
Coolify. It starts:

| Service | Role |
|---|---|
| `api` | FastAPI on port 8000. Runs Alembic and Procrastinate schema setup before uvicorn. |
| `worker-scrape` | Procrastinate worker, queue=`scrape`, concurrency=2 |
| `worker-ai` | Procrastinate worker, queue=`ai_decision`, concurrency=2 |
| `worker-provider` | Procrastinate worker, queue=`contact_fetch`, concurrency=1 |
| `worker-validation` | Procrastinate worker, queue=`validation`, concurrency=1 |

Postgres is external to this compose file. In Coolify, attach a managed
Postgres resource or provide a Postgres URL yourself. There is no Redis broker;
Procrastinate uses Postgres LISTEN/NOTIFY.

Backend env:

```bash
PS_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/DBNAME
PS_CORS_ALLOW_ORIGINS=https://your-frontend-domain.example
PS_SETTINGS_ENCRYPTION_KEY=...
PS_OPENROUTER_API_KEY=...
PS_SNOV_CLIENT_ID=...
PS_SNOV_CLIENT_SECRET=...
PS_APOLLO_API_KEY=...
PS_ZEROBOUNCE_API_KEY=...
```

Local backend container smoke test:

```bash
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build -d
curl -s http://127.0.0.1:8001/v1/health/live
```

### Frontend image

Deploy the frontend as a separate Coolify Dockerfile app:

- Dockerfile: `apps/web/Dockerfile`
- Build context: `apps/web`
- Build arg: `VITE_API_BASE_URL=https://your-backend-domain.example`

If the frontend and backend are behind the same reverse proxy origin, leave
`VITE_API_BASE_URL` empty so browser calls use relative `/v1/...` URLs.

---

## Running tests

Tests use PostgreSQL only. They do not create SQLite schemas or run against
SQLite fallbacks. Set `PS_TEST_DATABASE_URL` or `TEST_DATABASE_URL` to a
dedicated disposable Postgres database before running DB-backed tests.

```bash
# Example local test DB URL
export PS_TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/prospect_shortlisting_test

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
| `PS_DATABASE_URL` | Yes | PostgreSQL connection string |
| `PS_CORS_ALLOW_ORIGINS` | Yes in production | Comma-separated frontend origins allowed to call the API |
| `PS_SETTINGS_ENCRYPTION_KEY` | Recommended | Fernet key for encrypted DB-backed integration settings |
| `PS_OPENROUTER_API_KEY` | Yes | AI classification (S2) |
| `PS_SNOV_CLIENT_ID` / `PS_SNOV_CLIENT_SECRET` | For S3 | Contact discovery fallback |
| `PS_APOLLO_API_KEY` | For S3 | Contact discovery primary provider |
| `PS_ZEROBOUNCE_API_KEY` | For S4 | Email validation |
| `PS_WORKER_PROCESS` | Workers only | Set to `1` to switch SQLAlchemy to NullPool (set automatically by `run_worker.sh`) |
