"""
AI Fitness Assistant router.
POST /ai/chat — sends a context-enriched prompt to Groq AI
and returns a personalised fitness/nutrition reply.
Uses the Groq API (OpenAI-compatible interface).
Groq provides faster inference and much higher free tier quotas than Gemini.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import APIRouter, status, Depends
from openai import AsyncOpenAI, RateLimitError, APITimeoutError, APIStatusError
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

import time as _time
from collections import defaultdict
from threading import Lock as _Lock

from app.config import settings
from app.database import get_session
from app.db import FitnessProfile, WorkoutLog, MacroEntry, User
from app.exceptions import NotFoundError, ExternalServiceError, RateLimitError
from app.models import ChatRequest, ChatResponse
from app.routers.auth import get_current_user_from_header

_AI_RATE: dict[str, list[float]] = defaultdict(list)
_AI_RATE_LOCK = _Lock()
_AI_MAX_CALLS = 30       # per user per hour
_AI_WINDOW = 3600.0      # 1 hour


def _check_ai_rate(user_id: str) -> None:
    """Raise RateLimitError if user exceeded AI call quota."""
    now = _time.monotonic()
    with _AI_RATE_LOCK:
        calls = _AI_RATE[user_id]
        _AI_RATE[user_id] = [t for t in calls if now - t < _AI_WINDOW]
        if len(_AI_RATE[user_id]) >= _AI_MAX_CALLS:
            raise RateLimitError(
                f"AI rate limit reached ({_AI_MAX_CALLS} messages/hour). Please wait before sending more.",
                retry_after=int(_AI_WINDOW),
            )
        _AI_RATE[user_id].append(now)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["AI Assistant"])

_GROQ_MODEL = settings.groq_model

# ---------------------------------------------------------------------------
# In-memory context cache: avoids repeated DB round-trips within a 5-minute
# window for the same user.  Stored as {profile_id: (context_str, expires_at)}
# Capped at 500 entries; oldest entries evicted when full.
# ---------------------------------------------------------------------------
_CONTEXT_CACHE: dict[str, tuple[str, float]] = {}
_CONTEXT_TTL_SECONDS = 300   # 5 minutes
_CONTEXT_CACHE_MAX   = 500


def _get_cached_context(profile_id: str) -> Optional[str]:
    """Return cached context string if it exists and has not expired."""
    entry = _CONTEXT_CACHE.get(profile_id)
    if entry is None:
        return None
    context, expires_at = entry
    if time.monotonic() > expires_at:
        del _CONTEXT_CACHE[profile_id]
        return None
    return context


def _set_cached_context(profile_id: str, context: str) -> None:
    """Store context string in the cache; evict expired + oldest if over cap."""
    now = time.monotonic()
    # Evict all expired entries first
    expired = [k for k, (_, exp) in _CONTEXT_CACHE.items() if now > exp]
    for k in expired:
        del _CONTEXT_CACHE[k]
    # If still over cap, evict the oldest-expiring entries
    if len(_CONTEXT_CACHE) >= _CONTEXT_CACHE_MAX:
        oldest = sorted(_CONTEXT_CACHE, key=lambda k: _CONTEXT_CACHE[k][1])
        for k in oldest[: len(_CONTEXT_CACHE) - _CONTEXT_CACHE_MAX + 1]:
            del _CONTEXT_CACHE[k]
    _CONTEXT_CACHE[profile_id] = (context, now + _CONTEXT_TTL_SECONDS)


_groq_client: AsyncOpenAI | None = None

def _get_client() -> AsyncOpenAI:
    global _groq_client
    if _groq_client is None:
        _groq_client = AsyncOpenAI(api_key=settings.groq_api_key, base_url="https://api.groq.com/openai/v1")
    return _groq_client


async def _fetch_recent_workouts(user_id: str, profile_id: str, session: AsyncSession) -> list:
    """Fetch the 5 most recent workout logs scoped to a profile."""
    stmt = (
        select(WorkoutLog)
        .where(WorkoutLog.owner_id == user_id)
        .where(WorkoutLog.profile_id == profile_id)
        .order_by(desc(WorkoutLog.created_at))
        .limit(5)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def _fetch_recent_macros(user_id: str, profile_id: str, session: AsyncSession) -> list:
    """Fetch the 3 most recent macro entries scoped to a profile."""
    stmt = (
        select(MacroEntry)
        .where(MacroEntry.owner_id == user_id)
        .where(MacroEntry.profile_id == profile_id)
        .order_by(desc(MacroEntry.created_at))
        .limit(3)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def _build_context(profile: FitnessProfile, session: AsyncSession) -> str:
    """Build a rich context string from the user's stored data."""
    cached = _get_cached_context(profile.id)
    if cached is not None:
        return cached

    # Sequential fetch — AsyncSession is not safe for concurrent coroutines
    recent_logs = await _fetch_recent_workouts(profile.user_id, profile.id, session)
    recent_macros = await _fetch_recent_macros(profile.user_id, profile.id, session)

    goal_label = {
        "muscle": "Muscle Building / Hypertrophy",
        "weight_loss": "Weight Loss",
        "endurance": "Endurance / Cardio",
        "fit": "General Fitness / Maintenance",
    }.get(profile.goal, profile.goal.capitalize())

    ctx_lines: list[str] = [
        "=== USER FITNESS PROFILE ===",
        f"Name: {profile.name}",
        f"Age: {profile.age} | Gender: {profile.gender}",
        f"Weight: {profile.weight_kg} kg | Height: {profile.height_cm} cm",
        f"Goal: {goal_label}",
    ]

    if recent_logs:
        ctx_lines.append("\n=== RECENT WORKOUT LOGS (last 5) ===")
        for log in recent_logs:
            ctx_lines.append(
                f"- {log.log_date}: {log.sets}×{log.reps} @ {log.weight_kg} kg"
                + (f" | {log.notes}" if log.notes else "")
            )

    if recent_macros:
        ctx_lines.append("\n=== RECENT NUTRITION (last 3 days) ===")
        for m in recent_macros:
            ctx_lines.append(
                f"- {m.entry_date}: {m.calories} kcal | "
                f"P:{m.protein_g}g C:{m.carbs_g}g F:{m.fat_g}g"
            )

    context = "\n".join(ctx_lines)
    _set_cached_context(profile.id, context)
    return context


