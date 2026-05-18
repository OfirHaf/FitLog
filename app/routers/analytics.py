"""
Workout Summary & Analytics Router
Provides workout summaries (EX3) and a personal analytics API for the
progress dashboard.
"""

from datetime import date, datetime, timedelta, timezone
from collections import Counter, defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from app.exceptions import NotFoundError
from app.cache import cache, analytics_key
from app.config import settings
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.database import get_session
from app.db import (
    BodyMetricEntry,
    Exercise,
    FitnessProfile,
    HydrationEntry,
    MacroEntry,
    RecoveryEntry,
    SleepEntry,
    User,
    WorkoutLog,
)
from app.models import (
    AnalyticsSummaryOut,
    BodyMetricsTrendOut,
    NutritionTrendOut,
    StrengthProgressOut,
    WeeklyVolumeOut,
    WellnessTrendOut,
    WorkoutSummaryOut,
)
from app.routers.auth import get_current_user_from_header

router = APIRouter(prefix="/analytics", tags=["Analytics"])

# ─────────────────────────────────────────────
#  Helper utilities
# ─────────────────────────────────────────────

_WEEKLY_WORKOUT_GOAL = 5
_DAILY_CALORIE_GOAL = 2500.0


def _iso_week_label(d: date) -> str:
    """Return an ISO 8601 week label like '2026-W10'."""
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _epley_1rm(weight_kg: float, reps: int) -> float:
    """Epley formula: weight × (1 + reps / 30). Returns weight when reps == 1."""
    if reps <= 0:
        return weight_kg
    return round(weight_kg * (1 + reps / 30), 2)


# ─────────────────────────────────────────────
#  Legacy summary endpoint (EX3)
# ─────────────────────────────────────────────


@router.get(
    "/{profile_id}/workout-summary",
    response_model=WorkoutSummaryOut,
    summary="Get workout summary for a profile",
    description=(
        "Analyze recent workout logs and provide a summary including:\n"
        "- Total workouts this week\n"
        "- Total volume (weight x reps x sets)\n"
        "- Most worked muscle groups\n"
        "- Strength progression\n"
        "- Personalized recommendations"
    ),
)
async def get_workout_summary(
    profile_id: str,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
) -> WorkoutSummaryOut:
    """Generate workout summary and analytics from database."""
    stmt = select(FitnessProfile).where(
        (FitnessProfile.id == profile_id) & (FitnessProfile.user_id == current_user.id)
    )
    result = await session.execute(stmt)
    profile = result.scalars().first()

    if not profile:
        raise NotFoundError("Profile not found")

    stmt = select(WorkoutLog).where(WorkoutLog.owner_id == current_user.id)
    result = await session.execute(stmt)
    logs = result.scalars().all()

    # Fetch all referenced exercises in one query instead of N+1
    exercise_ids = {log.exercise_id for log in logs if log.exercise_id}
    exercises_by_id: dict = {}
    if exercise_ids:
        stmt = select(Exercise).where(
            Exercise.id.in_(exercise_ids) & (Exercise.owner_id == current_user.id)
        )
        result = await session.execute(stmt)
        exercises_by_id = {e.id: e for e in result.scalars().all()}

    total_volume = 0.0
    muscle_group_counts: Counter = Counter()
    total_workouts = len(logs)
    weekly_workouts = 0

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    for log in logs:
        volume = log.sets * log.reps * log.weight_kg
        total_volume += volume

        exercise = exercises_by_id.get(log.exercise_id)
        if exercise:
            muscle_group_counts[exercise.muscle_group] += 1

        log_ts = log.created_at.replace(tzinfo=timezone.utc) if log.created_at and log.created_at.tzinfo is None else log.created_at
        if log_ts and log_ts >= week_ago:
            weekly_workouts += 1

    most_worked = (
        muscle_group_counts.most_common(1)[0][0] if muscle_group_counts else "N/A"
    )

    if profile.goal == "muscle":
        recommendation = (
            f"You're lifting with great volume ({total_volume:.0f} kg total)! "
            f"Keep pushing leg volume to match your {profile.weight_kg:.0f} kg body weight. "
            f"Consider adding more compound movements."
        )
    else:
        recommendation = (
            f"Nice consistency with {total_workouts} workouts! "
            f"You're at {most_worked} focus. Aim for balanced muscle group distribution."
        )

    return WorkoutSummaryOut(
        user_id=profile.id,
        name=profile.name,
        total_workouts=total_workouts,
        total_volume_kg=total_volume,
        most_worked_muscle_group=most_worked,
        workouts_per_week=weekly_workouts,
        recommendation=recommendation,
    )


