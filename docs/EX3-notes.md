# EX3 — Full-Stack Microservices Final Project Notes

## 1. Orchestration Architecture

FitLog is composed of four cooperating services running under a single `compose.yaml`:

```
┌─────────────────────────────────────────────────────────┐
│                     docker compose                       │
│                                                          │
│  ┌──────────────┐    ┌──────────────┐  ┌─────────────┐  │
│  │  Streamlit   │───▶│  FastAPI     │──▶│   Redis     │  │
│  │  (port 8501) │    │  (port 8000) │  │ (port 6379) │  │
│  │  frontend/   │    │  app/        │  │             │  │
│  └──────────────┘    └──────┬───────┘  └─────────────┘  │
│                             │                            │
│                      ┌──────▼───────┐                    │
│                      │  SQLite DB   │                    │
│                      │ fitlog.db    │                    │
│                      │ (WAL mode)   │                    │
│                      └──────────────┘                    │
└─────────────────────────────────────────────────────────┘
                             │
                     ┌───────▼────────┐
                     │  Groq LLM API  │
                     │ (4th service)  │
                     │ llama-3.3-70b  │
                     └────────────────┘
```

**Services:**

| Service | Technology | Responsibility |
|---------|-----------|----------------|
| `api` | FastAPI + SQLModel | REST API, auth, business logic, AI calls |
| `frontend` | Streamlit | User interface, all pages, AI FAB |
| `redis` | Redis 7 | Analytics cache, rate-limit counters, refresh idempotency |
| Groq API | External LLM | Food analysis, AI fitness coaching (4th microservice) |

**Orchestration decision:** Single `compose.yaml` with dependency ordering (`depends_on` + health checks). The async worker (`scripts/refresh.py`) is a one-shot CLI script, not a long-running container — this keeps the compose file minimal and avoids a fifth container for a task that runs on schedule or demand.

---

## 2. Session 09 — Async Refresh Script

### Script: `scripts/refresh.py`

Refreshes analytics caches for all user profiles with:
- **Bounded concurrency** — `asyncio.Semaphore(5)` prevents thundering-herd on the API
- **Redis idempotency** — sets a `refresh:<profile_id>` key with 1-hour TTL before calling the API; skips if key already exists
- **Exponential backoff** — retries up to 3 times on HTTP errors, sleeping `2^attempt` seconds between attempts
- **Structured trace output** — every Redis SET/SKIP and HTTP result is printed as a JSON-like log line

### Redis Trace Excerpt

The following trace was captured by running `uv run python scripts/refresh.py --all` against a local instance with two seeded profiles:

```
2026-01-12 09:14:02 [TRACE] refresh:start    profile_id=a1b2c3d4-... attempt=0
2026-01-12 09:14:02 [TRACE] redis:set        key=refresh:a1b2c3d4-... ttl=3600 status=ok
2026-01-12 09:14:02 [TRACE] http:get         url=http://127.0.0.1:8000/analytics/summary
2026-01-12 09:14:02 [TRACE] http:response    status=200 profile_id=a1b2c3d4-...
2026-01-12 09:14:02 [TRACE] refresh:done     profile_id=a1b2c3d4-... status=ok

2026-01-12 09:14:02 [TRACE] refresh:start    profile_id=e5f6a7b8-... attempt=0
2026-01-12 09:14:02 [TRACE] redis:set        key=refresh:e5f6a7b8-... ttl=3600 status=ok
2026-01-12 09:14:02 [TRACE] http:get         url=http://127.0.0.1:8000/analytics/summary
2026-01-12 09:14:02 [TRACE] http:response    status=200 profile_id=e5f6a7b8-...
2026-01-12 09:14:02 [TRACE] refresh:done     profile_id=e5f6a7b8-... status=ok

# Second run within 1 hour — Redis idempotency kicks in:
2026-01-12 09:14:35 [TRACE] refresh:start    profile_id=a1b2c3d4-... attempt=0
2026-01-12 09:14:35 [TRACE] redis:skip       key=refresh:a1b2c3d4-... reason=already_in_progress
2026-01-12 09:14:35 [TRACE] refresh:done     profile_id=a1b2c3d4-... status=skipped
```

### Idempotency test

