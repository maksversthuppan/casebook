from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db import get_db
from app.main import app
from app.models import Advocate, Base
from app.security import hash_password

TEST_DB = "dcms_test"


def _test_url() -> str:
    base = get_settings().database_url
    return base.rsplit("/", 1)[0] + f"/{TEST_DB}"


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def engine():
    """Create the test database if it is missing, then build the schema.

    Schema comes from the metadata rather than Alembic: these tests check
    behaviour, and a migration bug is caught by running migrations, not here.
    """
    admin = create_async_engine(get_settings().database_url, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        exists = await conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_DB}
        )
        if not exists:
            await conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    await admin.dispose()

    eng = create_async_engine(_test_url())
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine) -> AsyncIterator:
    """A clean database per test. Truncate is cheaper than recreating the schema."""
    tables = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(engine, db) -> AsyncIterator[httpx.AsyncClient]:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def advocates(db) -> dict[str, Advocate]:
    people = {
        "anil": Advocate(
            name="Anil Kumar", email="anil@example.com", password_hash=hash_password("pw-anil")
        ),
        "priya": Advocate(
            name="Priya Menon", email="priya@example.com", password_hash=hash_password("pw-priya")
        ),
    }
    for person in people.values():
        db.add(person)
    await db.commit()
    return people


@pytest_asyncio.fixture
async def signed_in(client, advocates) -> httpx.AsyncClient:
    r = await client.post("/api/auth/login", json={"email": "priya@example.com", "password": "pw-priya"})
    assert r.status_code == 200, r.text
    return client
