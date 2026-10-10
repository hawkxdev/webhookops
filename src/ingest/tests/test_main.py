"""Тесты приёма."""

import hashlib
from collections.abc import Callable

import asyncpg
from fastapi import status
from httpx2 import AsyncClient

DETAIL_UNKNOWN_SOURCE_CONTRACT = 'unknown_source'
DETAIL_MALFORMED_JSON_CONTRACT = 'malformed_json'
DETAIL_PAYLOAD_NOT_OBJECT_CONTRACT = 'payload_not_object'
DETAIL_INVALID_IDEMPOTENCY_KEY_CONTRACT = 'invalid_idempotency_key'
BODY = b'{"order": 1}'
IDEMPOTENCY_KEY = 'key-1'
SOURCE = 'generic_json'
MALFORMED_BODY = b'not json'
NON_OBJECT_BODY = b'[1, 2]'
OVERSIZE_KEY = 'k' * 256
NON_ASCII_KEY = b'\xe9'


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


async def test_duplicate_webhook_returns_indistinguishable_accepted_response(
    client: AsyncClient,
    signed_headers: Callable[[bytes], dict[str, str]],
) -> None:
    headers = signed_headers(BODY) | {'Idempotency-Key': IDEMPOTENCY_KEY}
    initial_response = await client.post(
        f'/v1/webhooks/{SOURCE}',
        content=BODY,
        headers=headers,
    )
    retry_response = await client.post(
        f'/v1/webhooks/{SOURCE}',
        content=BODY,
        headers=headers,
    )
    assert initial_response.status_code == status.HTTP_202_ACCEPTED
    assert retry_response.status_code == initial_response.status_code
    assert initial_response.content == retry_response.content


async def test_malformed_json_body_returns_400(
    client: AsyncClient,
    signed_headers: Callable[[bytes], dict[str, str]],
) -> None:
    headers = signed_headers(MALFORMED_BODY)
    response = await client.post(
        f'/v1/webhooks/{SOURCE}',
        content=MALFORMED_BODY,
        headers=headers,
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()['detail'] == DETAIL_MALFORMED_JSON_CONTRACT


async def test_non_object_json_body_returns_400(
    client: AsyncClient,
    signed_headers: Callable[[bytes], dict[str, str]],
) -> None:
    headers = signed_headers(NON_OBJECT_BODY)
    response = await client.post(
        f'/v1/webhooks/{SOURCE}',
        content=NON_OBJECT_BODY,
        headers=headers,
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()['detail'] == DETAIL_PAYLOAD_NOT_OBJECT_CONTRACT


async def test_oversize_idempotency_key_returns_400(
    client: AsyncClient,
    signed_headers: Callable[[bytes], dict[str, str]],
) -> None:
    headers = signed_headers(BODY) | {'Idempotency-Key': OVERSIZE_KEY}
    response = await client.post(
        f'/v1/webhooks/{SOURCE}',
        content=BODY,
        headers=headers,
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    detail = response.json()['detail']
    assert detail == DETAIL_INVALID_IDEMPOTENCY_KEY_CONTRACT


async def test_non_ascii_idempotency_key_returns_400(
    client: AsyncClient,
    signed_headers: Callable[[bytes], dict[str, str]],
) -> None:
    # httpx2 не пропускает не-ASCII в строковом заголовке, поэтому шлём байты:
    # сервер декодирует их как latin-1, и проверка isascii отбивает ключ
    signed = signed_headers(BODY)
    headers: dict[bytes, bytes] = {
        name.encode(): value.encode() for name, value in signed.items()
    }
    headers[b'Idempotency-Key'] = NON_ASCII_KEY
    response = await client.post(
        f'/v1/webhooks/{SOURCE}',
        content=BODY,
        headers=headers,
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    detail = response.json()['detail']
    assert detail == DETAIL_INVALID_IDEMPOTENCY_KEY_CONTRACT


async def test_empty_idempotency_key_falls_back_to_body_hash(
    client: AsyncClient,
    conn: asyncpg.Connection,
    signed_headers: Callable[[bytes], dict[str, str]],
) -> None:
    headers = signed_headers(BODY) | {'Idempotency-Key': ''}
    response = await client.post(
        f'/v1/webhooks/{SOURCE}',
        content=BODY,
        headers=headers,
    )
    assert response.status_code == status.HTTP_202_ACCEPTED

    fallback_key = hashlib.sha256(BODY).hexdigest()
    event_id = await conn.fetchval(
        'SELECT id FROM webhooks_event WHERE source=$1 AND idempotency_key=$2',
        SOURCE,
        fallback_key,
    )
    assert event_id is not None
