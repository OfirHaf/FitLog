"""Shared pytest fixtures for FitLog tests."""
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.database as _db_module
from app.main import app

_TEST_PASSWORD = "TestPass1!"


@pytest.fixture
def anyio_backend() -> str:
    """Use asyncio for all pytest.mark.anyio tests in this suite."""
    return "asyncio"


@pytest.fixture
def client() -> TestClient:
    """TestClient backed by a fresh in-memory SQLite DB.

    Patches the database module globals so the lifespan (create_db_and_tables)
    and all request sessions operate on the same isolated in-memory database.
    Each test gets a clean slate — no data bleeds between tests and fitlog.db
    is never touched during test runs.

    A unique user is registered and pre-authenticated before the fixture yields.
    """
    test_engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    test_session_maker = sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    # Swap the module-level engine and session factory so that both
    # create_db_and_tables() (lifespan) and get_session() (requests) use our
    # isolated in-memory database for the duration of this test.
    _original_engine = _db_module.engine
    _original_session_maker = _db_module.async_session_maker
    _db_module.engine = test_engine
    _db_module.async_session_maker = test_session_maker

    try:
        with TestClient(app, raise_server_exceptions=True) as test_client:
            email = f"test_{uuid.uuid4().hex[:8]}@example.com"
            resp = test_client.post(
                "/auth/register",
                json={"email": email, "password": _TEST_PASSWORD, "name": "Test User"},
            )
            assert resp.status_code == 201, f"Test user registration failed: {resp.text}"
            token = resp.json()["access_token"]
            test_client.headers.update({"Authorization": f"Bearer {token}"})
            yield test_client
    finally:
        _db_module.engine = _original_engine
        _db_module.async_session_maker = _original_session_maker


@pytest.fixture
def auth_headers(client: TestClient) -> dict:
    """Return the Authorization headers used by the `client` fixture."""
    return {"Authorization": client.headers["Authorization"]}


@pytest.fixture
def sample_exercise(client: TestClient) -> dict:
    resp = client.post(
        "/exercises/",
        json={
            "name": "Barbell Squat",
            "category": "strength",
            "muscle_group": "legs",
            "description": "King of compound movements",
        },
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture
def sample_profile(client: TestClient) -> dict:
    resp = client.post(
        "/profile/",
        json={
            "name": "Alex",
            "weight_kg": 80.0,
            "height_cm": 175.0,
            "age": 28,
            "gender": "male",
            "goal": "muscle",
        },
    )
    assert resp.status_code == 201
    return resp.json()
