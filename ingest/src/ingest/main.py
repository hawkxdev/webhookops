"""Приложение FastAPI приёма вебхуков."""

from typing import Annotated

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Request, status

from ingest.config import Settings, get_settings
from ingest.db import get_conn, lifespan
from ingest.security import verify_signature

app = FastAPI(lifespan=lifespan)

KNOWN_SOURCE = 'generic_json'
MAX_BODY_BYTES = 1_048_576

HEADER_SIGNATURE = 'X-Signature-256'
HEADER_TIMESTAMP = 'X-Timestamp'
HEADER_CONTENT_LENGTH = 'Content-Length'

DETAIL_UNKNOWN_SOURCE = 'unknown_source'
DETAIL_INVALID_SIGNATURE = 'invalid_signature'
DETAIL_BODY_TOO_LARGE = 'body_too_large'


@app.get('/health')
async def health(
    conn: Annotated[asyncpg.Connection, Depends(get_conn)],
) -> dict[str, str]:
    """Проверка приложения и базы."""
    await conn.fetchval('SELECT 1')
    return {'status': 'ok'}


@app.post('/v1/webhooks/{source_slug}', status_code=status.HTTP_202_ACCEPTED)
async def receive_webhook(
    source_slug: str,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    """Приём вебхука источника."""
    if source_slug != KNOWN_SOURCE:
        raise HTTPException(status.HTTP_404_NOT_FOUND, DETAIL_UNKNOWN_SOURCE)

    signature = request.headers.get(HEADER_SIGNATURE)
    timestamp = request.headers.get(HEADER_TIMESTAMP)
    if signature is None or timestamp is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, DETAIL_INVALID_SIGNATURE
        )

    content_length = request.headers.get(HEADER_CONTENT_LENGTH)
    if content_length is not None and int(content_length) > MAX_BODY_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, DETAIL_BODY_TOO_LARGE
        )

    body = await request.body()
    if not verify_signature(
        body,
        signature=signature,
        secret=settings.generic_json_hmac_secret,
        timestamp=timestamp,
        tolerance=settings.hmac_tolerance,
    ):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, DETAIL_INVALID_SIGNATURE
        )

    return {'status': 'accepted'}
