"""Тесты ограничений схемы."""

import json

import asyncpg
import pytest

_INSERT_EVENT_WITHOUT_ON_CONFLICT = """
    INSERT INTO webhooks_event (source, idempotency_key, payload, received_at)
    VALUES ($1, $2, $3::jsonb, now())
    RETURNING id
"""


async def test_duplicate_source_key_raises_unique_violation(
    conn: asyncpg.Connection,
) -> None:
    source = 'generic_json'
    idempotency_key = 'key-1'
    payload = json.dumps({'n': 1})

    first_id = await conn.fetchval(
        _INSERT_EVENT_WITHOUT_ON_CONFLICT,
        source,
        idempotency_key,
        payload,
    )
    assert first_id is not None

    with pytest.raises(asyncpg.UniqueViolationError) as exc_info:
        await conn.execute(
            _INSERT_EVENT_WITHOUT_ON_CONFLICT,
            source,
            idempotency_key,
            payload,
        )
    assert (
        exc_info.value.constraint_name  # pyright: ignore
        == 'uniq_event_source_idempotency_key'
    )
