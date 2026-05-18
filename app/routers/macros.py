"""Macro / nutrition entries CRUD router with database persistence."""

import json
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, status, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from openai import AsyncOpenAI, RateLimitError, APITimeoutError, APIStatusError

from app.cache import cache, food_key
from app.config import settings
from app.exceptions import NotFoundError, ExternalServiceError
from app.models import (
    MacroEntryCreate,
    MacroEntryOut,
    MacroEntryUpdate,
    FoodAnalysisRequest,
    NutritionAnalysisResponse,
)
from app.db import MacroEntry, User
from app.database import get_session
from app.routers.auth import get_current_user_from_header

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/macros", tags=["Macro Entries"])


_groq_client: AsyncOpenAI | None = None

def _get_groq_client() -> AsyncOpenAI:
    global _groq_client
    if _groq_client is None:
        _groq_client = AsyncOpenAI(api_key=settings.groq_api_key, base_url="https://api.groq.com/openai/v1")
    return _groq_client


@router.post(
    "/analyze-food",
    response_model=NutritionAnalysisResponse,
    summary="Analyze food and calculate macros using AI",
)
async def analyze_food_nutrition(
    body: FoodAnalysisRequest,
    current_user: User = Depends(get_current_user_from_header),
):
    """
    Analyze food description using Groq AI and return estimated nutritional values.
    Takes a natural language description of food (e.g., "2 eggs, bacon, and toast")
    and returns calculated calories, protein, carbs, and fat.
    """
    ck = food_key(body.food_description)
    if cached := await cache.get(ck):
        return NutritionAnalysisResponse(**cached)

    try:
        client = _get_groq_client()

        # Sanitize: truncate to prevent excessively long inputs
        safe_description = body.food_description[:500]

        response = await client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a nutrition database expert. "
                        "The user will provide a food item description. "
                        "Respond ONLY with a valid JSON object containing exactly these keys: "
                        "calories (number, kcal), protein_g (number), carbs_g (number), "
                        "fat_g (number), analysis (string, 1-2 sentences). "
                        "Use standard nutrition database values. Be realistic and accurate."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Food item to analyze:\n"
                        "---\n"
                        f"{safe_description}\n"
                        "---\n"
                        "Return the nutritional breakdown as JSON."
                    ),
                },
            ],
            temperature=0.3,
            max_tokens=500,
            response_format={"type": "json_object"},
        )

        response_text = response.choices[0].message.content.strip()
        nutrition_data = json.loads(response_text)

        required_fields = ["calories", "protein_g", "carbs_g", "fat_g", "analysis"]
        if not all(field in nutrition_data for field in required_fields):
            raise ValueError(f"AI response missing fields. Got: {list(nutrition_data.keys())}")

        result_out = NutritionAnalysisResponse(
            food_description=body.food_description,
            calories=float(nutrition_data["calories"]),
            protein_g=float(nutrition_data["protein_g"]),
            carbs_g=float(nutrition_data["carbs_g"]),
            fat_g=float(nutrition_data["fat_g"]),
            analysis=str(nutrition_data["analysis"]),
        )
        await cache.set(ck, result_out.model_dump(), ttl=settings.cache_ttl_food_analysis)
        return result_out

    except ExternalServiceError:
        raise
    except RateLimitError:
        logger.warning("Groq rate limit hit during food analysis")
        raise ExternalServiceError("AI is rate-limited — wait a moment and try again.")
    except APITimeoutError:
        logger.warning("Groq API timeout during food analysis")
        raise ExternalServiceError("AI took too long to respond — please try again.")
    except APIStatusError as exc:
        logger.error("Groq API error %s: %s", exc.status_code, exc.message)
        raise ExternalServiceError(f"AI service error ({exc.status_code}) — please try again.")
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Food analysis JSON parse failed: %s", exc)
        raise ExternalServiceError("AI returned an unexpected format — please rephrase your meal description.")
    except Exception:
        logger.exception("Food analysis failed for: %s", body.food_description)
        raise ExternalServiceError("Food analysis is temporarily unavailable. Please try again.")


@router.get(
    "/", response_model=list[MacroEntryOut], summary="List user's macro entries"
)
async def list_macros(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    profile_id: Optional[str] = Query(
        None, description="Filter entries by fitness profile"
    ),
    start_date: Optional[date] = Query(
        None, description="Filter entries from this date (inclusive)"
    ),
    end_date: Optional[date] = Query(
        None, description="Filter entries until this date (inclusive)"
    ),
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """List macros for the authenticated user with pagination and optional filtering."""
    stmt = select(MacroEntry).where(MacroEntry.owner_id == current_user.id)

    if profile_id:
        stmt = stmt.where(MacroEntry.profile_id == profile_id)
    if start_date:
        stmt = stmt.where(MacroEntry.entry_date >= str(start_date))
    if end_date:
        stmt = stmt.where(MacroEntry.entry_date <= str(end_date))

    stmt = stmt.order_by(MacroEntry.entry_date.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return result.scalars().all()


@router.get(
    "/{entry_id}", response_model=MacroEntryOut, summary="Get a macro entry by ID"
)
async def get_macro(
    entry_id: str,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """Get a specific macro entry (only if owned by user)."""
    stmt = select(MacroEntry).where(
        (MacroEntry.id == entry_id) & (MacroEntry.owner_id == current_user.id)
    )
    result = await session.execute(stmt)
    record = result.scalars().first()

    if not record:
        raise NotFoundError("Macro entry not found")
    return record


@router.post(
    "/",
    response_model=MacroEntryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Log daily macros",
)
async def create_macro(
    body: MacroEntryCreate,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """Create a new macro entry for the authenticated user.
    
    Note: Pydantic validators handle date conversion (accepts both date objects and ISO strings).
    """
    data = body.model_dump()
    # Convert date to ISO string for database storage
    data["entry_date"] = body.entry_date.isoformat()
    entry = MacroEntry(**data, owner_id=current_user.id)
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


@router.put("/{entry_id}", response_model=MacroEntryOut, summary="Update a macro entry")
async def update_macro(
    entry_id: str,
    body: MacroEntryUpdate,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """Update a macro entry (only if owned by user)."""
    stmt = select(MacroEntry).where(
        (MacroEntry.id == entry_id) & (MacroEntry.owner_id == current_user.id)
    )
    result = await session.execute(stmt)
    record = result.scalars().first()

    if not record:
        raise NotFoundError("Macro entry not found")

    # Update only provided fields (Pydantic validators already normalized types)
    update_data = body.model_dump(exclude_none=True)
    
    # Convert date to ISO string if present
    if "entry_date" in update_data and update_data["entry_date"] is not None:
        update_data["entry_date"] = update_data["entry_date"].isoformat()
    
    for key, value in update_data.items():
        setattr(record, key, value)

    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


@router.delete(
    "/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a macro entry",
)
async def delete_macro(
    entry_id: str,
    current_user: User = Depends(get_current_user_from_header),
    session: AsyncSession = Depends(get_session),
):
    """Delete a macro entry (only if owned by user)."""
    stmt = select(MacroEntry).where(
        (MacroEntry.id == entry_id) & (MacroEntry.owner_id == current_user.id)
    )
    result = await session.execute(stmt)
    record = result.scalars().first()

    if not record:
        raise NotFoundError("Macro entry not found")

    await session.delete(record)
    await session.commit()
