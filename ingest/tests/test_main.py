"""Тесты приёма."""

from collections.abc import Callable

import asyncpg
from fastapi import status
from httpx2 import AsyncClient

DETAIL_UNKNOWN_SOURCE_CONTRACT = 'unknown_source'
BODY = b'{"order": 1}'
IDEMPOTENCY_KEY = 'key-1'
SOURCE = 'generic_json'


async def test_unknown_source_returns_404(client: AsyncClient) -> None:
    source_slug = 'not_generic_json'
    response = await client.post(f'/v1/webhooks/{source_slug}')
    assert response.status_code == status.HTTP_404_NOT_FOUND
    body = response.json()
    assert body['detail'] == DETAIL_UNKNOWN_SOURCE_CONTRACT


async def test_valid_webhook_is_accepted_and_stored(
    client: AsyncClient,
    conn: asyncpg.Connection,
    signed_headers: Callable[[bytes], dict[str, str]],
) -> None:
    headers = signed_headers(BODY) | {'Idempotency-Key': IDEMPOTENCY_KEY}
    response = await client.post(
        f'/v1/webhooks/{SOURCE}',
        content=BODY,
        headers=headers,
    )
    assert response.status_code == status.HTTP_202_ACCEPTED

    event_id = await conn.fetchval(
        'SELECT id FROM webhooks_event WHERE source=$1 AND idempotency_key=$2',
        SOURCE,
        IDEMPOTENCY_KEY,
    )
    assert event_id is not None
    outbox = await conn.fetchval(
        'SELECT count(*) FROM webhooks_outboxmessage WHERE event_id=$1',
        event_id,
    )
    assert outbox == 1
