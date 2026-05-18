"""
FitLog – Pydantic models for all domain resources.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field, EmailStr, field_validator


# ─────────────────────────────────────────────
#  Authentication & User Management
# ─────────────────────────────────────────────


class UserRegister(BaseModel):
    """User registration request."""

    email: EmailStr = Field(..., examples=["user@example.com"])
    password: str = Field(
        ..., min_length=8, max_length=100, examples=["SecurePass123!"]
    )
    name: str = Field(..., min_length=1, max_length=100, examples=["Alex"])


class UserLogin(BaseModel):
    """User login request."""

    email: EmailStr = Field(..., examples=["user@example.com"])
    password: str = Field(..., examples=["SecurePass123!"])


class TokenResponse(BaseModel):
    """JWT token response after login."""

    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    user_id: str
    name: str
    expires_in: int = 86400  # 24 hours


class UserResponse(BaseModel):
    """User profile response (without password)."""

    id: str
    email: str
    name: str


# ─────────────────────────────────────────────
#  Exercise
# ─────────────────────────────────────────────


class ExerciseBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, examples=["Barbell Squat"])
    category: str = Field(..., examples=["strength", "cardio", "flexibility"])
    muscle_group: str = Field(
        ...,
        examples=["legs", "chest", "back", "shoulders", "arms", "core", "full-body"],
    )
    description: Optional[str] = Field(None, max_length=500)


class ExerciseCreate(ExerciseBase):
    pass


class ExerciseUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    category: Optional[str] = None
    muscle_group: Optional[str] = None
    description: Optional[str] = None


class ExerciseOut(ExerciseBase):
    id: str


# ─────────────────────────────────────────────
#  Workout Log
# ─────────────────────────────────────────────


class WorkoutLogBase(BaseModel):
    """Workout log base model with type-safe date handling."""
    exercise_id: str = Field(..., description="Exercise ID")
    profile_id: Optional[str] = Field(None, description="Fitness profile ID")
    log_date: date = Field(..., examples=["2026-03-25"], description="Workout date (YYYY-MM-DD)")
    sets: int = Field(..., ge=1, le=100, description="Number of sets")
    reps: int = Field(..., ge=1, le=1000, description="Reps per set")
    weight_kg: float = Field(..., ge=0, le=1000, examples=[80.0], description="Weight in kg")
    duration_minutes: Optional[int] = Field(None, ge=1, le=600, description="Duration in minutes")
    notes: Optional[str] = Field(None, max_length=500, description="Workout notes")
    
    @field_validator('log_date', mode='before')
    @classmethod
    def validate_log_date(cls, v: Union[str, date]) -> date:
        """Accept both string and date objects, normalize to date."""
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            try:
                return date.fromisoformat(v)
            except ValueError:
                raise ValueError(f"Invalid date format: {v}. Use YYYY-MM-DD")
        raise ValueError(f"Date must be string or date object, got {type(v).__name__}")


class WorkoutLogCreate(WorkoutLogBase):
    """Request model for creating workout logs."""
    pass


class WorkoutLogUpdate(BaseModel):
    """Request model for updating workout logs (all fields optional)."""
    exercise_id: Optional[str] = None
    log_date: Optional[date] = None
    sets: Optional[int] = Field(None, ge=1, le=100)
    reps: Optional[int] = Field(None, ge=1, le=1000)
    weight_kg: Optional[float] = Field(None, ge=0, le=1000)
    duration_minutes: Optional[int] = Field(None, ge=1, le=600)
    notes: Optional[str] = None
    
    @field_validator('log_date', mode='before')
    @classmethod
    def validate_log_date(cls, v: Union[str, date, None]) -> Optional[date]:
        """Accept both string and date objects, normalize to date."""
        if v is None:
            return None
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            try:
                return date.fromisoformat(v)
            except ValueError:
                raise ValueError(f"Invalid date format: {v}. Use YYYY-MM-DD")
        raise ValueError(f"Date must be string or date object, got {type(v).__name__}")


class WorkoutLogOut(WorkoutLogBase):
    """Response model for workout logs (includes ID)."""
    id: str = Field(..., description="Workout log ID")
    profile_id: Optional[str] = Field(None, description="Fitness profile ID")


# ─────────────────────────────────────────────
#  Macro Entry (daily nutrition)
# ─────────────────────────────────────────────


class MacroEntryBase(BaseModel):
    """Macro entry model with type-safe date handling."""
    profile_id: Optional[str] = Field(None, description="Fitness profile ID")
    entry_date: date = Field(..., examples=["2026-03-25"], description="Entry date (YYYY-MM-DD)")
    calories: float = Field(..., ge=0, le=20000, examples=[2200.0], description="Total calories")
    protein_g: float = Field(..., ge=0, le=1000, examples=[180.0], description="Protein in grams")
    carbs_g: float = Field(..., ge=0, le=2000, examples=[250.0], description="Carbs in grams")
    fat_g: float = Field(..., ge=0, le=1000, examples=[70.0], description="Fat in grams")
    notes: Optional[str] = Field(None, max_length=500, description="Notes")
    
    @field_validator('entry_date', mode='before')
    @classmethod
    def validate_entry_date(cls, v: Union[str, date]) -> date:
        """Accept both string and date objects, normalize to date."""
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            try:
                return date.fromisoformat(v)
            except ValueError:
                raise ValueError(f"Invalid date format: {v}. Use YYYY-MM-DD")
        raise ValueError(f"Date must be string or date object, got {type(v).__name__}")


class MacroEntryCreate(MacroEntryBase):
    """Request model for creating macro entries."""
    pass


class MacroEntryUpdate(BaseModel):
    """Request model for updating macro entries (all fields optional)."""
    entry_date: Optional[date] = None
    calories: Optional[float] = Field(None, ge=0, le=20000)
    protein_g: Optional[float] = Field(None, ge=0, le=1000)
    carbs_g: Optional[float] = Field(None, ge=0, le=2000)
    fat_g: Optional[float] = Field(None, ge=0, le=1000)
    notes: Optional[str] = None
    
    @field_validator('entry_date', mode='before')
    @classmethod
    def validate_entry_date(cls, v: Union[str, date, None]) -> Optional[date]:
        """Accept both string and date objects, normalize to date."""
        if v is None:
            return None
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            try:
                return date.fromisoformat(v)
            except ValueError:
                raise ValueError(f"Invalid date format: {v}. Use YYYY-MM-DD")
        raise ValueError(f"Date must be string or date object, got {type(v).__name__}")


class MacroEntryOut(MacroEntryBase):
    """Response model for macro entries (includes ID)."""
    id: str = Field(..., description="Macro entry ID")
    profile_id: Optional[str] = Field(None, description="Fitness profile ID")


class FoodAnalysisRequest(BaseModel):
    """Request to analyze food description and calculate nutrition."""

    food_description: str = Field(
        ...,
        min_length=3,
        max_length=500,
        examples=["2 eggs, bacon, and toast with butter"],
    )


class NutritionAnalysisResponse(BaseModel):
    """Response with calculated nutrition from AI analysis."""

    food_description: str
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    analysis: str


# ─────────────────────────────────────────────
#  User Profile
# ─────────────────────────────────────────────


class UserProfileBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, examples=["Alex"])
    weight_kg: float = Field(..., gt=0, le=500, examples=[80.0])
    height_cm: float = Field(..., gt=0, le=300, examples=[175.0])
    age: int = Field(..., ge=10, le=120, examples=[28])
    gender: Literal["male", "female", "other"] = Field(..., examples=["male"])
    goal: Literal["fit", "muscle", "weight_loss", "maintenance", "general_health", "endurance", "flexibility", "hypertrophy", "strength", "athletic_performance"] = Field(..., examples=["muscle"])


class UserProfileCreate(UserProfileBase):
    pass


class UserProfileUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    weight_kg: Optional[float] = Field(None, gt=0, le=500)
    height_cm: Optional[float] = Field(None, gt=0, le=300)
    age: Optional[int] = Field(None, ge=10, le=120)
    gender: Optional[Literal["male", "female", "other"]] = None
    goal: Optional[Literal["fit", "muscle", "weight_loss", "maintenance", "general_health", "endurance", "flexibility", "hypertrophy", "strength", "athletic_performance"]] = None


class UserProfileOut(UserProfileBase):
    id: str


# ─────────────────────────────────────────────
#  Protein Target response
# ─────────────────────────────────────────────


class ProteinTargetOut(BaseModel):
    user_id: str
    name: str
    weight_kg: float
    goal: str
    protein_g: float
    multiplier_g_per_kg: float
    recommendation: str


# ─────────────────────────────────────────────
#  AI Assistant
# ─────────────────────────────────────────────


class ChatRequest(BaseModel):
    profile_id: str  # Profile ID (not user ID) - FitnessProfile.id
    message: str = Field(..., min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    reply: str


# ─────────────────────────────────────────────
#  Workout Summary & Analytics (EX3 Enhancement)
# ─────────────────────────────────────────────


class WorkoutSummaryOut(BaseModel):
    user_id: str
    name: str
    total_workouts: int
    total_volume_kg: float
    most_worked_muscle_group: str
    workouts_per_week: int
    recommendation: str


# ─────────────────────────────────────────────
#  Personal Analytics API — Progress Dashboard
# ─────────────────────────────────────────────


class AnalyticsSummaryOut(BaseModel):
    """High-level progress summary for the dashboard header."""

    workouts_this_week: int = Field(..., description="Workout sessions logged in the current 7-day window")
    workouts_goal: int = Field(..., description="Weekly workout goal (fixed at 5)")
    avg_calories_7d: float = Field(..., description="Average daily calorie intake over the last 7 days")
    calorie_goal: float = Field(..., description="Daily calorie goal (fixed at 2500)")
    weight_change_30d: float = Field(..., description="Weight change in kg over the last 30 days (negative = loss)")
    current_streak_days: int = Field(..., description="Consecutive days with at least one workout up to today")
    total_workouts_all_time: int = Field(..., description="All-time total workout log entries for the user")


class WeeklyVolumeOut(BaseModel):
    """Weekly workout volume bucket."""

    week: str = Field(..., description="ISO week label, e.g. '2026-W10'")
    total_volume: float = Field(..., description="Sum of sets × reps × weight_kg across all logs in the week")
    session_count: int = Field(..., description="Number of distinct workout log entries in the week")


class StrengthProgressOut(BaseModel):
    """Single data point for a strength-progression chart."""

    date: str = Field(..., description="ISO date of the workout log entry (YYYY-MM-DD)")
    max_weight_kg: float = Field(..., description="Heaviest weight lifted for this exercise on that date")
    estimated_1rm: float = Field(..., description="Epley estimated 1-rep max: weight × (1 + reps / 30)")


class BodyMetricsTrendOut(BaseModel):
    """Body composition snapshot for a single day."""

    date: str = Field(..., description="ISO date (YYYY-MM-DD)")
    weight_kg: Optional[float] = Field(None, description="Body weight in kg")
    bmi: Optional[float] = Field(None, description="BMI derived from weight and the user's stored height")
    body_fat_pct: Optional[float] = Field(None, description="Body fat percentage if recorded")


class NutritionTrendOut(BaseModel):
    """Daily macro totals for the nutrition trend chart."""

    date: str = Field(..., description="ISO date (YYYY-MM-DD)")
    calories: float = Field(..., description="Total calories logged")
    protein_g: float = Field(..., description="Protein in grams")
    carbs_g: float = Field(..., description="Carbohydrates in grams")
    fat_g: float = Field(..., description="Fat in grams")


class WellnessTrendOut(BaseModel):
    """Combined wellness snapshot merging sleep, hydration, and recovery data."""

    date: str = Field(..., description="ISO date (YYYY-MM-DD)")
    sleep_hours: Optional[float] = Field(None, description="Hours slept (from sleep log)")
    sleep_quality: Optional[int] = Field(None, description="Sleep quality score 1–5")
    hydration_ml: Optional[float] = Field(None, description="Total water intake in ml")
    recovery_score: Optional[float] = Field(
        None,
        description=(
            "Composite recovery score (1–5) derived from energy_level, "
            "soreness_level (inverted), and mood"
        ),
    )


# ─────────────────────────────────────────────
#  Sleep Entry
# ─────────────────────────────────────────────


class SleepEntryBase(BaseModel):
    profile_id: Optional[str] = Field(None, description="Fitness profile ID")
    entry_date: date = Field(..., examples=["2026-03-25"], description="Entry date (YYYY-MM-DD)")
    sleep_hours: float = Field(..., ge=0, le=24, examples=[7.5], description="Hours slept")
    sleep_quality: int = Field(..., ge=1, le=5, examples=[4], description="1=poor, 5=excellent")
    notes: Optional[str] = Field(None, max_length=500)

    @field_validator('entry_date', mode='before')
    @classmethod
    def validate_entry_date(cls, v: Union[str, date]) -> date:
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            try:
                return date.fromisoformat(v)
            except ValueError:
                raise ValueError(f"Invalid date format: {v}. Use YYYY-MM-DD")
        raise ValueError(f"Date must be string or date object, got {type(v).__name__}")


class SleepEntryCreate(SleepEntryBase):
    pass


class SleepEntryOut(SleepEntryBase):
    id: str = Field(..., description="Sleep entry ID")
    profile_id: Optional[str] = Field(None, description="Fitness profile ID")


# ─────────────────────────────────────────────
#  Hydration Entry
# ─────────────────────────────────────────────


class HydrationEntryBase(BaseModel):
    profile_id: Optional[str] = Field(None, description="Fitness profile ID")
    entry_date: date = Field(..., examples=["2026-03-25"], description="Entry date (YYYY-MM-DD)")
    water_ml: float = Field(..., ge=0, le=20000, examples=[2500.0], description="Water in ml")
    notes: Optional[str] = Field(None, max_length=500)

    @field_validator('entry_date', mode='before')
    @classmethod
    def validate_entry_date(cls, v: Union[str, date]) -> date:
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            try:
                return date.fromisoformat(v)
            except ValueError:
                raise ValueError(f"Invalid date format: {v}. Use YYYY-MM-DD")
        raise ValueError(f"Date must be string or date object, got {type(v).__name__}")


class HydrationEntryCreate(HydrationEntryBase):
    pass


class HydrationEntryOut(HydrationEntryBase):
    id: str = Field(..., description="Hydration entry ID")
    profile_id: Optional[str] = Field(None, description="Fitness profile ID")


# ─────────────────────────────────────────────
#  Body Metric Entry
# ─────────────────────────────────────────────


class BodyMetricEntryBase(BaseModel):
    profile_id: Optional[str] = Field(None, description="Fitness profile ID")
    entry_date: date = Field(..., examples=["2026-03-25"], description="Entry date (YYYY-MM-DD)")
    weight_kg: Optional[float] = Field(None, ge=0, le=500, examples=[80.0], description="Weight in kg")
    body_fat_pct: Optional[float] = Field(None, ge=0, le=100, examples=[15.0], description="Body fat %")
    waist_cm: Optional[float] = Field(None, ge=0, le=300, examples=[82.0], description="Waist in cm")
    resting_hr: Optional[int] = Field(None, ge=20, le=250, examples=[65], description="Resting heart rate")
    notes: Optional[str] = Field(None, max_length=500)

    @field_validator('entry_date', mode='before')
    @classmethod
    def validate_entry_date(cls, v: Union[str, date]) -> date:
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            try:
                return date.fromisoformat(v)
            except ValueError:
                raise ValueError(f"Invalid date format: {v}. Use YYYY-MM-DD")
        raise ValueError(f"Date must be string or date object, got {type(v).__name__}")


class BodyMetricEntryCreate(BodyMetricEntryBase):
    pass


class BodyMetricEntryOut(BodyMetricEntryBase):
    id: str = Field(..., description="Body metric entry ID")
    profile_id: Optional[str] = Field(None, description="Fitness profile ID")


# ─────────────────────────────────────────────
#  Recovery Entry
# ─────────────────────────────────────────────


class RecoveryEntryBase(BaseModel):
    profile_id: Optional[str] = Field(None, description="Fitness profile ID")
    entry_date: date = Field(..., examples=["2026-03-25"], description="Entry date (YYYY-MM-DD)")
    soreness_level: int = Field(..., ge=1, le=5, examples=[3], description="1=none, 5=extreme")
    energy_level: int = Field(..., ge=1, le=5, examples=[4], description="1=exhausted, 5=energized")
    stress_level: int = Field(..., ge=1, le=5, examples=[2], description="1=relaxed, 5=very stressed")
    mood: int = Field(..., ge=1, le=5, examples=[4], description="1=low, 5=great")
    notes: Optional[str] = Field(None, max_length=500)

    @field_validator('entry_date', mode='before')
    @classmethod
    def validate_entry_date(cls, v: Union[str, date]) -> date:
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            try:
                return date.fromisoformat(v)
            except ValueError:
                raise ValueError(f"Invalid date format: {v}. Use YYYY-MM-DD")
        raise ValueError(f"Date must be string or date object, got {type(v).__name__}")


class RecoveryEntryCreate(RecoveryEntryBase):
    pass


class RecoveryEntryOut(RecoveryEntryBase):
    id: str = Field(..., description="Recovery entry ID")
    profile_id: Optional[str] = Field(None, description="Fitness profile ID")


# ─────────────────────────────────────────────
#  Wellness Update Schemas (partial PATCH)
# ─────────────────────────────────────────────


class SleepEntryUpdate(BaseModel):
    entry_date: Optional[date] = None
    sleep_hours: Optional[float] = Field(None, ge=0, le=24)
    sleep_quality: Optional[int] = Field(None, ge=1, le=5)
    notes: Optional[str] = Field(None, max_length=500)

    @field_validator("entry_date", mode="before")
    @classmethod
    def validate_entry_date(cls, v: object) -> Optional[date]:
        if v is None:
            return None
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            try:
                return date.fromisoformat(v)
            except ValueError:
                raise ValueError(f"Invalid date format: {v}. Use YYYY-MM-DD")
        raise ValueError(f"Expected date or str, got {type(v).__name__}")


class HydrationEntryUpdate(BaseModel):
    entry_date: Optional[date] = None
    water_ml: Optional[float] = Field(None, ge=0, le=20000)
    notes: Optional[str] = Field(None, max_length=500)

    @field_validator("entry_date", mode="before")
    @classmethod
    def validate_entry_date(cls, v: object) -> Optional[date]:
        if v is None:
            return None
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            try:
                return date.fromisoformat(v)
            except ValueError:
                raise ValueError(f"Invalid date format: {v}. Use YYYY-MM-DD")
        raise ValueError(f"Expected date or str, got {type(v).__name__}")


class BodyMetricEntryUpdate(BaseModel):
    entry_date: Optional[date] = None
    weight_kg: Optional[float] = Field(None, ge=0, le=500)
    body_fat_pct: Optional[float] = Field(None, ge=0, le=100)
    waist_cm: Optional[float] = Field(None, ge=0, le=300)
    resting_hr: Optional[int] = Field(None, ge=20, le=250)
    notes: Optional[str] = Field(None, max_length=500)

    @field_validator("entry_date", mode="before")
    @classmethod
    def validate_entry_date(cls, v: object) -> Optional[date]:
        if v is None:
            return None
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            try:
                return date.fromisoformat(v)
            except ValueError:
                raise ValueError(f"Invalid date format: {v}. Use YYYY-MM-DD")
        raise ValueError(f"Expected date or str, got {type(v).__name__}")


class RecoveryEntryUpdate(BaseModel):
    entry_date: Optional[date] = None
    soreness_level: Optional[int] = Field(None, ge=1, le=5)
    energy_level: Optional[int] = Field(None, ge=1, le=5)
    stress_level: Optional[int] = Field(None, ge=1, le=5)
    mood: Optional[int] = Field(None, ge=1, le=5)
    notes: Optional[str] = Field(None, max_length=500)

    @field_validator("entry_date", mode="before")
    @classmethod
    def validate_entry_date(cls, v: object) -> Optional[date]:
        if v is None:
            return None
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            try:
                return date.fromisoformat(v)
            except ValueError:
                raise ValueError(f"Invalid date format: {v}. Use YYYY-MM-DD")
        raise ValueError(f"Expected date or str, got {type(v).__name__}")


# ─────────────────────────────────────────────
#  Profile Goals
# ─────────────────────────────────────────────


class ProfileGoalsOut(BaseModel):
    """User-defined goal targets for a fitness profile."""

    profile_id: str
    daily_steps: Optional[int] = None
    weekly_workouts: Optional[int] = None
    daily_calories: Optional[int] = None
    daily_protein_g: Optional[float] = None
    daily_water_ml: Optional[float] = None


class ProfileGoalsUpdate(BaseModel):
    """Partial update for profile goals — all fields optional."""

    daily_steps: Optional[int] = Field(None, ge=0, le=100000)
    weekly_workouts: Optional[int] = Field(None, ge=0, le=14)
    daily_calories: Optional[int] = Field(None, ge=0, le=20000)
    daily_protein_g: Optional[float] = Field(None, ge=0, le=500)
    daily_water_ml: Optional[float] = Field(None, ge=0, le=10000)


# ─────────────────────────────────────────────
#  Step Entry
# ─────────────────────────────────────────────


class StepEntryBase(BaseModel):
    profile_id: Optional[str] = Field(None, description="Fitness profile ID")
    entry_date: date = Field(..., examples=["2026-03-25"], description="Entry date (YYYY-MM-DD)")
    steps: int = Field(..., ge=0, le=100000, description="Step count")
    distance_km: Optional[float] = Field(None, ge=0, le=200, description="Distance in km")
    active_minutes: Optional[int] = Field(None, ge=0, le=1440, description="Active minutes")
    notes: Optional[str] = Field(None, max_length=300)

    @field_validator("entry_date", mode="before")
    @classmethod
    def validate_entry_date(cls, v: object) -> date:
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            try:
                return date.fromisoformat(v)
            except ValueError:
                raise ValueError(f"Invalid date format: {v}. Use YYYY-MM-DD")
        raise ValueError(f"Expected date or str, got {type(v).__name__}")


class StepEntryCreate(StepEntryBase):
    pass


class StepEntryOut(StepEntryBase):
    id: str = Field(..., description="Step entry ID")


class StepEntryUpdate(BaseModel):
    entry_date: Optional[date] = None
    steps: Optional[int] = Field(None, ge=0, le=100000)
    distance_km: Optional[float] = Field(None, ge=0, le=200)
    active_minutes: Optional[int] = Field(None, ge=0, le=1440)
    notes: Optional[str] = Field(None, max_length=300)

    @field_validator("entry_date", mode="before")
    @classmethod
    def validate_entry_date(cls, v: object) -> Optional[date]:
        if v is None:
            return None
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            try:
                return date.fromisoformat(v)
            except ValueError:
                raise ValueError(f"Invalid date format: {v}. Use YYYY-MM-DD")
        raise ValueError(f"Expected date or str, got {type(v).__name__}")
