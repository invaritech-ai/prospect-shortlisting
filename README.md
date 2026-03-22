## Run with Docker (API + Worker)

This setup runs two app processes:

- `api`: FastAPI service
- `worker`: Redis queue consumer for async scrape jobs

Redis is **external** (not part of `docker-compose.yml`).

### 1) Set environment

Copy `.env.example` to `.env` and set at least:

- `PS_DATABASE_URL`
- `PS_REDIS_URL` (non-TLS `redis://...`)
- `PS_OPENROUTER_API_KEY`

### 2) Start services

```bash
docker compose up --build -d
```

### 3) Check API health

```bash
curl -sS http://127.0.0.1:8000/v1/health/live
```

### 4) Queue scrape jobs (async)

Jobs are automatically enqueued when created via `POST /v1/scrape-jobs`. To retry a failed/terminal job:

```bash
curl -sS -X POST "$BASE/v1/scrape-jobs/$JOB_ID/enqueue" | jq
```
