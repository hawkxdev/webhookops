"""Outbox publisher entry point."""

from django.core.management.base import BaseCommand, CommandError

from management.webhooks.publisher import publish_pending


def submit_delivery(event_id):
    """Raises until the delivery task lands."""
    raise NotImplementedError('delivery task is not wired yet')


class Command(BaseCommand):
    """Runs one publisher pass."""

    help = 'Takes pending outbox rows and hands them to the broker submitter.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Maximum rows per publisher pass.',
        )

    def handle(self, *args, **options):
        try:
            published = publish_pending(
                options['batch_size'],
                submit_delivery,
            )
        except ValueError as error:
            raise CommandError(str(error))
        except NotImplementedError:
            raise CommandError('delivery task is not wired yet')
        self.stdout.write(self.style.SUCCESS(f'Published {published} rows.'))