# ─────────────────────────────────────────────
#  Personal Analytics — Progress Dashboard
# ─────────────────────────────────────────────


@router.get(
    "/summary",
    response_model=AnalyticsSummaryOut,
    summary="Dashboard summary",
    description="High-level progress summary: workouts this week, avg calories, weight change, streak, and all-time totals.",
)
async def get_summary(
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
) -> AnalyticsSummaryOut:
    cache_key = analytics_key(str(current_user.id), "summary")
    if cached := await cache.get(cache_key):
        return AnalyticsSummaryOut(**cached)

    today = date.today()
    week_start = today - timedelta(days=today.weekday())  # Monday of current week
    thirty_days_ago = today - timedelta(days=30)
    seven_days_ago = today - timedelta(days=7)

    # All workout logs
    stmt = select(WorkoutLog).where(WorkoutLog.owner_id == current_user.id)
    result = await session.execute(stmt)
    all_logs = result.scalars().all()

    total_workouts_all_time = len(all_logs)

    workouts_this_week = sum(
        1 for log in all_logs if log.log_date >= week_start.isoformat()
    )

    # Average calories over last 7 days
    stmt = select(MacroEntry).where(
        (MacroEntry.owner_id == current_user.id)
        & (MacroEntry.entry_date >= seven_days_ago.isoformat())
    )
    result = await session.execute(stmt)
    recent_macros = result.scalars().all()
    avg_calories_7d = (
        sum(m.calories for m in recent_macros) / len(recent_macros)
        if recent_macros
        else 0.0
    )

    # Weight change over last 30 days
    stmt = select(BodyMetricEntry).where(
        (BodyMetricEntry.owner_id == current_user.id)
        & (BodyMetricEntry.entry_date >= thirty_days_ago.isoformat())
        & (BodyMetricEntry.weight_kg.is_not(None))  # type: ignore[attr-defined]
    )
    result = await session.execute(stmt)
    weight_entries = sorted(
        [e for e in result.scalars().all() if e.weight_kg is not None],
        key=lambda e: e.entry_date,
    )
    if len(weight_entries) >= 2:
        weight_change_30d = round(
            weight_entries[-1].weight_kg - weight_entries[0].weight_kg, 2  # type: ignore[operator]
        )
    else:
        weight_change_30d = 0.0

    # Current streak: consecutive days with at least one log up to today
    log_dates = {log.log_date for log in all_logs}
    streak = 0
    check_date = today
    while check_date.isoformat() in log_dates:
        streak += 1
        check_date -= timedelta(days=1)

    result_out = AnalyticsSummaryOut(
        workouts_this_week=workouts_this_week,
        workouts_goal=_WEEKLY_WORKOUT_GOAL,
        avg_calories_7d=round(avg_calories_7d, 1),
        calorie_goal=_DAILY_CALORIE_GOAL,
        weight_change_30d=weight_change_30d,
        current_streak_days=streak,
        total_workouts_all_time=total_workouts_all_time,
    )
    await cache.set(cache_key, result_out.model_dump(), ttl=settings.cache_ttl_analytics)
    return result_out


@router.get(
    "/workout-volume",
    response_model=list[WeeklyVolumeOut],
    summary="Weekly workout volume",
    description="Returns weekly workout volume (sets × reps × weight_kg) for the last N weeks.",
)
async def get_workout_volume(
    weeks: int = Query(default=8, ge=1, le=52, description="Number of weeks to look back"),
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
) -> list[WeeklyVolumeOut]:
    cutoff = date.today() - timedelta(weeks=weeks)

    stmt = select(WorkoutLog).where(
        (WorkoutLog.owner_id == current_user.id)
        & (WorkoutLog.log_date >= cutoff.isoformat())
    )
    result = await session.execute(stmt)
    logs = result.scalars().all()

    # Aggregate by ISO week
    week_volume: dict[str, float] = defaultdict(float)
    week_count: dict[str, int] = defaultdict(int)

    for log in logs:
        week_label = _iso_week_label(date.fromisoformat(log.log_date))
        week_volume[week_label] += log.sets * log.reps * log.weight_kg
        week_count[week_label] += 1

    return [
        WeeklyVolumeOut(
            week=week,
            total_volume=round(week_volume[week], 2),
            session_count=week_count[week],
        )
        for week in sorted(week_volume)
    ]


