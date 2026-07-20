"""Приложение FastAPI приёма вебхуков."""

import hashlib
import json
from typing import Annotated

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Request, status

from ingest.config import Settings, get_settings
from ingest.db import get_conn, get_pool, lifespan
from ingest.security import verify_signature
from shared.persistence import persist_event

app = FastAPI(lifespan=lifespan)

KNOWN_SOURCE = 'generic_json'
MAX_BODY_BYTES = 1_048_576
MAX_IDEMPOTENCY_KEY_LENGTH = 255

HEADER_SIGNATURE = 'X-Signature-256'
HEADER_TIMESTAMP = 'X-Timestamp'
HEADER_CONTENT_LENGTH = 'Content-Length'
HEADER_IDEMPOTENCY_KEY = 'Idempotency-Key'

DETAIL_UNKNOWN_SOURCE = 'unknown_source'
DETAIL_INVALID_SIGNATURE = 'invalid_signature'
DETAIL_BODY_TOO_LARGE = 'body_too_large'
DETAIL_MALFORMED_JSON = 'malformed_json'
DETAIL_PAYLOAD_NOT_OBJECT = 'payload_not_object'
DETAIL_INVALID_IDEMPOTENCY_KEY = 'invalid_idempotency_key'


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
    pool: Annotated[asyncpg.Pool, Depends(get_pool)],
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

    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, RecursionError):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, DETAIL_MALFORMED_JSON
        ) from None
    if not isinstance(payload, dict):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, DETAIL_PAYLOAD_NOT_OBJECT
        )

    received_key = request.headers.get(HEADER_IDEMPOTENCY_KEY)
    if received_key and (
        not received_key.isascii()
        or len(received_key) > MAX_IDEMPOTENCY_KEY_LENGTH
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, DETAIL_INVALID_IDEMPOTENCY_KEY
        )

    idempotency_key = received_key or hashlib.sha256(body).hexdigest()

    async with pool.acquire() as conn:
        await persist_event(
            conn,
            source=KNOWN_SOURCE,
            idempotency_key=idempotency_key,
            payload=payload,
        )

    return {'status': 'accepted'}
