"""
User Fitness Profile CRUD + Protein Target calculator.

Fitness profiles are user-specific training goals and metrics.

Protein multipliers (evidence-based, per ISSN / ACSM guidelines):
  - fit    (maintenance/recomp): 1.6 g / kg body weight
  - muscle (hypertrophy/bulk):   2.2 g / kg body weight
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, status, Depends, Header
from app.exceptions import NotFoundError, ConflictError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models import (
    ProfileGoalsOut,
    ProfileGoalsUpdate,
    ProteinTargetOut,
    UserProfileCreate,
    UserProfileOut,
    UserProfileUpdate,
)
from app.database import get_session
from app.db import User, FitnessProfile, ProfileGoals
from app.routers.auth import get_current_user_from_header

router = APIRouter(prefix="/profile", tags=["Fitness Profile"])

# Protein multipliers per goal (g per kg of body weight)
PROTEIN_MULTIPLIERS: dict[str, float] = {
    "fit": 1.8,
    "muscle": 2.2,
    "weight_loss": 2.0,
    "maintenance": 1.6,
    "general_health": 1.4,
    "endurance": 1.6,
    "flexibility": 1.4,
    "hypertrophy": 2.2,
    "strength": 2.0,
    "athletic_performance": 1.8,
}

GOAL_DESCRIPTIONS: dict[str, str] = {
    "fit": "maintenance and light body recomposition (1.8g/kg)",
    "muscle": "muscle hypertrophy and bulking phase (2.2g/kg)",
    "weight_loss": "fat loss while preserving lean mass (2.0g/kg)",
    "maintenance": "maintaining current body composition (1.6g/kg)",
    "general_health": "overall health and wellbeing (1.4g/kg)",
    "endurance": "endurance training and recovery (1.6g/kg)",
    "flexibility": "flexibility and mobility focus (1.4g/kg)",
    "hypertrophy": "maximum muscle growth (2.2g/kg)",
    "strength": "strength and power development (2.0g/kg)",
    "athletic_performance": "athletic performance optimization (1.8g/kg)",
}


@router.get(
    "/",
    response_model=list[UserProfileOut],
    summary="List user's fitness profiles",
    description="Get all fitness profiles for the logged-in user",
)
async def list_profiles(
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """List all fitness profiles for the authenticated user."""
    stmt = select(FitnessProfile).where(FitnessProfile.user_id == current_user.id)
    result = await session.execute(stmt)
    profiles = result.scalars().all()

    return [
        UserProfileOut(
            id=p.id,
            name=p.name,
            weight_kg=p.weight_kg,
            height_cm=p.height_cm,
            age=p.age,
            gender=p.gender,
            goal=p.goal,
        )
        for p in profiles
    ]


@router.get(
    "/{profile_id}",
    response_model=UserProfileOut,
    summary="Get a fitness profile",
)
async def get_profile(
    profile_id: str,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """Get a specific fitness profile (only if owned by current user)."""
    stmt = select(FitnessProfile).where(
        (FitnessProfile.id == profile_id) & (FitnessProfile.user_id == current_user.id)
    )
    result = await session.execute(stmt)
    profile = result.scalars().first()

    if not profile:
        raise NotFoundError("Profile not found")

    return UserProfileOut(
        id=profile.id,
        name=profile.name,
        weight_kg=profile.weight_kg,
        height_cm=profile.height_cm,
        age=profile.age,
        gender=profile.gender,
        goal=profile.goal,
    )


@router.post(
    "/",
    response_model=UserProfileOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a fitness profile",
    description="Create a new fitness profile for the logged-in user",
)
async def create_profile(
    body: UserProfileCreate,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """Create a new fitness profile for the authenticated user."""
    # Prevent duplicate profile names per user
    dup = await session.execute(
        select(FitnessProfile).where(
            (FitnessProfile.user_id == current_user.id) & (FitnessProfile.name == body.name)
        )
    )
    if dup.scalars().first():
        raise ConflictError(f"You already have a profile named '{body.name}'")

    new_profile = FitnessProfile(
        user_id=current_user.id,
        name=body.name,
        weight_kg=body.weight_kg,
        height_cm=body.height_cm,
        age=body.age,
        gender=body.gender,
        goal=body.goal,
    )

    session.add(new_profile)
    await session.commit()
    await session.refresh(new_profile)

    return UserProfileOut(
        id=new_profile.id,
        name=new_profile.name,
        weight_kg=new_profile.weight_kg,
        height_cm=new_profile.height_cm,
        age=new_profile.age,
        gender=new_profile.gender,
        goal=new_profile.goal,
    )


@router.put(
    "/{profile_id}",
    response_model=UserProfileOut,
    summary="Update a fitness profile",
)
async def update_profile(
    profile_id: str,
    body: UserProfileUpdate,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """Update a fitness profile (only if owned by current user)."""
    stmt = select(FitnessProfile).where(
        (FitnessProfile.id == profile_id) & (FitnessProfile.user_id == current_user.id)
    )
    result = await session.execute(stmt)
    profile = result.scalars().first()

    if not profile:
        raise NotFoundError("Profile not found")

    # Update fields that are provided
    update_data = body.model_dump(exclude_none=True)
    for key, value in update_data.items():
        setattr(profile, key, value)

    await session.commit()
    await session.refresh(profile)

    return UserProfileOut(
        id=profile.id,
        name=profile.name,
        weight_kg=profile.weight_kg,
        height_cm=profile.height_cm,
        age=profile.age,
        gender=profile.gender,
        goal=profile.goal,
    )


@router.delete(
    "/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a fitness profile",
)
async def delete_profile(
    profile_id: str,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """Delete a fitness profile (only if owned by current user)."""
    stmt = select(FitnessProfile).where(
        (FitnessProfile.id == profile_id) & (FitnessProfile.user_id == current_user.id)
    )
    result = await session.execute(stmt)
    profile = result.scalars().first()

    if not profile:
        raise NotFoundError("Profile not found")

    await session.delete(profile)
    await session.commit()


@router.get(
    "/{profile_id}/protein-target",
    response_model=ProteinTargetOut,
    summary="Calculate daily protein target",
    description=(
        "Returns the recommended daily protein intake in grams based on the fitness profile's "
        "body weight and fitness goal.\n\n"
        "- **fit** (maintenance / recomp): **1.6 g / kg** — per ISSN Position Stand\n"
        "- **muscle** (hypertrophy / bulk): **2.2 g / kg** — upper end for maximising MPS"
    ),
)
async def get_protein_target(
    profile_id: str,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """Get protein target for a specific fitness profile."""
    stmt = select(FitnessProfile).where(
        (FitnessProfile.id == profile_id) & (FitnessProfile.user_id == current_user.id)
    )
    result = await session.execute(stmt)
    profile = result.scalars().first()

    if not profile:
        raise NotFoundError("Profile not found")

    multiplier = PROTEIN_MULTIPLIERS.get(profile.goal, 1.6)
    protein_g = profile.weight_kg * multiplier
    goal_desc = GOAL_DESCRIPTIONS.get(profile.goal, "fitness goal")

    return ProteinTargetOut(
        user_id=profile.user_id,
        name=profile.name,
        weight_kg=profile.weight_kg,
        goal=profile.goal,
        protein_g=round(protein_g, 1),
        multiplier_g_per_kg=multiplier,
        recommendation=f"Based on {profile.weight_kg} kg and your goal of {goal_desc}, "
        f"aim for {protein_g:.0f}-{protein_g * 1.05:.0f}g of protein daily.",
    )


@router.get(
    "/{profile_id}/goals",
    response_model=ProfileGoalsOut,
    summary="Get goal targets for a fitness profile",
)
async def get_profile_goals(
    profile_id: str,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """Return the user-defined goals for a profile. Returns empty goals if none set yet."""
    # Verify profile ownership
    stmt = select(FitnessProfile).where(
        (FitnessProfile.id == profile_id) & (FitnessProfile.user_id == current_user.id)
    )
    result = await session.execute(stmt)
    if not result.scalars().first():
        raise NotFoundError("Profile not found")

    stmt = select(ProfileGoals).where(ProfileGoals.profile_id == profile_id)
    result = await session.execute(stmt)
    goals = result.scalars().first()

    return ProfileGoalsOut(
        profile_id=profile_id,
        daily_steps=goals.daily_steps if goals else None,
        weekly_workouts=goals.weekly_workouts if goals else None,
        daily_calories=goals.daily_calories if goals else None,
        daily_protein_g=goals.daily_protein_g if goals else None,
        daily_water_ml=goals.daily_water_ml if goals else None,
    )


@router.put(
    "/{profile_id}/goals",
    response_model=ProfileGoalsOut,
    summary="Set goal targets for a fitness profile",
)
async def upsert_profile_goals(
    profile_id: str,
    body: ProfileGoalsUpdate,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """Create or update the user-defined goals for a profile (upsert)."""
    # Verify profile ownership
    stmt = select(FitnessProfile).where(
        (FitnessProfile.id == profile_id) & (FitnessProfile.user_id == current_user.id)
    )
    result = await session.execute(stmt)
    if not result.scalars().first():
        raise NotFoundError("Profile not found")

    stmt = select(ProfileGoals).where(ProfileGoals.profile_id == profile_id)
    result = await session.execute(stmt)
    goals = result.scalars().first()

    updates = body.model_dump(exclude_none=True)
    if goals is None:
        goals = ProfileGoals(profile_id=profile_id, **updates)
        session.add(goals)
    else:
        for k, v in updates.items():
            setattr(goals, k, v)
        goals.updated_at = datetime.now(timezone.utc)

    await session.commit()
    await session.refresh(goals)

    return ProfileGoalsOut(
        profile_id=profile_id,
        daily_steps=goals.daily_steps,
        weekly_workouts=goals.weekly_workouts,
        daily_calories=goals.daily_calories,
        daily_protein_g=goals.daily_protein_g,
        daily_water_ml=goals.daily_water_ml,
    )
