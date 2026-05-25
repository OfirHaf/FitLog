"""
SQLModel definitions for FitLog database persistence.
This replaces the in-memory repository with SQLite/PostgreSQL backed storage.
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlmodel import SQLModel, Field, Relationship


class User(SQLModel, table=True):
    """User account model stored in database.
    
    Indexes:
    - email: unique index for fast login lookups
    - name: index for search/filtering
    """

    __tablename__ = "users"

    id: Optional[str] = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    email: str = Field(max_length=100, unique=True, index=True, description="Unique email for login")
    hashed_password: str
    name: str = Field(max_length=100, index=True, description="User full name")
    role: str = Field(default="user", max_length=20, description="Role: 'user' or 'admin'")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    fitness_profiles: list["FitnessProfile"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    exercises: list["Exercise"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    workout_logs: list["WorkoutLog"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    macro_entries: list["MacroEntry"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    sleep_entries: list["SleepEntry"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    hydration_entries: list["HydrationEntry"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    body_metric_entries: list["BodyMetricEntry"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    recovery_entries: list["RecoveryEntry"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )
    step_entries: list["StepEntry"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class FitnessProfileBase(SQLModel):
    """Base fields for fitness profiles (per-user training goals)."""

    name: str = Field(max_length=100, index=True)
    weight_kg: float = Field(gt=0, le=500)
    height_cm: float = Field(gt=0, le=300)
    age: int = Field(ge=10, le=120)
    gender: str = Field(max_length=20)  # "male", "female", "other"
    goal: str = Field(max_length=50)  # "fit", "muscle"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FitnessProfile(FitnessProfileBase, table=True):
    """Fitness profile model - user's training goal and metrics."""

    __tablename__ = "fitness_profiles"

    id: Optional[str] = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    user_id: str = Field(foreign_key="users.id")

    # Relationships
    owner: User = Relationship(back_populates="fitness_profiles")


class ProfileGoals(SQLModel, table=True):
    """User-defined goal targets per fitness profile (1:1)."""

    __tablename__ = "profile_goals"

    id: Optional[str] = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    profile_id: str = Field(foreign_key="fitness_profiles.id", unique=True, index=True)
    daily_steps: Optional[int] = Field(None, ge=0, le=100000, description="Steps/day goal")
    weekly_workouts: Optional[int] = Field(None, ge=0, le=14, description="Sessions/week goal")
    daily_calories: Optional[int] = Field(None, ge=0, le=20000, description="kcal/day goal (overrides TDEE)")
    daily_protein_g: Optional[float] = Field(None, ge=0, le=500, description="Protein g/day goal")
    daily_water_ml: Optional[float] = Field(None, ge=0, le=10000, description="Water ml/day goal")
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# Keep UserProfile as an alias for backward compatibility
UserProfile = User


