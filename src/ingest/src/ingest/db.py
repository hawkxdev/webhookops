"""Пул соединений и зависимости."""

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, Request

from ingest.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Пул соединений на время жизни приложения."""
    settings = get_settings()
    pool = await asyncpg.create_pool(
        host=settings.postgres_host,
        port=settings.postgres_port,
        user=settings.postgres_user,
        password=settings.postgres_password,
        database=settings.postgres_db,
    )
    app.state.pool = pool
    try:
        yield
    finally:
        await pool.close()


async def get_conn(request: Request) -> AsyncIterator[asyncpg.Connection]:
    """Соединение из пула на запрос."""
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        yield conn


async def get_pool(request: Request) -> asyncpg.Pool:
    """Общий пул соединений."""
    return request.app.state.pool
