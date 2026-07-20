"""Контракт записи события и outbox."""

import json
from typing import NamedTuple

import asyncpg
from asyncpg.pool import PoolConnectionProxy

DBConnection = asyncpg.Connection | PoolConnectionProxy


class PersistResult(NamedTuple):
    """Итог записи события."""

    created: bool
    event_id: int


_INSERT_EVENT = """
    INSERT INTO webhooks_event (source, idempotency_key, payload, received_at)
    VALUES ($1, $2, $3::jsonb, now())
    ON CONFLICT (source, idempotency_key) DO NOTHING
    RETURNING id
"""

_INSERT_OUTBOX = """
    INSERT INTO webhooks_outboxmessage (event_id, status, created_at)
    VALUES ($1, 'pending', now())
"""

_SELECT_EVENT_ID = """
    SELECT id FROM webhooks_event
    WHERE source = $1 AND idempotency_key = $2
"""


async def persist_event(
    conn: DBConnection,
    *,
    source: str,
    idempotency_key: str,
    payload: dict,
) -> PersistResult:
    """Запись события и outbox в транзакции."""
    async with conn.transaction():
        event_id = await conn.fetchval(
            _INSERT_EVENT, source, idempotency_key, json.dumps(payload)
        )
        if event_id is not None:
            await conn.execute(_INSERT_OUTBOX, event_id)
            return PersistResult(created=True, event_id=event_id)

        existing_id = await conn.fetchval(
            _SELECT_EVENT_ID, source, idempotency_key
        )
        if existing_id is None:
            raise RuntimeError(
                'событие исчезло после конфликта идемпотентности'
            )
        return PersistResult(created=False, event_id=existing_id)
