"""
FitLog FastAPI application entry point.
Run with: uv run uvicorn app.main:app --reload
Docs at:  http://127.0.0.1:8000/docs
"""
import logging
import logging.config
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.config import settings
from app.database import create_db_and_tables
from app.exceptions import register_exception_handlers
from app.routers import (
    admin,
    ai_assistant,
    analytics,
    auth,
    body_metrics,
    exercises,
    hydration,
    macros,
    profile,
    recovery,
    sleep,
    steps,
    workout_logs,
)

# ─── Logging ───────────────────────────────────────────────────────────────
logging.config.dictConfig(
    {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
            },
        },
        "root": {
            "handlers": ["console"],
            "level": "DEBUG" if settings.is_development else "INFO",
        },
    }
)

logger = logging.getLogger(__name__)


# ─── Lifespan ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting FitLog API (%s)", settings.app_env)
    await create_db_and_tables()
    yield
    logger.info("Shutting down FitLog API")


# ─── App ───────────────────────────────────────────────────────────────────

app = FastAPI(
    title="FitLog API",
    description=(
        "FitLog — Your personal fitness & nutrition tracking backend.\n\n"
        "Track exercises, log workouts, manage macros, and get AI-powered advice."
    ),
    version="0.1.0",
    contact={"name": "FitLog", "email": "fitlog@example.com"},
    license_info={"name": "MIT"},
    lifespan=lifespan,
)

# Compress responses >= 1KB
app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS — allow all origins so the Streamlit components.html iframe (null origin)
# can reach the API. Bearer-token auth doesn't need allow_credentials=True.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Centralized exception handling
register_exception_handlers(app)

# ─── Routers ───────────────────────────────────────────────────────────────

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(exercises.router)
app.include_router(workout_logs.router)
app.include_router(macros.router)
app.include_router(profile.router)
app.include_router(ai_assistant.router)
app.include_router(analytics.router)
app.include_router(sleep.router)
app.include_router(hydration.router)
app.include_router(body_metrics.router)
app.include_router(recovery.router)
app.include_router(steps.router)


# ─── Health ────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def health_check() -> dict:
    """API health check — confirms the service is running."""
    return {
        "status": "ok",
        "service": "FitLog API",
        "version": "0.1.0",
        "environment": settings.app_env,
        "docs": "/docs",
    }
