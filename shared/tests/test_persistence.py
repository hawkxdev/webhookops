"""Тесты контракта записи."""

from shared.persistence import persist_event


async def test_first_call_creates_event_and_outbox(conn):
    result = await persist_event(
        conn,
        source='generic_json',
        idempotency_key='key-1',
        payload={'hello': 'world'},
    )

    assert result.created is True

    events = await conn.fetchval(
        'SELECT count(*) FROM webhooks_event '
        'WHERE source=$1 AND idempotency_key=$2',
        'generic_json',
        'key-1',
    )
    outbox = await conn.fetchval(
        'SELECT count(*) FROM webhooks_outboxmessage WHERE event_id=$1',
        result.event_id,
    )
    assert events == 1
    assert outbox == 1


async def test_duplicate_key_does_not_create_second_event(conn):
    first = await persist_event(
        conn,
        source='generic_json',
        idempotency_key='key-1',
        payload={'n': 1},
    )
    second = await persist_event(
        conn,
        source='generic_json',
        idempotency_key='key-1',
        payload={'n': 2},
    )

    assert second.created is False
    assert second.event_id == first.event_id

    events = await conn.fetchval(
        'SELECT count(*) FROM webhooks_event '
        'WHERE source=$1 AND idempotency_key=$2',
        'generic_json',
        'key-1',
    )
    outbox = await conn.fetchval(
        'SELECT count(*) FROM webhooks_outboxmessage WHERE event_id=$1',
        first.event_id,
    )
    assert events == 1
    assert outbox == 1