_SYSTEM_INSTRUCTION = """You are FitLog AI, a knowledgeable and encouraging senior fitness advisor.
You have access to the user's fitness profile, recent workout logs, and nutrition data.
Provide personalised, evidence-based advice. Be concise, warm, and motivating.
When discussing protein, reference ISSN/ACSM guidelines.
Never recommend unsafe practices. Always remind users to consult a doctor for medical concerns."""


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Chat with your AI Fitness Assistant",
    description=(
        "Send a message to FitLog AI. The assistant has full context of your profile, "
        "recent workouts, and nutrition history to give personalised advice."
    ),
)
async def chat(
    body: ChatRequest,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    _check_ai_rate(current_user.id)

    # Check if profile exists and belongs to current user
    stmt = select(FitnessProfile).where(
        (FitnessProfile.id == body.profile_id)
        & (FitnessProfile.user_id == current_user.id)
    )
    result = await session.execute(stmt)
    profile = result.scalars().first()

    if not profile:
        raise NotFoundError("Fitness profile not found. Create a profile first at POST /profile.")

    # Pass the already-fetched profile object to avoid a redundant DB query
    context = await _build_context(profile, session)
    full_message = f"{context}\n\n=== USER QUESTION ===\n{body.message}"

    client = _get_client()
    try:
        response = await client.chat.completions.create(
            model=_GROQ_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_INSTRUCTION},
                {"role": "user", "content": full_message},
            ],
            temperature=0.7,
            max_tokens=1024,
        )
        reply = response.choices[0].message.content
        return ChatResponse(reply=reply or "")
    except ExternalServiceError:
        raise
    except RateLimitError:
        logger.warning("Groq rate limit hit for user %s", current_user.id)
        raise ExternalServiceError("AI is rate-limited — wait a moment and try again.")
    except APITimeoutError:
        raise ExternalServiceError("AI took too long to respond — please try again.")
    except APIStatusError as exc:
        logger.error("Groq API error %s for user %s", exc.status_code, current_user.id)
        raise ExternalServiceError(f"AI service error ({exc.status_code}) — please try again.")
    except Exception as exc:
        logger.exception("Groq API call failed for user %s", current_user.id)
        raise ExternalServiceError("AI assistant is temporarily unavailable. Please try again later.") from exc
