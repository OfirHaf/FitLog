# FitLog — Docker Compose Runbook

## Prerequisites

- Docker Desktop (or Docker Engine + Compose plugin) installed and running
- A `.env` file at the project root (copy from `.env.example`, fill in `SECRET_KEY` and `GROQ_API_KEY`)

---

## 1. Launch the Full Stack

```bash
# From the project root
docker compose up --build -d
```

This starts three services in dependency order:

| Service | Port | Role |
|---------|------|------|
| `redis` | 6379 | Cache + idempotency store |
| `api` | 8000 | FastAPI backend |
| `frontend` | 8501 | Streamlit UI |

### Verify all containers are healthy

```bash
docker compose ps
```

Expected output — all three services show `running` or `healthy`:

```
NAME                  STATUS         PORTS
fitlog-redis-1        Up (healthy)   0.0.0.0:6379->6379/tcp
fitlog-api-1          Up             0.0.0.0:8000->8000/tcp
fitlog-frontend-1     Up             0.0.0.0:8501->8501/tcp
```

---

## 2. Verify Health and Rate-Limit Headers

### API health check

```bash
curl -s http://localhost:8000/ | python -m json.tool
```

Expected:

```json
{
    "status": "ok",
    "service": "FitLog API",
    "version": "0.1.0",
    "environment": "production",
    "docs": "/docs"
}
```

### Inspect rate-limit headers after login

```bash
curl -si -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"bad@ex.com","password":"wrong"}' \
  | grep -i "retry-after\|x-ratelimit\|HTTP/"
```

After 10 failed attempts within 60 seconds from the same IP, the server responds:

```
HTTP/1.1 429 Too Many Requests
retry-after: 60
```

### OpenAPI docs

```
http://localhost:8000/docs
```

---

## 3. Run the Async Cache Refresher (Session 09)

The refresh worker is a one-shot script; run it after users have logged data:

```bash
# Refresh a single profile (pass a real UUID from the DB)
docker compose exec api \
  uv run python scripts/refresh.py --profile-id <PROFILE_UUID>

# Refresh all profiles
docker compose exec api \
  uv run python scripts/refresh.py --all
```

The script prints a structured trace to stdout. Verify Redis idempotency:

```bash
# Connect to Redis CLI inside the container
docker compose exec redis redis-cli

# List all refresh-lock keys set by the script
127.0.0.1:6379> KEYS refresh:*
```

---

## 4. Run Tests in CI

### Run the full pytest suite

```bash
# Against the local source (no Docker needed — uses in-memory SQLite)
uv run pytest tests/ -v --tb=short

# With coverage report
uv run pytest tests/ --cov=app --cov-report=term-missing
```

### Run async tests only (anyio)

```bash
uv run pytest tests/test_refresh.py -v
```

### Schemathesis contract tests (API must be running first)

```bash
# Install Schemathesis if not present
uv pip install schemathesis

# Run against the live API
uv run schemathesis run http://localhost:8000/openapi.json \
  --checks all \
  --validate-schema true
```

---

## 5. Stop the Stack

```bash
docker compose down          # stops containers, keeps volumes
docker compose down -v       # also removes volumes (wipes DB + Redis data)
```

---

## 6. View Logs

```bash
docker compose logs api       # API logs only
docker compose logs -f        # tail all services
```

---

## 7. Environment Variables Reference

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `SECRET_KEY` | Yes | — | Min 32 chars, rotate periodically |
| `GROQ_API_KEY` | Yes | — | From console.groq.com |
| `DATABASE_URL` | No | `sqlite+aiosqlite:///fitlog.db` | Override for PostgreSQL |
| `REDIS_URL` | No | `redis://localhost:6379/0` | Falls back to in-memory if unavailable |
| `JWT_ALGORITHM` | No | `HS256` | |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `1440` | 24 hours |
| `GROQ_MODEL` | No | `llama-3.3-70b-versatile` | |