@router.get(
    "/strength-progress",
    response_model=list[StrengthProgressOut],
    summary="Strength progression for an exercise",
    description=(
        "Returns max weight and estimated 1RM (Epley formula) per workout date "
        "for a given exercise name."
    ),
)
async def get_strength_progress(
    exercise_name: str = Query(..., description="Exercise name to filter by (case-insensitive)"),
    weeks: int = Query(default=12, ge=1, le=104, description="Number of weeks to look back"),
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
) -> list[StrengthProgressOut]:
    cutoff = date.today() - timedelta(weeks=weeks)

    # Resolve exercise IDs by name (case-insensitive)
    stmt = select(Exercise).where(Exercise.owner_id == current_user.id)
    result = await session.execute(stmt)
    matching_ids = {
        e.id
        for e in result.scalars().all()
        if e.name.lower() == exercise_name.lower()
    }

    if not matching_ids:
        return []

    stmt = select(WorkoutLog).where(
        (WorkoutLog.owner_id == current_user.id)
        & (WorkoutLog.exercise_id.in_(matching_ids))  # type: ignore[attr-defined]
        & (WorkoutLog.log_date >= cutoff.isoformat())
    )
    result = await session.execute(stmt)
    logs = result.scalars().all()

    # Per date: keep the row with the heaviest weight
    best_by_date: dict[str, WorkoutLog] = {}
    for log in logs:
        existing = best_by_date.get(log.log_date)
        if existing is None or log.weight_kg > existing.weight_kg:
            best_by_date[log.log_date] = log

    return [
        StrengthProgressOut(
            date=d,
            max_weight_kg=best_by_date[d].weight_kg,
            estimated_1rm=_epley_1rm(best_by_date[d].weight_kg, best_by_date[d].reps),
        )
        for d in sorted(best_by_date)
    ]


@router.get(
    "/body-metrics-trend",
    response_model=list[BodyMetricsTrendOut],
    summary="Body metrics trend",
    description="Returns weight, BMI, and body fat percentage over time.",
)
async def get_body_metrics_trend(
    days: int = Query(default=90, ge=1, le=730, description="Number of days to look back"),
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
) -> list[BodyMetricsTrendOut]:
    cutoff = date.today() - timedelta(days=days)

    # Fetch user's latest profile for BMI calculation.
    # Note: BMI is computed using the current profile height for all historical
    # entries. BodyMetricEntry does not store height, so historical height at
    # time of entry is unavailable. For adults this is acceptable since height
    # is stable; a future improvement could add height_cm to BodyMetricEntry.
    stmt = select(FitnessProfile).where(
        FitnessProfile.user_id == current_user.id
    ).order_by(desc(FitnessProfile.created_at))
    result = await session.execute(stmt)
    latest_profile = result.scalars().first()
    height_cm: Optional[float] = latest_profile.height_cm if latest_profile else None

    stmt = select(BodyMetricEntry).where(
        (BodyMetricEntry.owner_id == current_user.id)
        & (BodyMetricEntry.entry_date >= cutoff.isoformat())
    )
    result = await session.execute(stmt)
    entries = sorted(result.scalars().all(), key=lambda e: e.entry_date)

    out: list[BodyMetricsTrendOut] = []
    for entry in entries:
        bmi: Optional[float] = None
        if entry.weight_kg is not None and height_cm is not None and height_cm > 0:
            height_m = height_cm / 100.0
            bmi = round(entry.weight_kg / (height_m ** 2), 1)

        out.append(
            BodyMetricsTrendOut(
                date=entry.entry_date,
                weight_kg=entry.weight_kg,
                bmi=bmi,
                body_fat_pct=entry.body_fat_pct,
            )
        )

    return out


