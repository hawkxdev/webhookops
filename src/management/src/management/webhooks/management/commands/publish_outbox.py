"""Outbox publisher entry point."""

from django.core.management.base import BaseCommand, CommandError
from kombu.exceptions import OperationalError

from management.webhooks.publisher import publish_pending
from management.webhooks.tasks import deliver_event


def submit_delivery(event_id: int) -> None:
    """Queues one delivery task."""
    deliver_event.delay(event_id)


class Command(BaseCommand):
    """Runs one publisher pass."""

    help = 'Takes pending outbox rows and hands them to the broker submitter.'

    def add_arguments(self, parser):
        """Registers batch size option."""
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Maximum rows per publisher pass.',
        )

    def handle(self, *args, **options):
        """Executes one publisher pass."""
        try:
            published = publish_pending(
                options['batch_size'],
                submit_delivery,
            )
        except ValueError as error:
            raise CommandError(str(error))
        except OperationalError as error:
            raise CommandError(f'broker unavailable: {error}') from error
        self.stdout.write(self.style.SUCCESS(f'Published {published} rows.'))
