"""Приложение FastAPI приёма вебхуков."""

from typing import Annotated

import asyncpg
from fastapi import Depends, FastAPI

from ingest.db import get_conn, lifespan

app = FastAPI(lifespan=lifespan)


@app.get('/health')
async def health(
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
) -> dict[str, str]:
    """Проверка приложения и базы."""
    await conn.fetchval('SELECT 1')
    return {'status': 'ok'}