@router.get(
    "/nutrition-trend",
    response_model=list[NutritionTrendOut],
    summary="Nutrition trend",
    description="Returns daily calorie and macro totals for the last N days.",
)
async def get_nutrition_trend(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to look back"),
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
) -> list[NutritionTrendOut]:
    cutoff = date.today() - timedelta(days=days)

    stmt = select(MacroEntry).where(
        (MacroEntry.owner_id == current_user.id)
        & (MacroEntry.entry_date >= cutoff.isoformat())
    )
    result = await session.execute(stmt)
    entries = sorted(result.scalars().all(), key=lambda e: e.entry_date)

    # Aggregate multiple entries on the same day
    day_totals: dict[str, dict[str, float]] = defaultdict(
        lambda: {"calories": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
    )
    for entry in entries:
        day_totals[entry.entry_date]["calories"] += entry.calories
        day_totals[entry.entry_date]["protein_g"] += entry.protein_g
        day_totals[entry.entry_date]["carbs_g"] += entry.carbs_g
        day_totals[entry.entry_date]["fat_g"] += entry.fat_g

    return [
        NutritionTrendOut(
            date=d,
            calories=round(day_totals[d]["calories"], 1),
            protein_g=round(day_totals[d]["protein_g"], 1),
            carbs_g=round(day_totals[d]["carbs_g"], 1),
            fat_g=round(day_totals[d]["fat_g"], 1),
        )
        for d in sorted(day_totals)
    ]


@router.get(
    "/wellness-trend",
    response_model=list[WellnessTrendOut],
    summary="Wellness trend",
    description=(
        "Returns combined daily wellness metrics: sleep, hydration, and a composite "
        "recovery score derived from energy, soreness (inverted), and mood."
    ),
)
async def get_wellness_trend(
    days: int = Query(default=14, ge=1, le=365, description="Number of days to look back"),
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
) -> list[WellnessTrendOut]:
    cutoff = date.today() - timedelta(days=days)
    cutoff_iso = cutoff.isoformat()

    # Fetch all three sources in parallel queries
    sleep_stmt = select(SleepEntry).where(
        (SleepEntry.owner_id == current_user.id)
        & (SleepEntry.entry_date >= cutoff_iso)
    )
    hydration_stmt = select(HydrationEntry).where(
        (HydrationEntry.owner_id == current_user.id)
        & (HydrationEntry.entry_date >= cutoff_iso)
    )
    recovery_stmt = select(RecoveryEntry).where(
        (RecoveryEntry.owner_id == current_user.id)
        & (RecoveryEntry.entry_date >= cutoff_iso)
    )

    sleep_result, hydration_result, recovery_result = (
        await session.execute(sleep_stmt),
        await session.execute(hydration_stmt),
        await session.execute(recovery_stmt),
    )

    # Index by date (latest entry per day wins)
    sleep_by_date: dict[str, SleepEntry] = {}
    for s in sleep_result.scalars().all():
        sleep_by_date[s.entry_date] = s

    hydration_by_date: dict[str, float] = defaultdict(float)
    for h in hydration_result.scalars().all():
        hydration_by_date[h.entry_date] += h.water_ml

    recovery_by_date: dict[str, RecoveryEntry] = {}
    for r in recovery_result.scalars().all():
        recovery_by_date[r.entry_date] = r

    all_dates = sorted(
        set(sleep_by_date) | set(hydration_by_date) | set(recovery_by_date)
    )

    out: list[WellnessTrendOut] = []
    for d in all_dates:
        sleep_entry = sleep_by_date.get(d)
        recovery_entry = recovery_by_date.get(d)

        recovery_score: Optional[float] = None
        if recovery_entry is not None:
            # Composite score: energy + (6 - soreness) + mood, normalised to 1–5
            raw = (
                recovery_entry.energy_level
                + (6 - recovery_entry.soreness_level)
                + recovery_entry.mood
            )
            # raw range: 3 (all at worst) to 15 (all at best) → map to 1–5
            recovery_score = round(1 + (raw - 3) / 12 * 4, 2)

        out.append(
            WellnessTrendOut(
                date=d,
                sleep_hours=sleep_entry.sleep_hours if sleep_entry else None,
                sleep_quality=sleep_entry.sleep_quality if sleep_entry else None,
                hydration_ml=hydration_by_date.get(d),
                recovery_score=recovery_score,
            )
        )

    return out