class ExerciseBase(SQLModel):
    """Base fields for exercises."""

    name: str = Field(max_length=100, index=True)
    category: str = Field(max_length=50)  # "strength", "cardio", "flexibility"
    muscle_group: str = Field(max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Exercise(ExerciseBase, table=True):
    """Exercise model stored in database.
    
    Indexes:
    - owner_id: foreign key index for fast user lookups
    - name: index for search
    """

    __tablename__ = "exercises"

    id: Optional[str] = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    owner_id: str = Field(foreign_key="users.id", index=True, description="Exercise owner")

    # Relationships
    owner: User = Relationship(back_populates="exercises")
    workout_logs: list["WorkoutLog"] = Relationship(back_populates="exercise")


class WorkoutLogBase(SQLModel):
    """Base fields for workout logs.
    
    Note on types:
    - log_date: stored as ISO string (YYYY-MM-DD) for database portability
      Input via API accepts both date objects and strings (Pydantic validator normalizes)
      Output via API always returns ISO string
    """

    exercise_id: str = Field(foreign_key="exercises.id")
    log_date: str = Field(..., description="ISO format date (YYYY-MM-DD)")
    sets: int = Field(ge=1, le=100)
    reps: int = Field(ge=1, le=1000)
    weight_kg: float = Field(ge=0, le=1000)
    duration_minutes: Optional[int] = Field(None, ge=1, le=600)
    notes: Optional[str] = Field(None, max_length=500)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class WorkoutLog(WorkoutLogBase, table=True):
    """Workout log model stored in database.
    
    Indexes:
    - owner_id: foreign key index for fast user lookup
    - profile_id: foreign key index for profile filtering
    
    Performance notes:
    - Queries filter by owner_id first (indexed)
    - Date range queries on log_date benefit from owner_id index
    - For large datasets, consider adding compound index (owner_id, log_date)
    """

    __tablename__ = "workout_logs"

    id: Optional[str] = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    owner_id: str = Field(foreign_key="users.id", index=True, description="Log owner")
    profile_id: Optional[str] = Field(
        default=None, foreign_key="fitness_profiles.id", index=True, description="Associated fitness profile"
    )

    # Relationships
    owner: User = Relationship(back_populates="workout_logs")
    exercise: Optional[Exercise] = Relationship(back_populates="workout_logs")


class MacroEntryBase(SQLModel):
    """Base fields for macro entries.
    
    Note on types:
    - entry_date: stored as ISO string (YYYY-MM-DD) for database portability
      Input via API accepts both date objects and strings (Pydantic validator normalizes)
      Output via API always returns ISO string
    """

    entry_date: str = Field(..., description="ISO format date (YYYY-MM-DD)")
    calories: float = Field(ge=0, le=20000)
    protein_g: float = Field(ge=0, le=1000)
    carbs_g: float = Field(ge=0, le=2000)
    fat_g: float = Field(ge=0, le=1000)
    notes: Optional[str] = Field(None, max_length=500)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MacroEntry(MacroEntryBase, table=True):
    """Macro entry model stored in database.
    
    Indexes:
    - owner_id: foreign key index for fast user lookup
    - profile_id: foreign key index for profile filtering
    
    Performance notes:
    - Queries filter by owner_id first (indexed)
    - Date range queries on entry_date benefit from owner_id index
    - For large datasets, consider adding compound index (owner_id, entry_date)
    """

    __tablename__ = "macro_entries"

    id: Optional[str] = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    owner_id: str = Field(foreign_key="users.id", index=True, description="Entry owner")
    profile_id: Optional[str] = Field(
        default=None, foreign_key="fitness_profiles.id", index=True, description="Associated fitness profile"
    )

    # Relationships
    owner: User = Relationship(back_populates="macro_entries")


class SleepEntryBase(SQLModel):
    """Base fields for sleep entries."""

    entry_date: str = Field(..., description="ISO format date (YYYY-MM-DD)")
    sleep_hours: float = Field(ge=0, le=24)
    sleep_quality: int = Field(ge=1, le=5, description="1=poor, 5=excellent")
    notes: Optional[str] = Field(None, max_length=500)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SleepEntry(SleepEntryBase, table=True):
    """Sleep tracking entry."""

    __tablename__ = "sleep_entries"

    id: Optional[str] = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    owner_id: str = Field(foreign_key="users.id", index=True)
    profile_id: Optional[str] = Field(default=None, foreign_key="fitness_profiles.id", index=True)

    owner: User = Relationship(back_populates="sleep_entries")


class HydrationEntryBase(SQLModel):
    """Base fields for hydration entries."""

    entry_date: str = Field(..., description="ISO format date (YYYY-MM-DD)")
    water_ml: float = Field(ge=0, le=20000)
    notes: Optional[str] = Field(None, max_length=500)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class HydrationEntry(HydrationEntryBase, table=True):
    """Hydration tracking entry."""

    __tablename__ = "hydration_entries"

    id: Optional[str] = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    owner_id: str = Field(foreign_key="users.id", index=True)
    profile_id: Optional[str] = Field(default=None, foreign_key="fitness_profiles.id", index=True)

    owner: User = Relationship(back_populates="hydration_entries")


class BodyMetricEntryBase(SQLModel):
    """Base fields for body metric entries."""

    entry_date: str = Field(..., description="ISO format date (YYYY-MM-DD)")
    weight_kg: Optional[float] = Field(None, ge=0, le=500)
    body_fat_pct: Optional[float] = Field(None, ge=0, le=100)
    waist_cm: Optional[float] = Field(None, ge=0, le=300)
    resting_hr: Optional[int] = Field(None, ge=20, le=250)
    notes: Optional[str] = Field(None, max_length=500)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BodyMetricEntry(BodyMetricEntryBase, table=True):
    """Body metric tracking entry."""

    __tablename__ = "body_metric_entries"

    id: Optional[str] = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    owner_id: str = Field(foreign_key="users.id", index=True)
    profile_id: Optional[str] = Field(default=None, foreign_key="fitness_profiles.id", index=True)

    owner: User = Relationship(back_populates="body_metric_entries")


class RecoveryEntryBase(SQLModel):
    """Base fields for recovery entries."""

    entry_date: str = Field(..., description="ISO format date (YYYY-MM-DD)")
    soreness_level: int = Field(ge=1, le=5, description="1=none, 5=extreme")
    energy_level: int = Field(ge=1, le=5, description="1=exhausted, 5=energized")
    stress_level: int = Field(ge=1, le=5, description="1=relaxed, 5=very stressed")
    mood: int = Field(ge=1, le=5, description="1=low, 5=great")
    notes: Optional[str] = Field(None, max_length=500)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RecoveryEntry(RecoveryEntryBase, table=True):
    """Recovery tracking entry."""

    __tablename__ = "recovery_entries"

    id: Optional[str] = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    owner_id: str = Field(foreign_key="users.id", index=True)
    profile_id: Optional[str] = Field(default=None, foreign_key="fitness_profiles.id", index=True)

    owner: User = Relationship(back_populates="recovery_entries")


class StepEntry(SQLModel, table=True):
    """Daily step count tracking entry."""

    __tablename__ = "step_entries"

    id: Optional[str] = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    owner_id: str = Field(foreign_key="users.id", index=True)
    profile_id: Optional[str] = Field(default=None, foreign_key="fitness_profiles.id", index=True)
    entry_date: str = Field(..., description="ISO format date (YYYY-MM-DD)")
    steps: int = Field(ge=0, le=100000)
    distance_km: Optional[float] = Field(None, ge=0, le=200)
    active_minutes: Optional[int] = Field(None, ge=0, le=1440)
    notes: Optional[str] = Field(None, max_length=300)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    owner: User = Relationship(back_populates="step_entries")
