"""Event delivery task branches."""

from django.test import TransactionTestCase

from management.webhooks.models import Event
from management.webhooks.tasks import deliver_event


class DeliverEventTest(TransactionTestCase):
    """Event delivery task branches."""

    def test_missing_event_is_skipped_with_warning(self):
        with self.assertLogs(
            'management.webhooks.tasks', level='WARNING'
        ) as logs:
            deliver_event(42)
        self.assertIn('event 42 is missing', logs.output[0])
        self.assertEqual(logs.records[0].levelname, 'WARNING')

    def test_existing_event_raises_not_implemented_with_pk(self):
        event = Event.objects.create(
            source='generic_json',
            idempotency_key='k1',
            payload={'k': 'k1'},
        )
        with self.assertRaises(NotImplementedError) as caught:
            deliver_event(event.pk)
        self.assertEqual(
            str(caught.exception),
            f'delivery of event {event.pk} is not wired yet',
        )
