"""Outbox command seam tests."""

from io import StringIO
from unittest.mock import call, patch

from django.core.management import CommandError, call_command
from django.test import TransactionTestCase
from kombu.exceptions import OperationalError

from management.webhooks.management.commands import publish_outbox
from management.webhooks.models import Event, OutboxMessage, OutboxStatus


def _make_outbox(key):
    """Creates pending outbox row."""
    event = Event.objects.create(
        source='generic_json',
        idempotency_key=key,
        payload={'k': key},
    )
    return OutboxMessage.objects.create(event=event)


class PublishOutboxCommandTest(TransactionTestCase):
    """Outbox command boundary tests."""

    def test_queues_task_with_event_id(self):
        with patch.object(publish_outbox.deliver_event, 'delay') as mock_delay:
            publish_outbox.submit_delivery(42)
        mock_delay.assert_called_once_with(42)

    def test_marks_rows_published_after_queueing(self):
        Event.objects.create(
            source='generic_json',
            idempotency_key='without-outbox',
            payload={},
        )
        rows = [_make_outbox(f'k{i}') for i in range(3)]
        with patch.object(publish_outbox.deliver_event, 'delay') as mock_delay:
            call_command(
                'publish_outbox',
                batch_size=10,
                stdout=StringIO(),
            )
        self.assertCountEqual(
            mock_delay.call_args_list,
            [call(row.event_id) for row in rows],
        )
        for row in rows:
            row.refresh_from_db()
            self.assertEqual(row.status, OutboxStatus.PUBLISHED)
            self.assertIsNotNone(row.published_at)

    def test_broker_failure_leaves_rows_pending(self):
        rows = [_make_outbox(f'k{i}') for i in range(3)]
        with patch.object(publish_outbox.deliver_event, 'delay') as mock_delay:
            mock_delay.side_effect = [None, OperationalError('broker down')]
            with self.assertRaises(CommandError) as caught:
                call_command(
                    'publish_outbox',
                    batch_size=10,
                    stdout=StringIO(),
                )
        self.assertEqual(
            str(caught.exception),
            'broker unavailable: broker down',
        )
        self.assertEqual(mock_delay.call_count, 2)
        for row in rows:
            row.refresh_from_db()
            self.assertEqual(row.status, OutboxStatus.PENDING)
            self.assertIsNone(row.published_at)