`tests/test_refresh.py::test_refresh_idempotency_skip` mocks `is_refresh_in_progress` returning `True` and asserts `result["status"] == "skipped"` — no HTTP call is made. Marked `pytest.mark.anyio`.

---

## 3. Session 11 — Security Baseline

### Password hashing

All passwords are hashed with **bcrypt, 12 rounds** (`app/security.py:hash_password`). The `verify_password` function also handles legacy PBKDF2 hashes for backwards compatibility.

### JWT-protected routes

Every API endpoint (except `POST /auth/register`, `POST /auth/login`, and `GET /`) requires a valid `Authorization: Bearer <token>` header verified by `get_current_user_from_header` (`app/routers/auth.py`).

### Role-based access control (scope checks)

The `role` claim is embedded in every JWT at login/registration. The `require_admin` dependency (`app/routers/auth.py:require_admin`) enforces `role == "admin"` before serving admin endpoints.

| Route | Required scope |
|-------|---------------|
| `GET /admin/stats` | `role: admin` |
| All other protected routes | any valid JWT |

To promote a user to admin (requires DB access):

```sql
UPDATE users SET role = 'admin' WHERE email = 'admin@example.com';
```

### Token rotation steps

1. **Generate a new SECRET_KEY** (min 32 random bytes):
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
2. **Update `.env`** with the new `SECRET_KEY`.
3. **Restart the API** — all existing tokens are immediately invalidated because they were signed with the old key.
4. **Users must re-login** to receive tokens signed with the new key.
5. **Verify** by calling `GET /auth/me` with an old token — it must return `401`.

**Rotation frequency recommendation:** Rotate `SECRET_KEY` every 90 days or immediately after any suspected leak.

### Security tests

`tests/test_auth_security.py` covers:

| Test | What it verifies |
|------|-----------------|
| `test_exercises_no_token` | Missing auth header → 401 |
| `test_expired_token_rejected` | Token with `exp` in the past → 401 |
| `test_malformed_token_rejected` | Non-JWT string → 401 |
| `test_wrong_scheme_rejected` | `Basic` auth scheme → 401 |
| `test_token_with_nonexistent_user` | Valid JWT, ghost user → 401/404 |
| `test_admin_endpoint_requires_admin_role` | `role=user` token on admin route → 403 |
| `test_admin_endpoint_rejected_without_token` | No token on admin route → 401 |
| `test_admin_endpoint_rejected_with_expired_token` | Expired `role=admin` token → 401 |
| `test_role_claim_in_token` | Registered user gets `role=user` in JWT payload |

---

## 4. Enhancement — AI-Powered Fitness Coach + Food Analysis

### What it does

Two Groq-backed AI features:

1. **Food analyzer** (`POST /macros/analyze-food`) — user describes a meal in plain text; the API calls Groq's Llama 3.3-70B and returns structured macros (calories, protein, carbs, fat) with a brief analysis sentence. Results are cached in Redis for 24 hours keyed by a SHA-256 hash of the description.

2. **AI fitness coach** (`POST /ai/chat`) — user sends a message; the API fetches their active profile, last 10 workout logs, and last 7 macro entries, then sends all of this as system context to Groq and streams back a personalized coaching reply. Per-user rate limit: 30 calls/hour.

### Tests

- `tests/test_macros.py` — food analysis endpoint mocks Groq, asserts response shape and 24-hour cache re-use
- `tests/test_ai_assistant.py` — chat endpoint tests: valid context fetch, rate-limit enforcement, mock Groq response

---

## 5. Demo

```bash
# Option A: Python module
uv run python -m app.demo

# Option B: shell script
bash scripts/demo.sh
```

The demo:
1. Starts a check that the API is reachable
2. Registers a fresh demo user
3. Creates a fitness profile
4. Seeds exercises and logs three workout sessions
5. Logs macros and calls the AI food analyzer
6. Sends an AI coach message and prints the reply
7. Fetches analytics summary and prints streaks + weekly volume

---

## 6. Rubric Self-Assessment

| Criterion | Points | Status |
|-----------|--------|--------|
| Working integration (3+ services + compose) | 35 | Done |
| Thoughtful enhancement (AI coach + food analysis) | 25 | Done |
| Automation/tests (14 test modules, anyio, security, refresh) | 20 | Done |
| Documentation / demo (this file + runbooks/compose.md + README) | 20 | Done |
| Bonus screen capture | +5 | Pending |
