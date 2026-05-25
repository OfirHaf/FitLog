"""
Admin router — role-protected endpoints (Session 11, EX3).

All routes here require `role == "admin"` in the JWT.
Regular user tokens are rejected with HTTP 403.

To create an admin user:
    UPDATE users SET role = 'admin' WHERE email = 'you@example.com';

Or via the Alembic migration in alembic/versions/.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from app.database import get_session
from app.db import (
    BodyMetricEntry,
    HydrationEntry,
    MacroEntry,
    RecoveryEntry,
    SleepEntry,
    StepEntry,
    User,
    WorkoutLog,
)
from app.routers.auth import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get(
    "/stats",
    summary="Platform-wide statistics (admin only)",
    description=(
        "Returns aggregate counts across all users. "
        "Requires a JWT with `role: admin`. "
        "Regular user tokens receive HTTP 403."
    ),
)
async def admin_stats(
    _admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return platform-wide aggregate statistics. Admin scope required."""
    async def _count(model) -> int:
        result = await session.execute(select(func.count()).select_from(model))
        return result.scalar_one()

    total_users = await _count(User)
    total_workouts = await _count(WorkoutLog)
    total_macros = await _count(MacroEntry)
    total_sleep = await _count(SleepEntry)
    total_hydration = await _count(HydrationEntry)
    total_body_metrics = await _count(BodyMetricEntry)
    total_recovery = await _count(RecoveryEntry)
    total_steps = await _count(StepEntry)

    logger.info(
        "Admin stats requested — %d users, %d workouts",
        total_users,
        total_workouts,
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "users": total_users,
        "workout_logs": total_workouts,
        "macro_entries": total_macros,
        "sleep_entries": total_sleep,
        "hydration_entries": total_hydration,
        "body_metric_entries": total_body_metrics,
        "recovery_entries": total_recovery,
        "step_entries": total_steps,
    }
