"""Тесты контракта записи."""

import asyncpg
import pytest

from shared import persistence
from shared.persistence import persist_event

SOURCE = 'generic_json'
IDEMPOTENCY_KEY = 'key-1'

BROKEN_SQL = """
    INSERT INTO no_such_outbox_table (event_id, status, created_at)
    VALUES ($1, 'pending', now())
"""

COUNT_EVENTS = """
    SELECT count(*) FROM webhooks_event
    WHERE source = $1 AND idempotency_key = $2
"""

COUNT_OUTBOX = """
    SELECT count(*) FROM webhooks_outboxmessage WHERE event_id = $1
"""


async def test_first_call_creates_event_and_outbox(
    conn: asyncpg.Connection,
) -> None:
    result = await persist_event(
        conn,
        source=SOURCE,
        idempotency_key=IDEMPOTENCY_KEY,
        payload={'hello': 'world'},
    )
    assert result.created is True

    events = await conn.fetchval(COUNT_EVENTS, SOURCE, IDEMPOTENCY_KEY)
    outbox = await conn.fetchval(COUNT_OUTBOX, result.event_id)
    assert events == 1
    assert outbox == 1


async def test_duplicate_key_does_not_create_second_event(
    conn: asyncpg.Connection,
) -> None:
    first = await persist_event(
        conn,
        source=SOURCE,
        idempotency_key=IDEMPOTENCY_KEY,
        payload={'n': 1},
    )
    second = await persist_event(
        conn,
        source=SOURCE,
        idempotency_key=IDEMPOTENCY_KEY,
        payload={'n': 2},
    )
    assert second.created is False
    assert second.event_id == first.event_id

    events = await conn.fetchval(COUNT_EVENTS, SOURCE, IDEMPOTENCY_KEY)
    outbox = await conn.fetchval(COUNT_OUTBOX, first.event_id)
    assert events == 1
    assert outbox == 1


async def test_outbox_failure_rolls_back_event(
    conn: asyncpg.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(persistence, '_INSERT_OUTBOX', BROKEN_SQL)

    with pytest.raises(asyncpg.UndefinedTableError):
        await persist_event(
            conn,
            source=SOURCE,
            idempotency_key=IDEMPOTENCY_KEY,
            payload={'n': 1},
        )

    events = await conn.fetchval(COUNT_EVENTS, SOURCE, IDEMPOTENCY_KEY)
    assert events == 0
