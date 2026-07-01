"""Фикстуры для тестов записи."""

import os
from pathlib import Path

import asyncpg
import pytest_asyncio

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


def _load_env():
    """Читает .env файл в окружение."""
    env_path = WORKSPACE_ROOT / '.env'
    if not env_path.exists():
        return
    for raw in env_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        os.environ.setdefault(key.strip(), value.strip())


_load_env()


@pytest_asyncio.fixture
async def conn():
    """Соединение в транзакции с откатом."""
    connection = await asyncpg.connect(
        host=os.environ.get('POSTGRES_HOST', '127.0.0.1'),
        port=os.environ.get('POSTGRES_PORT', 5432),
        user=os.environ.get('POSTGRES_USER'),
        password=os.environ.get('POSTGRES_PASSWORD'),
        database=os.environ.get('POSTGRES_DB'),
    )
    transaction = connection.transaction()
    await transaction.start()
    try:
        yield connection
    finally:
        await transaction.rollback()
        await connection.close()
    