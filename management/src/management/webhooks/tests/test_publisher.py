"""Outbox publisher tests."""

import psycopg
from django.db import connection
from django.test import TransactionTestCase
from psycopg import sql

from management.webhooks.models import Event, OutboxMessage, OutboxStatus
from management.webhooks.publisher import publish_pending


class Recorder:
    """Collects submitted event ids."""

    def __init__(self):
        self.event_ids = []

    def __call__(self, event_id):
        self.event_ids.append(event_id)


def _make_outbox(key):
    """Creates one event with a pending outbox row."""
    event = Event.objects.create(
        source='generic_json',
        idempotency_key=key,
        payload={'k': key},
    )
    return OutboxMessage.objects.create(event=event)


class PublishPendingTest(TransactionTestCase):
    """Single publisher pass over pending rows."""

    def test_publishes_whole_batch_and_marks_rows(self):
        events = [_make_outbox(f'k{i}') for i in range(3)]
        recorder = Recorder()
        published = publish_pending(10, recorder)
        self.assertEqual(published, 3)
        self.assertEqual(len(recorder.event_ids), 3)
        self.assertEqual(len(set(recorder.event_ids)), 3)
        expected = {event.event_id for event in events}
        self.assertEqual(set(recorder.event_ids), expected)
        for row in OutboxMessage.objects.all():
            self.assertEqual(row.status, OutboxStatus.PUBLISHED)
            self.assertIsNotNone(row.published_at)

    def test_batch_limit_leaves_rest_pending(self):
        for i in range(5):
            _make_outbox(f'k{i}')
        recorder = Recorder()
        self.assertEqual(publish_pending(3, recorder), 3)
        self.assertEqual(
            OutboxMessage.objects.filter(status=OutboxStatus.PENDING).count(),
            2,
        )
        self.assertEqual(publish_pending(3, recorder), 2)
        self.assertEqual(
            OutboxMessage.objects.filter(
                status=OutboxStatus.PUBLISHED
            ).count(),
            5,
        )

    def test_rejects_non_positive_batch_size(self):
        with self.assertRaises(ValueError):
            publish_pending(0, Recorder())
        with self.assertRaises(ValueError):
            publish_pending(-1, Recorder())

    def test_empty_outbox_publishes_nothing(self):
        recorder = Recorder()
        self.assertEqual(publish_pending(5, recorder), 0)
        self.assertEqual(recorder.event_ids, [])


class PublisherConcurrencyTest(TransactionTestCase):
    """Two concurrent takes split pending rows without overlap."""

    def _connect(self):
        params = connection.settings_dict
        kwargs = {
            'dbname': params['NAME'],
            'user': params['USER'],
            'password': params['PASSWORD'],
            'host': params['HOST'],
            'port': params['PORT'],
        }
        kwargs = {k: v for k, v in kwargs.items() if v}
        return psycopg.connect(**kwargs)

    def _take_pending(self, conn, limit):
        query = sql.SQL(
            'SELECT id FROM {} WHERE status = {} '
            'ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT %s'
        ).format(
            sql.Identifier(OutboxMessage._meta.db_table),
            sql.Literal(OutboxStatus.PENDING.value),
        )
        with conn.cursor() as cursor:
            cursor.execute(query, (limit,))
            return [row[0] for row in cursor.fetchall()]

    def _mark_published(self, conn, ids):
        query = sql.SQL(
            'UPDATE {} SET status = {}, published_at = now() '
            'WHERE id = ANY(%s)'
        ).format(
            sql.Identifier(OutboxMessage._meta.db_table),
            sql.Literal(OutboxStatus.PUBLISHED.value),
        )
        with conn.cursor() as cursor:
            cursor.execute(query, (ids,))
        conn.commit()

    def test_skip_locked_yields_disjoint_batches(self):
        for i in range(3):
            _make_outbox(f'k{i}')
        rows = list(OutboxMessage.objects.values_list('id', flat=True))
        self.assertEqual(len(rows), 3)
        conn_a = self._connect()
        conn_b = self._connect()
        try:
            taken_a = self._take_pending(conn_a, 2)
            self.assertEqual(len(taken_a), 2)
            taken_b = self._take_pending(conn_b, 2)
            self.assertEqual(len(taken_b), 1)
            self.assertEqual(set(taken_a) & set(taken_b), set())
            self.assertEqual(set(taken_a) | set(taken_b), set(rows))
            self.assertEqual(
                self._take_pending(conn_b, 2),
                taken_b,
            )
            conn_c = self._connect()
            try:
                self.assertEqual(self._take_pending(conn_c, 3), [])
            finally:
                conn_c.close()
            self._mark_published(conn_b, taken_b)
            self._mark_published(conn_a, taken_a)
        finally:
            conn_a.close()
            conn_b.close()
        self.assertEqual(
            OutboxMessage.objects.filter(status=OutboxStatus.PENDING).count(),
            0,
        )
        self.assertEqual(
            OutboxMessage.objects.filter(
                status=OutboxStatus.PUBLISHED,
                published_at__isnull=False,
            ).count(),
            3,
        )
