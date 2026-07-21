"""Фикстуры для тестов приёма."""

from collections.abc import AsyncGenerator, AsyncIterator, Iterator
from contextlib import asynccontextmanager

import asyncpg
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from ingest.config import Settings, get_settings
from ingest.db import get_pool
from ingest.main import app

TEST_HMAC_SECRET = 'test-secret'


def build_test_settings() -> Settings:
    """Настройки с известным секретом."""
    return Settings(
        postgres_db='test',
        postgres_user='test',
        postgres_password='test',
        generic_json_hmac_secret=TEST_HMAC_SECRET,
    )


@pytest_asyncio.fixture
async def conn() -> AsyncIterator[asyncpg.Connection]:
    """Соединение в транзакции с откатом."""
    real = Settings()  # type: ignore[call-arg]
    connection = await asyncpg.connect(
        host=real.postgres_host,
        port=real.postgres_port,
        user=real.postgres_user,
        password=real.postgres_password,
        database=real.postgres_db,
    )
    transaction = connection.transaction()
    await transaction.start()
    try:
        yield connection
    finally:
        await transaction.rollback()
        await connection.close()


class _SingleConnPool:
    """Пул из одного тестового соединения."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[asyncpg.Connection]:
        yield self._conn


@pytest.fixture
def client(conn: asyncpg.Connection) -> Iterator[TestClient]:
    """Клиент с подменёнными зависимостями."""
    app.dependency_overrides[get_settings] = build_test_settings
    app.dependency_overrides[get_pool] = lambda: _SingleConnPool(conn)
    yield TestClient(app)
    app.dependency_overrides.clear()
