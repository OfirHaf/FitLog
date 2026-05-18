"""Exercises CRUD router with database persistence."""
from fastapi import APIRouter, status, Query, Depends
from app.exceptions import NotFoundError, ConflictError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models import ExerciseCreate, ExerciseOut, ExerciseUpdate
from app.db import Exercise, User
from app.database import get_session
from app.routers.auth import get_current_user_from_header

router = APIRouter(prefix="/exercises", tags=["Exercises"])


@router.get("/", response_model=list[ExerciseOut], summary="List user's exercises")
async def list_exercises(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session)
):
    """List exercises for the authenticated user with pagination."""
    stmt = select(Exercise).where(Exercise.owner_id == current_user.id).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get("/{exercise_id}", response_model=ExerciseOut, summary="Get an exercise by ID")
async def get_exercise(
    exercise_id: str,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session)
):
    """Get a specific exercise (only if owned by user)."""
    stmt = select(Exercise).where(
        (Exercise.id == exercise_id) & (Exercise.owner_id == current_user.id)
    )
    result = await session.execute(stmt)
    record = result.scalars().first()
    
    if not record:
        raise NotFoundError("Exercise not found")
    return record


@router.post("/", response_model=ExerciseOut, status_code=status.HTTP_201_CREATED, summary="Create a new exercise")
async def create_exercise(
    body: ExerciseCreate,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session)
):
    """Create a new exercise for the authenticated user."""
    # Prevent duplicate exercise names per user
    dup = await session.execute(
        select(Exercise).where(
            (Exercise.owner_id == current_user.id) & (Exercise.name == body.name)
        )
    )
    if dup.scalars().first():
        raise ConflictError(f"You already have an exercise named '{body.name}'")

    exercise = Exercise(
        **body.model_dump(),
        owner_id=current_user.id
    )
    session.add(exercise)
    await session.commit()
    await session.refresh(exercise)
    return exercise


@router.put("/{exercise_id}", response_model=ExerciseOut, summary="Update an exercise")
async def update_exercise(
    exercise_id: str,
    body: ExerciseUpdate,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session)
):
    """Update an exercise (only if owned by user)."""
    stmt = select(Exercise).where(
        (Exercise.id == exercise_id) & (Exercise.owner_id == current_user.id)
    )
    result = await session.execute(stmt)
    record = result.scalars().first()
    
    if not record:
        raise NotFoundError("Exercise not found")
    
    # Update only provided fields
    update_data = body.model_dump(exclude_none=True)
    for key, value in update_data.items():
        setattr(record, key, value)
    
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


@router.delete("/{exercise_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an exercise")
async def delete_exercise(
    exercise_id: str,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session)
):
    """Delete an exercise (only if owned by user)."""
    stmt = select(Exercise).where(
        (Exercise.id == exercise_id) & (Exercise.owner_id == current_user.id)
    )
    result = await session.execute(stmt)
    record = result.scalars().first()
    
    if not record:
        raise NotFoundError("Exercise not found")
    
    await session.delete(record)
    await session.commit()
